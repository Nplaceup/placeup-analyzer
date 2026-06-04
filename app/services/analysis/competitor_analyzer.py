# 모듈3 · 경쟁업체 키워드 분석
#
# ─ 역할 ──────────────────────────────────────────────────────────────────────
# 동일 카테고리+지역의 상위 경쟁업체(리뷰수 기준) 키워드를 분석해
# 갭 키워드 / 순위역전 키워드 / 독점 키워드 / 카테고리 갭을 추출한다.
#
# ─ 출력 구분 ─────────────────────────────────────────────────────────────────
# [blender 투입]    gap_keywords, rank_gap_keywords
# [프론트 전용]     advantage_keywords, category_gap
#
# ─ 파이프라인 위치 ───────────────────────────────────────────────────────────
# STAGE 0 (place_info 조회) → [모듈1] → (모듈2) → [*모듈3*] → keyword_blender

from collections import Counter, defaultdict

from app.db.repository import (
    get_competitor_place_ids,     # 카테고리+지역 기반 경쟁업체 ID 조회
    get_keywords_by_place_ids,    # place_id 리스트로 키워드+순위 조회
    get_place_rankings,           # place_id로 내 키워드+순위 조회
    get_keyword_monthly_search,   # 키워드 리스트로 월간 검색량 조회
    get_competitor_names,         # place_id 리스트로 업체명 조회
)
from app.data.semantic_dictionary import get_semantic_tag
from app.core.config import COMPETITOR_LIMIT, MIN_COMPETITOR_COUNT

# 크롤러 순위 추적 범위 (70위까지만 수집, 이후는 null 반환)
# rank_gap 계산 시 null → RANK_UNTRACKED으로 처리해 누락 방지
RANK_UNTRACKED = 71


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _get_category(keyword: str) -> str:
    """
    semantic_dictionary 직접 조회로 키워드 카테고리 반환.
    미등록 키워드는 "미분류" 반환 (SemanticMapper 미사용 — 속도 우선).
    """
    tag = get_semantic_tag(keyword)
    return tag.category if tag is not None else "미분류"


def _normalize_scores(items: list[dict]) -> list[dict]:
    """score 필드를 0~1로 정규화. items가 비어있으면 그대로 반환."""
    if not items:
        return items
    max_score = max(item["score"] for item in items) or 1.0
    for item in items:
        item["score"] = round(item["score"] / max_score, 4)
    return items


# ── 메인 함수 ─────────────────────────────────────────────────────────────────

