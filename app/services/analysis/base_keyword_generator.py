# 모듈1 · 지역+업종 기반 기본 키워드 생성
#
# ─ 역할 ──────────────────────────────────────────────────────────────────────
# place_info(category, neighborhood, city)를 조합해
# 검색량 기반 기본 키워드 목록을 생성한다.
#
# 리뷰 데이터 없이도 키워드를 제공할 수 있어
# cold_start 사용자(리뷰 ≤ 5개)의 핵심 데이터 소스가 된다.
#
# ─ 조합 규칙 ─────────────────────────────────────────────────────────────────
# {neighborhood} {category}   예: "역삼 파스타"
# {city}         {category}   예: "강남 파스타"
# {neighborhood} 맛집         예: "역삼 맛집"
# {city}         맛집         예: "강남 맛집"
# {category}     {유도어}     예: "파스타 맛집", "파스타 추천", "파스타 맛있는곳"
#
# ─ 점수 ──────────────────────────────────────────────────────────────────────
# 검색량 / 그룹 내 최대 검색량 → 0~1 정규화
# (블렌더에서 nlp_keywords 점수와 동일 스케일로 합산하기 위함)
#
# ─ 파이프라인 위치 ───────────────────────────────────────────────────────────
# STAGE 0 (place_info 조회) → [모듈1] → keyword_blender

from app.db.repository import get_keyword_monthly_search

# 업종 키워드에 결합할 유도어 목록
# "맛집"은 지역 토큰과도 결합하므로 별도 처리
CATEGORY_SUFFIXES = ["맛집"]


def generate_base_keywords(place_info: dict) -> list[dict]:
    """
    지역+업종 조합 기반 기본 키워드를 생성하고 검색량 점수를 부여한다.

    Parameters
    ----------
    place_info : dict
        get_place_info() 반환값
        {"name": str, "category": str, "neighborhood": str, "city": str}

    Returns
    -------
    list[dict]  검색량 내림차순 정렬
        [
            {
                "keyword":               str,
                "score":                 float,  # 0~1 정규화 (검색량 기반)
                "source":                "base",
                "monthly_search_volume": int,
            },
            ...
        ]
    검색량 데이터가 없는 키워드는 제외.
    place_info가 None이거나 category가 없으면 빈 리스트 반환.
    """
    if not place_info:
        return []

    category     = (place_info.get("category") or "").strip()
    neighborhood = (place_info.get("neighborhood") or "").strip()
    city         = (place_info.get("city") or "").strip()

    if not category:
        return []

    # ── 1. 후보 키워드 조합 ────────────────────────────────────────────────
    candidates: set[str] = set()

    location_tokens = [t for t in [neighborhood, city] if t]

    for loc in location_tokens:
        candidates.add(f"{loc} {category}")   # "역삼 파스타"
        candidates.add(f"{loc} 맛집")         # "역삼 맛집"

    for suffix in CATEGORY_SUFFIXES:
        candidates.add(f"{category} {suffix}")  # "파스타 맛집", "파스타 추천" ...

    if not candidates:
        return []

    # ── 2. 검색량 조회 ────────────────────────────────────────────────────
    volumes: dict[str, int] = get_keyword_monthly_search(list(candidates))

    # ── 3. 검색량 없는 키워드 제거 ────────────────────────────────────────
    scored_raw = [
        (kw, volumes[kw])
        for kw in candidates
        if volumes.get(kw, 0) > 0
    ]

    if not scored_raw:
        return []

    # ── 4. 검색량 기반 0~1 정규화 점수 ───────────────────────────────────
    max_vol = max(vol for _, vol in scored_raw)

    return sorted(
        [
            {
                "keyword":               kw,
                "score":                 round(vol / max_vol, 4),
                "source":                "base",
                "monthly_search_volume": vol,
            }
            for kw, vol in scored_raw
        ],
        key=lambda x: -x["score"],
    )
