"""
main_demo.py — 발표용 파이프라인 실행 파일

DB 연결 없이 app/data/demo_data.py의 크롤링 대체 데이터로 전체 파이프라인을 시연합니다.
로직·출력 형식은 main.py와 동일하며, DB I/O 부분만 로컬 데이터로 대체됩니다.

    DB 조회  →  demo_data.py 상수
    DB 저장  →  콘솔 출력 (upsert 스킵)
"""

from collections import Counter

# ── 파이프라인 모듈 (main.py와 동일) ─────────────────────────────────────────
from app.services.nlp.nlp_preprocessing import ReviewPreprocessor         # STAGE 1  (clean_text 전처리)
from app.services.nlp.review_tfidf_analyze import ReviewTfidfAnalyzer     # STAGE 1  (형태소 분석) + STAGE 1b (TF-IDF)
from app.services.nlp.keyword_normalizer import KeywordNormalizer          # STAGE 1a (표현 통일)
from app.services.scoring.keyword_scorer import keywordScorer              # STAGE 3  (스코어링)
from app.output.keyword_formatter import expand_nlp_keywords, attach_inducement  # STAGE 3.5 / 4
from app.data.blocklist import KEYWORD_BLOCKLIST                           # STAGE 1a (범용어 제거)

# ── 발표용 로컬 데이터 ────────────────────────────────────────────────────────
from app.data.demo_data import (
    DEMO_REVIEWS,
    DEMO_RANKINGS,
    DEMO_SEARCH_VOLUMES,
    DEMO_PLACE_INFO,
)


# ── DB 대체 함수 ──────────────────────────────────────────────────────────────
def _get_reviews() -> list[dict]:
    return DEMO_REVIEWS


def _get_review_dates() -> dict[int, object]:
    return {r["id"]: r["created_at"] for r in DEMO_REVIEWS}


def _get_place_info() -> dict:
    return DEMO_PLACE_INFO


def _get_place_rankings() -> list[dict]:
    return DEMO_RANKINGS


def _get_keyword_monthly_search(keyword_names: list[str]) -> dict[str, int]:
    return {kw: DEMO_SEARCH_VOLUMES.get(kw, 0) for kw in keyword_names}


# ── STAGE 2 인라인 구현 (keyword_merger가 repository를 직접 호출하므로 대체) ──
def _merge_keywords_demo(
    nlp_tfidf:      dict[str, float],
    nlp_per_review: dict[int, Counter],
) -> tuple[dict, dict, dict]:
    """
    keyword_merger.merge_keywords()와 동일한 로직.
    get_place_rankings / get_keyword_monthly_search 호출을 로컬 데이터로 대체.
    """
    CASE_B_SCORE_CAP = 0.7

    rankings       = _get_place_rankings()
    ranked_keywords: set[str]      = {r["keyword"] for r in rankings}
    rank_map: dict[str, dict]      = {r["keyword"]: r for r in rankings}
    search_volumes: dict[str, int] = _get_keyword_monthly_search(list(ranked_keywords))

    # mention_count: 각 키워드가 등장한 리뷰 수
    mention_counts: dict[str, int] = {}
    for counter in nlp_per_review.values():
        for kw in counter:
            mention_counts[kw] = mention_counts.get(kw, 0) + 1

    nlp_keywords = set(nlp_tfidf.keys())
    case_a = nlp_keywords & ranked_keywords
    case_b = ranked_keywords - nlp_keywords
    case_c = nlp_keywords - ranked_keywords

    # CASE B 합성 점수
    max_nlp_score  = max(nlp_tfidf.values()) if nlp_tfidf else 1.0
    case_b_volumes = {kw: search_volumes.get(kw, 0) for kw in case_b}
    max_b_volume   = max(case_b_volumes.values(), default=1) or 1
    case_b_scores  = {
        kw: round((vol / max_b_volume) * max_nlp_score * CASE_B_SCORE_CAP, 6)
        for kw, vol in case_b_volumes.items()
    }

    merged_tfidf: dict[str, float] = {**nlp_tfidf, **case_b_scores}
    merged_per_review               = dict(nlp_per_review)

    COMPETITION_THRESHOLDS = {"높음": 10_000, "중간": 1_000}

    def _competition_level(vol: int) -> str:
        if vol >= COMPETITION_THRESHOLDS["높음"]: return "높음"
        if vol >= COMPETITION_THRESHOLDS["중간"]: return "중간"
        return "낮음"

    keyword_meta: dict[str, dict] = {}
    for kw in merged_tfidf:
        rank_info   = rank_map.get(kw, {})
        rank_no     = rank_info.get("rank_no")
        search_vol  = search_volumes.get(kw, 0)
        case_type   = "A" if kw in case_a else ("B" if kw in case_b else "C")
        keyword_meta[kw] = {
            "case_type":             case_type,
            "rank_no":               rank_no,
            "rank_no_change":        rank_info.get("rank_no_change", 0),
            "monthly_search_volume": search_vol,
            "mention_count":         mention_counts.get(kw, 0),
            "competition_level":     _competition_level(search_vol),
            "is_opportunity":        search_vol >= 1_000 and (rank_no is None or rank_no > 10),
        }

    return merged_tfidf, merged_per_review, keyword_meta