def analyze_competitors(
    place_id:    int,
    place_info:  dict,
    my_keywords: set[str],
) -> dict:
    """
    경쟁업체 키워드 분석 결과를 반환한다.

    Parameters
    ----------
    place_id    : 내 매장 ID
    place_info  : get_place_info() 반환값 {"category", "city", ...}
    my_keywords : 현재 내 키워드 집합 (CASE A+B+C 전체)
                  gap/advantage 판별 기준

    Returns
    -------
    {
        "gap_keywords": [
            {
                "keyword":               str,
                "score":                 float,   # 0~1
                "source":                "competitor",
                "competitor_count":      int,     # 몇 개 업체에서 등장
                "monthly_search_volume": int,
            }, ...
        ],
        "rank_gap_keywords": [
            {
                "keyword":               str,
                "score":                 float,   # 0~1
                "source":                "competitor",
                "my_rank_no":            int,
                "competitor_avg_rank":   float,
                "rank_gap":              float,   # my_rank_no - competitor_avg_rank (양수 = 내가 불리)
                "monthly_search_volume": int,
            }, ...
        ],
        "advantage_keywords": [                  # 프론트 전용 — 내 독점 키워드
            {"keyword": str, "monthly_search_volume": int}, ...
        ],
        "category_gap": {                        # 프론트 전용 — 카테고리별 비교
            category: {
                "mine":            int,
                "competitor_avg":  float,
            }, ...
        },
        "competitor_count": int,                 # 실제 분석된 경쟁업체 수
        "competitor_names": [str, ...],          # 프론트 전용 — 경쟁업체 이름 목록
    }

    경쟁업체를 찾지 못하면 모든 리스트가 빈 값인 dict 반환.
    """
    _empty = {
        "gap_keywords":      [],
        "rank_gap_keywords": [],
        "advantage_keywords":[],
        "category_gap":      {},
        "competitor_count":  0,
        "competitor_names":  [],
    }

    category = place_info.get("category", "")
    city     = place_info.get("city", "")
    if not category or not city:
        return _empty

    # ── 1. 경쟁업체 ID 조회 (리뷰수 내림차순 상위 N개) ──────────────────────
    competitor_ids = get_competitor_place_ids(
        category         = category,
        city             = city,
        exclude_place_id = place_id,
        limit            = COMPETITOR_LIMIT,
    )
    if not competitor_ids:
        return _empty

    n_competitors = len(competitor_ids)
    name_map = get_competitor_names(competitor_ids)

    # ── 2. 경쟁업체 키워드+순위 수집 ─────────────────────────────────────────
    competitor_kw_map = get_keywords_by_place_ids(competitor_ids)
    # {place_id: [{"keyword": str, "rank_no": int}, ...]}

    # 키워드별 등장 업체 수 + 순위 목록 집계
    kw_freq:  Counter               = Counter()
    kw_ranks: dict[str, list[int]]  = defaultdict(list)

    for kwd in competitor_kw_map.values():
        seen_in_place: set[str] = set()
        for item in kwd:
            kw = item["keyword"]
            if kw not in seen_in_place:
                kw_freq[kw] += 1
                seen_in_place.add(kw)
            if item["rank_no"] is not None:
                kw_ranks[kw].append(item["rank_no"])

    # 경쟁업체 전체 키워드 집합
    all_competitor_kwd: set[str] = set(kw_freq.keys())

    # ── 3. 내 순위 데이터 조회 ────────────────────────────────────────────────
    my_rankings = get_place_rankings(place_id)
    my_rank_map: dict[str, int] = {
        r["keyword"]: r["rank_no"]
        for r in my_rankings
        if r["rank_no"] is not None
    }

    # 검색량 조회 대상: gap + rank_gap + advantage 후보 전체
    search_volume_targets = (
        (all_competitor_kwd - my_keywords)       # gap 후보
        | (my_keywords & all_competitor_kwd)     # rank_gap 후보
        | (my_keywords - all_competitor_kwd)     # advantage 후보
    )
    volumes = get_keyword_monthly_search(list(search_volume_targets))

    # ── 4. gap_keywords 산출 ─────────────────────────────────────────────────
    # 조건: MIN_COMPETITOR_COUNT개 이상 경쟁업체 등장 + 내 키워드에 없음
    gap_raw = []
    for kw, cnt in kw_freq.items():
        if kw in my_keywords or cnt < MIN_COMPETITOR_COUNT:
            continue
        vol        = volumes.get(kw, 0)
        max_vol    = max(volumes.values(), default=1) or 1
        freq_score = cnt / n_competitors
        vol_score  = vol / max_vol
        gap_raw.append({
            "keyword":               kw,
            "score":                 vol_score * 0.7 + freq_score * 0.3,
            "source":                "competitor",
            "category":              _get_category(kw),
            "competitor_count":      cnt,
            "monthly_search_volume": vol,
        })

    gap_keywords = _normalize_scores(
        sorted(gap_raw, key=lambda x: -x["score"])
    )

    # ── 5. rank_gap_keywords 산출 ────────────────────────────────────────────
    # 조건: 나도 있고 경쟁업체도 있는데, 경쟁업체 평균 순위 < 내 순위
    #       (숫자가 작을수록 높은 순위 — 1위가 최상위)
    # null 처리: 크롤러가 70위까지만 추적하므로 null = RANK_UNTRACKED(71)로 처리
    #            "경쟁업체 5위, 나는 70위 초과"인 경우를 rank_gap에 포함
    rank_gap_raw = []
    for kw in my_keywords & all_competitor_kwd:
        my_rank = my_rank_map.get(kw, RANK_UNTRACKED)   # null → 71위로 처리
        comp_ranks = kw_ranks.get(kw, [])
        if not comp_ranks:
            continue

        comp_avg = sum(comp_ranks) / len(comp_ranks)
        gap      = my_rank - comp_avg          # 양수 = 내 순위가 낮음(불리)
        if gap <= 0:
            continue                           # 내가 이미 유리하면 제외

        # 점수: 순위 격차 70% + 검색량 30%
        vol       = volumes.get(kw, 0)
        max_vol   = max(volumes.values(), default=1) or 1
        gap_score = min(gap / 50, 1.0)        # 최대 50위 차이를 1.0으로 정규화
        vol_score = vol / max_vol
        rank_gap_raw.append({
            "keyword":               kw,
            "score":                 gap_score * 0.7 + vol_score * 0.3,
            "source":                "competitor",
            "category":              _get_category(kw),
            "my_rank_no":            my_rank_map.get(kw),   # 원본 유지 (null = 70위 초과)
            "competitor_avg_rank":   round(comp_avg, 1),
            "rank_gap":              round(gap, 1),
            "monthly_search_volume": vol,
        })

    rank_gap_keywords = _normalize_scores(
        sorted(rank_gap_raw, key=lambda x: -x["score"])
    )

    # ── 6. advantage_keywords 산출 (프론트 전용) ─────────────────────────────
    # 내 키워드에는 있고 경쟁업체 전체에 없는 것
    advantage_set = my_keywords - all_competitor_kwd
    advantage_keywords = [
        {"keyword": kw, "monthly_search_volume": volumes.get(kw, 0)}
        for kw in sorted(advantage_set)
    ]

    # ── 7. category_gap 산출 (프론트 전용) ───────────────────────────────────
    # 경쟁업체 키워드 카테고리 분포 vs 내 키워드 카테고리 분포 비교
    TRACKED_CATEGORIES = {"음식", "장소", "서비스", "분위기"}

    # 내 키워드 카테고리별 개수
    my_cat_count: Counter = Counter()
    for kw in my_keywords:
        cat = _get_category(kw)
        if cat in TRACKED_CATEGORIES:
            my_cat_count[cat] += 1

    # 경쟁업체 키워드 카테고리 누적 (업체별 집합으로 중복 방지)
    comp_cat_total: Counter = Counter()
    for kws in competitor_kw_map.values():
        seen_cats: set[str] = set()
        for item in kws:
            cat = _get_category(item["keyword"])
            if cat in TRACKED_CATEGORIES and cat not in seen_cats:
                comp_cat_total[cat] += 1
                seen_cats.add(cat)

    category_gap: dict[str, dict] = {}
    for cat in TRACKED_CATEGORIES:
        comp_avg = round(comp_cat_total[cat] / n_competitors, 1)
        category_gap[cat] = {
            "mine":           my_cat_count[cat],
            "competitor_avg": comp_avg,
        }

    return {
        "gap_keywords":      gap_keywords,
        "rank_gap_keywords": rank_gap_keywords,
        "advantage_keywords":advantage_keywords,
        "category_gap":      category_gap,
        "competitor_count":  n_competitors,
        "competitor_names":  list(name_map.values()),
    }
