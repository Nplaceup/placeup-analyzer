# STAGE 2.5 · 외부 키워드 결합
#
# ─ 역할 ──────────────────────────────────────────────────────────────────────
# NLP 추출 키워드(STAGE 2 결과)와 RDS 순위 데이터를 병합.
# CASE A/B/C로 분류해 최종 merged_tfidf / keyword_meta 생성.
#
# ─ CASE 정의 ────────────────────────────────────────────────────────────────
# CASE A : NLP ∩ rankings  — 리뷰에도 언급되고 현재 순위도 있는 키워드
#           → NLP 점수 유지 + 순위 메타데이터 결합
# CASE B : rankings only   — 순위는 있으나 NLP에서 추출되지 않은 키워드
#           → 검색량 기반 합성 점수로 merged_tfidf에 추가
# CASE C : NLP only        — NLP에서 추출됐으나 순위 데이터 없음
#           → NLP 점수 그대로 유지
#
# ─ is_opportunity 판별 ──────────────────────────────────────────────────────
# 검색량이 높은(≥ 1000)데 순위권(≤ 10위) 밖에 있는 키워드 → 개선 여지 있음
#
# ─ 파이프라인 위치 ───────────────────────────────────────────────────────────
# STAGE 2 (N-gram) → [STAGE 2.5] → STAGE 3 (scorer)

from collections import Counter

from app.db.repository import get_place_rankings, get_keyword_monthly_search


# 경쟁도 분류 기준 (월간 검색량 기준)
COMPETITION_THRESHOLDS = {
    "높음": 10_000,
    "중간": 1_000,
    # 미만 → "낮음"
}

# CASE B 합성 점수 상한 (NLP top 점수 대비 비율)
# 순위만 있는 키워드가 NLP 키워드를 밀어내지 않도록 캡 적용
CASE_B_SCORE_CAP = 0.7


def get_competition_level(monthly_search_volume: int) -> str:
    if monthly_search_volume >= COMPETITION_THRESHOLDS["높음"]:
        return "높음"
    if monthly_search_volume >= COMPETITION_THRESHOLDS["중간"]:
        return "중간"
    return "낮음"


def merge_keywords(
    place_id: int,
    nlp_tfidf: dict[str, float],
    nlp_per_review: dict[int, Counter],
) -> tuple[dict[str, float], dict[int, Counter], dict[str, dict]]:
    """
    NLP 추출 키워드 + RDS 순위 데이터 병합.

    Parameters
    ----------
    place_id      : 매장 ID
    nlp_tfidf     : STAGE 2 merged_tfidf  {keyword: tfidf_score}
    nlp_per_review: STAGE 2 merged_per_review  {review_id: Counter}

    Returns
    -------
    merged_tfidf     : CASE A/B/C 키워드 포함  {keyword: float}
    merged_per_review: CASE B 합성 Counter 추가  {review_id: Counter}
                       ※ CASE B는 mention_count=0, recency=0, consistency=0
    keyword_meta     : 키워드별 CASE/순위/검색량 메타데이터
                       {keyword: {case_type, rank_no, rank_no_change,
                                  monthly_search_volume, mention_count,
                                  competition_level, is_opportunity}}
    """
    # ── 0. RDS 데이터 조회 ─────────────────────────────────────────────────
    rankings: list[dict] = get_place_rankings(place_id)

    # 순위 키워드 집합 및 검색량 조회
    ranked_keywords: set[str]     = {r["keyword"] for r in rankings}
    rank_map: dict[str, dict]     = {r["keyword"]: r for r in rankings}
    search_volumes: dict[str, int] = get_keyword_monthly_search(list(ranked_keywords))

    # ── 1. mention_count 계산 (per_review 기반) ────────────────────────────
    # 각 키워드가 몇 개 리뷰에 등장했는지
    mention_counts: dict[str, int] = {}
    for counter in nlp_per_review.values():
        for kw in counter:
            mention_counts[kw] = mention_counts.get(kw, 0) + 1

    # ── 2. CASE 분류 ────────────────────────────────────────────────────────
    nlp_keywords: set[str] = set(nlp_tfidf.keys())
    case_a = nlp_keywords & ranked_keywords   # NLP ∩ rankings
    case_b = ranked_keywords - nlp_keywords   # rankings only
    case_c = nlp_keywords - ranked_keywords   # NLP only

    # ── 3. CASE B 합성 점수 계산 ────────────────────────────────────────────
    # 검색량 기반으로 NLP top 점수의 최대 CASE_B_SCORE_CAP 비율로 스케일
    max_nlp_score  = max(nlp_tfidf.values()) if nlp_tfidf else 1.0
    case_b_volumes = {kw: search_volumes.get(kw, 0) for kw in case_b}
    max_b_volume   = max(case_b_volumes.values(), default=1) or 1

    case_b_scores: dict[str, float] = {
        kw: round((vol / max_b_volume) * max_nlp_score * CASE_B_SCORE_CAP, 6)
        for kw, vol in case_b_volumes.items()
    }

    # ── 4. merged_tfidf 구성 (CASE A + C 유지, CASE B 추가) ────────────────
    merged_tfidf: dict[str, float] = dict(nlp_tfidf)   # CASE A + C
    merged_tfidf.update(case_b_scores)                  # CASE B 추가

    # ── 5. merged_per_review — CASE B는 빈 Counter (리뷰 언급 없음) ──────────
    # scorer가 CASE B에 대해 recency=0, consistency=0 반환하는 것이 의도된 동작
    merged_per_review: dict[int, Counter] = dict(nlp_per_review)

    # ── 6. keyword_meta 구성 ───────────────────────────────────────────────
    keyword_meta: dict[str, dict] = {}

    for kw in merged_tfidf:
        rank_info   = rank_map.get(kw, {})
        rank_no     = rank_info.get("rank_no")
        rank_change = rank_info.get("rank_no_change", 0)
        search_vol  = search_volumes.get(kw, 0)
        mention_cnt = mention_counts.get(kw, 0)

        if kw in case_a:
            case_type = "A"
        elif kw in case_b:
            case_type = "B"
        else:
            case_type = "C"

        # is_opportunity: 검색량 높은데 10위권 밖이거나 순위 없는 키워드
        is_opportunity = (
            search_vol >= COMPETITION_THRESHOLDS["중간"]
            and (rank_no is None or rank_no > 10)
        )

        keyword_meta[kw] = {
            "case_type":              case_type,
            "rank_no":                rank_no,
            "rank_no_change":         rank_change,
            "monthly_search_volume":  search_vol,
            "mention_count":          mention_cnt,
            "competition_level":      get_competition_level(search_vol),
            "is_opportunity":         is_opportunity,
        }

    return merged_tfidf, merged_per_review, keyword_meta