# ── 출력 헬퍼 (main.py와 동일) ────────────────────────────────────────────────
def _print_counter_sample(title: str, counter: Counter, top: int = 15):
    print(f"\n  [{title}] 상위 {top}개")
    for kw, cnt in counter.most_common(top):
        print(f"    {kw:<18} {cnt}")

def _sep(label: str):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)


# ── 파이프라인 ─────────────────────────────────────────────────────────────────
def run():

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 0 · 데이터 로드 (DB 대신 demo_data.py)
    # ══════════════════════════════════════════════════════════════════════
    reviews      = _get_reviews()
    review_dates = _get_review_dates()
    place_info   = _get_place_info()

    _sep("STAGE 0 · 데이터 로드 [DEMO]")
    print(f"  리뷰 수        : {len(reviews)}개")
    print(f"  날짜 매핑 수   : {len(review_dates)}개")
    print(f"  매장명         : {place_info['name']}")
    print(f"  업종           : {place_info['category']}")
    print(f"  동네/역세권    : {place_info['neighborhood']}")
    print(f"  시/구          : {place_info['city']}")
    print(f"  리뷰 샘플 (10개):")
    for r in reviews[:10]:
        body = r["content"][:60].replace("\n", " ")
        print(f"    id={r['id']} | {body}...")

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 1 · 형태소 분석
    # ══════════════════════════════════════════════════════════════════════
    analyzer   = ReviewTfidfAnalyzer()
    per_review = analyzer.extract_per_review(reviews)

    _sep("STAGE 1 · 형태소 분석 (Okt POS)")
    total_tokens_s1 = sum(sum(c.values()) for c in per_review.values())
    unique_kw_s1    = len(set(kw for c in per_review.values() for kw in c))
    print(f"  리뷰별 Counter 수  : {len(per_review)}개")
    print(f"  전체 토큰 수       : {total_tokens_s1}개")
    print(f"  고유 키워드 수     : {unique_kw_s1}개")
    all_s1: Counter = Counter()
    for c in per_review.values():
        all_s1.update(c)
    _print_counter_sample("전체 합산 키워드", all_s1, top=20)

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 1a · BLOCKLIST 필터 + 동의어 정규화
    # ══════════════════════════════════════════════════════════════════════
    normalizer        = KeywordNormalizer()
    per_review_clean  : dict[int, Counter] = {}
    blocklist_removed : Counter = Counter()

    for review_id, counter in per_review.items():
        removed  = Counter({kw: cnt for kw, cnt in counter.items() if kw in KEYWORD_BLOCKLIST})
        filtered = Counter({kw: cnt for kw, cnt in counter.items() if kw not in KEYWORD_BLOCKLIST})
        blocklist_removed.update(removed)
        per_review_clean[review_id] = normalizer.normalize(filtered)

    _sep("STAGE 1a · BLOCKLIST 필터 + 표현 통일")
    total_tokens_clean = sum(sum(c.values()) for c in per_review_clean.values())
    unique_kw_clean    = len(set(kw for c in per_review_clean.values() for kw in c))
    print(f"  블랙리스트 제거 키워드 ({len(blocklist_removed)}종):")
    for kw, cnt in blocklist_removed.most_common():
        print(f"    '{kw}' × {cnt}회 제거")
    print(f"  정제 후 전체 토큰 수  : {total_tokens_clean}개 (제거 전 {total_tokens_s1}개)")
    print(f"  정제 후 고유 키워드   : {unique_kw_clean}개 (제거 전 {unique_kw_s1}개)")
    all_clean: Counter = Counter()
    for c in per_review_clean.values():
        all_clean.update(c)
    _print_counter_sample("정제 후 합산 키워드", all_clean, top=20)

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 1b · TF-IDF 계산
    # ══════════════════════════════════════════════════════════════════════
    tfidf = analyzer.compute_tfidf(per_review_clean)

    _sep("STAGE 1b · TF-IDF")
    print(f"  TF-IDF 키워드 수 : {len(tfidf)}개")
    print(f"  score=0 키워드   : {sum(1 for v in tfidf.values() if v == 0.0)}개  (df=N → IDF=0, 정상)")
    print(f"\n  {'키워드':<18} {'TF-IDF':>8}")
    print(f"  {'-'*28}")
    for kw, score in sorted(tfidf.items(), key=lambda x: -x[1])[:20]:
        print(f"  {kw:<18} {score:>8.5f}")

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 2 · 외부 키워드 결합 (CASE A/B/C)
    # ══════════════════════════════════════════════════════════════════════
    merged_tfidf, merged_per_review, keyword_meta = _merge_keywords_demo(
        nlp_tfidf      = tfidf,
        nlp_per_review = per_review_clean,
    )

    _sep("STAGE 2 · 외부 키워드 결합 [DEMO 순위 데이터]")
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

    case_a_items = [(kw, m) for kw, m in keyword_meta.items() if m["case_type"] == "A"]
    if case_a_items:
        print(f"\n  [CASE A] NLP∩순위 키워드")
        print(f"  {'키워드':<22} {'순위':>4}  {'변동':>4}  {'검색량':>8}  {'NLP점수':>8}")
        print(f"  {'-'*56}")
        for kw, m in sorted(case_a_items, key=lambda x: x[1]["rank_no"] or 999):
            print(f"  {kw:<22} {str(m['rank_no']):>4}  {m['rank_no_change']:>+4}  "
                  f"{m['monthly_search_volume']:>8,}  {merged_tfidf.get(kw, 0):>8.5f}")

    case_b_items = [(kw, m) for kw, m in keyword_meta.items() if m["case_type"] == "B"]
    if case_b_items:
        print(f"\n  [CASE B] 순위only 키워드")
        print(f"  {'키워드':<22} {'순위':>4}  {'검색량':>8}  {'경쟁도':<6}  {'기회':>4}")
        print(f"  {'-'*52}")
        for kw, m in sorted(case_b_items, key=lambda x: x[1]["rank_no"] or 999):
            print(f"  {kw:<22} {str(m['rank_no']):>4}  "
                  f"{m['monthly_search_volume']:>8,}  {m['competition_level']:<6}  "
                  f"{'O' if m['is_opportunity'] else 'X':>4}")

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 3 · 스코어링
    # ══════════════════════════════════════════════════════════════════════
    scorer = keywordScorer()
    scored = scorer._calc_score(
        tfidf        = merged_tfidf,
        per_review   = merged_per_review,
        review_dates = review_dates,
        sentiment    = None,
    )

    _sep("STAGE 3 · 스코어링")
    print(f"  채점 키워드 수 : {len(scored)}개")
    print(f"\n  {'키워드':<22} {'최종':>6}  {'TF-IDF':>7}  {'감성':>6}  {'최신성':>6}  {'일관성':>6}")
    print(f"  {'-'*66}")
    for item in scored[:25]:
        b = item["breakdown"]
        print(f"  {item['keyword']:<22} {item['score']:>6.4f}  "
              f"{b['tfidf']:>7.4f}  {b['sentiment']:>6.4f}  "
              f"{b['recency']:>6.4f}  {b['consistency']:>6.4f}")

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 3.5 · NLP 키워드 의미 태깅 + 메뉴 검색형 확장
    # ══════════════════════════════════════════════════════════════════════
    expanded     = expand_nlp_keywords(scored, use_similarity=True)
    nlp_keywords = [{**item, "source": "nlp"} for item in expanded]

    _sep("STAGE 3.5 · NLP 키워드 의미 태깅 + 메뉴 검색형 확장")
    search_kws    = [it for it in expanded if it["keyword_purpose"] == "search"]
    marketing_kws = [it for it in expanded if it["keyword_purpose"] == "marketing"]
    induced_kws   = [it for it in expanded if it["is_induced"]]
    print(f"  원본 scored      : {len(scored)}개")
    print(f"  확장 후 총 키워드 : {len(expanded)}개  "
          f"(search={len(search_kws)}, marketing={len(marketing_kws)}, "
          f"induced={len(induced_kws)})")
    if induced_kws:
        print(f"\n  [유도어 결합형 샘플]")
        for it in induced_kws[:8]:
            print(f"    {it['keyword']:<28}  {it['category']}/{it['property']}")

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 4 · 의미 태깅 + 포맷팅
    # ══════════════════════════════════════════════════════════════════════
    formatted = attach_inducement(nlp_keywords, top_n=20, use_similarity=True)

    for item in formatted:
        base_kw = (
            " ".join(item["keyword"].split()[:-1])
            if item["is_induced"]
            else item["keyword"]
        )
        meta = keyword_meta.get(base_kw, {})
        item["case_type"]             = meta.get("case_type", "C")
        item["rank_no"]               = meta.get("rank_no")
        item["rank_no_change"]        = meta.get("rank_no_change", 0)
        item["monthly_search_volume"] = meta.get("monthly_search_volume", 0)
        item["mention_count"]         = meta.get("mention_count", 0)
        item["competition_level"]     = meta.get("competition_level", "낮음")
        item["is_opportunity"]        = meta.get("is_opportunity", False)

    _sep("STAGE 4 · 의미 태깅 + 포맷팅")
    print(f"  입력 top-20 → 출력 {len(formatted)}개")
    print(f"\n  {'키워드':<26} {'점수':>6}  {'카테고리':<8}  {'목적':<10}  induced")
    print(f"  {'-'*68}")
    for item in formatted:
        print(f"  {item['keyword']:<26} {item['base_score']:>6.4f}  "
              f"{item['category']:<8}  {item['keyword_purpose']:<10}  "
              f"{'O' if item['is_induced'] else 'X':^6}")

    untagged = [it for it in formatted if not it["is_induced"] and it["category"] == "미분류"]
    if untagged:
        print(f"\n  ※ 미분류 키워드 {len(untagged)}개:")
        for it in untagged:
            print(f"    - {it['keyword']}")

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 5 · 결과 출력 (DB 저장 대신 콘솔 출력)
    # ══════════════════════════════════════════════════════════════════════
    _sep("STAGE 5 · 최종 추천 키워드 [DEMO — DB 저장 스킵]")
    print(f"\n  {'#':<3}  {'키워드':<26} {'점수':>6}  {'CASE'}  {'순위':>4}  {'검색량':>8}  {'경쟁도':<6}  기회")
    print(f"  {'-'*78}")
    for i, item in enumerate(formatted, 1):
        print(f"  {i:<3}  {item['keyword']:<26} {item['base_score']:>6.4f}  "
              f"{item['case_type']:<4}  "
              f"{str(item['rank_no']) if item['rank_no'] else '-':>4}  "
              f"{item['monthly_search_volume']:>8,}  "
              f"{item['competition_level']:<6}  "
              f"{'★' if item['is_opportunity'] else ''}")
    print(f"\n  총 {len(formatted)}개 키워드 생성 완료")


if __name__ == "__main__":
    run()
