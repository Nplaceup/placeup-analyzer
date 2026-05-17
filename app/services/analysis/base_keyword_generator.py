# 모듈1 · 지역+업종 기반 기본 키워드 생성
#
# ─ 역할 ──────────────────────────────────────────────────────────────────────
# place_info(category, neighborhood, city)를 조합해
# 기본 키워드 목록을 생성한다.
#
# 리뷰 데이터 없이도 키워드를 제공할 수 있어
# cold_start 사용자(리뷰 ≤ 5개)의 핵심 데이터 소스가 된다.
#
# ─ 조합 규칙 ─────────────────────────────────────────────────────────────────
# {neighborhood} {category}   예: "역삼 파스타"
# {city}         {category}   예: "강남 파스타"
# {neighborhood} 맛집         예: "역삼 맛집"
# {city}         맛집         예: "강남 맛집"
# {category}     {유도어}     예: "파스타 맛집"
#
# ─ 점수 ──────────────────────────────────────────────────────────────────────
# 검색량 있으면: 검색량 / 그룹 내 최대 검색량 → 0~1 정규화
# 검색량 없으면: 조합 규칙 우선순위 기반 fallback 점수 (0.2~0.6)
# 실제 검색 수요 검증은 NLP + STAGE 2.5 (CASE A/B/C) 에서 담당하므로
# 기본 키워드는 검색량 유무와 무관하게 항상 생성된다.
#
# ─ 파이프라인 위치 ───────────────────────────────────────────────────────────
# STAGE 0 (place_info 조회) → [모듈1] → keyword_blender

from app.db.repository import get_keyword_monthly_search

# 업종 키워드에 결합할 유도어 목록
# "맛집"은 지역 토큰과도 결합하므로 별도 처리
CATEGORY_SUFFIXES = ["맛집"]


def generate_base_keywords(place_info: dict) -> list[dict]:
    """
    지역+업종 조합 기반 기본 키워드를 생성한다.

    Parameters
    ----------
    place_info : dict
        get_place_info() 반환값
        {"name": str, "category": str, "neighborhood": str, "city": str}

    Returns
    -------
    list[dict]  점수 내림차순 정렬
        [
            {
                "keyword":               str,
                "score":                 float,  # 0~1 (검색량 정규화 or fallback)
                "source":                "base",
                "monthly_search_volume": int,    # 검색량 없으면 0
            },
            ...
        ]
    place_info가 None이거나 category가 없으면 빈 리스트 반환.
    """
    if not place_info:
        return []

    category     = (place_info.get("category") or "").strip()
    neighborhood = (place_info.get("neighborhood") or "").strip()
    city         = (place_info.get("city") or "").strip()

    if not category:
        return []

    # ── 1. 후보 키워드 + fallback 우선순위 점수 ───────────────────────────────
    # 검색량 데이터가 없을 때 사용하는 규칙 기반 점수
    # 지역이 구체적일수록, 업종 직결도가 높을수록 높은 점수
    candidates: list[tuple[str, float]] = []
    seen: set[str] = set()

    def _add(kw: str, fallback: float) -> None:
        if kw not in seen:
            candidates.append((kw, fallback))
            seen.add(kw)

    if neighborhood:
        _add(f"{neighborhood} {category}", 0.6)
        _add(f"{neighborhood} 맛집",       0.4)
    if city:
        _add(f"{city} {category}", 0.5)
        _add(f"{city} 맛집",       0.3)
    for suffix in CATEGORY_SUFFIXES:
        _add(f"{category} {suffix}", 0.2)

    if not candidates:
        return []

    # ── 2. 검색량 조회 ────────────────────────────────────────────────────────
    volumes: dict[str, int] = get_keyword_monthly_search([kw for kw, _ in candidates])

    # ── 3. 점수 결정: 검색량 있으면 정규화, 없으면 fallback ──────────────────
    vol_values = [volumes[kw] for kw, _ in candidates if volumes.get(kw, 0) > 0]
    max_vol    = max(vol_values) if vol_values else 0

    return sorted(
        [
            {
                "keyword":               kw,
                "score":                 round(volumes[kw] / max_vol, 4) if volumes.get(kw, 0) > 0 else fallback,
                "source":                "base",
                "monthly_search_volume": volumes.get(kw, 0),
            }
            for kw, fallback in candidates
        ],
        key=lambda x: -x["score"],
    )