def summarize_merge_result(
    keyword_meta: dict[str, dict],
    nlp_tfidf: dict[str, float],
) -> None:
    """
    STAGE 2.5 결과 요약 출력 (디버그용).
    main.py _sep() 블록 내에서 호출.
    """
    case_counts = {"A": 0, "B": 0, "C": 0}
    opp_count   = 0

    for meta in keyword_meta.values():
        case_counts[meta["case_type"]] += 1
        if meta["is_opportunity"]:
            opp_count += 1

    print(f"  CASE A (NLP∩순위)  : {case_counts['A']:>4}개")
    print(f"  CASE B (순위only)   : {case_counts['B']:>4}개  (합성 점수로 추가)")
    print(f"  CASE C (NLP only)  : {case_counts['C']:>4}개")
    print(f"  is_opportunity     : {opp_count:>4}개")

    # CASE A 상세 (순위 + NLP 점수)
    case_a_items = [
        (kw, meta) for kw, meta in keyword_meta.items()
        if meta["case_type"] == "A"
    ]
    if case_a_items:
        print(f"\n  [CASE A] NLP∩순위 키워드")
        print(f"  {'키워드':<18} {'순위':>4}  {'변동':>4}  {'검색량':>8}  {'NLP점수':>8}")
        print(f"  {'-'*52}")
        for kw, meta in sorted(case_a_items, key=lambda x: x[1]["rank_no"] or 999):
            print(
                f"  {kw:<18} {str(meta['rank_no']):>4}  "
                f"{meta['rank_no_change']:>+4}  "
                f"{meta['monthly_search_volume']:>8,}  "
                f"{nlp_tfidf.get(kw, 0):>8.5f}"
            )

    # CASE B 상세 (순위만 있는 키워드)
    case_b_items = [
        (kw, meta) for kw, meta in keyword_meta.items()
        if meta["case_type"] == "B"
    ]
    if case_b_items:
        print(f"\n  [CASE B] 순위only 키워드 (리뷰 미언급 → 합성 점수 부여)")
        print(f"  {'키워드':<18} {'순위':>4}  {'검색량':>8}  {'경쟁도':<6}  {'기회':>4}")
        print(f"  {'-'*48}")
        for kw, meta in sorted(case_b_items, key=lambda x: x[1]["rank_no"] or 999):
            print(
                f"  {kw:<18} {str(meta['rank_no']):>4}  "
                f"{meta['monthly_search_volume']:>8,}  "
                f"{meta['competition_level']:<6}  "
                f"{'O' if meta['is_opportunity'] else 'X':>4}"
            )
