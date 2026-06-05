# 모듈1 · 지역+업종 기반 기본 키워드 생성
#
# cold_start 사용자(리뷰 ≤ 5개)의 핵심 데이터 소스.
# Round 1: 검색량 없이 후보 목록만 생성 → Spring 전달
# Round 2: Spring이 크롤링한 검색량으로 점수 계산 + BASE_SCORE_THRESHOLD 미만 탈락
# 조합: 동/구 + term/맛집/상황어, 역/랜드마크 + term/맛집, keyword_related 연관검색어
#
# 파이프라인: STAGE 0(place_info) → [모듈1] → keyword_blender

from app.core.config import (
    RELATED_SCORE_CAP,
    RELATED_TOP_N,
    BASE_SCORE_THRESHOLD,
)
from app.data.landmark_dict import LOCATION_MAP
from app.db.repository import (
    get_keyword_monthly_search,
    get_related_keywords_for_place,
)

# ── 카테고리 파싱 상수 ────────────────────────────────────────────────────────
# 검색어로 쓰기 어색한 접미사 — 단일/복합 term 모두 strip 적용
# 예: "고기요리" → "고기" / "돼지고기구이" → "돼지고기" / "중식당" → "중식"
CATEGORY_STRIP_SUFFIXES = ["요리", "구이", "당"]

# 지역 기반 상황별 검색어 조합용
SITUATION_WORDS = ["데이트", "혼밥", "회식"]


def _parse_category_terms(category: str) -> list[str]:
    """
    category 문자열을 파싱해 검색 친화적 term 목록 반환.

    대분류/소분류 패턴 판별:
    - split 후 소분류 term 중 CATEGORY_STRIP_SUFFIXES 접미사가 있으면
      대분류/소분류 구조로 간주 → 첫 term(대분류) 제거 + 접미사 strip
    - 없으면 동등한 항목들로 간주 → 전부 사용 (예: 곱창,막창,양)

    Examples
    --------
    "육류,고기요리"  → ["고기"]
    "카페,디저트"    → ["카페", "디저트"]  (접미사 없음 → 전부 사용)
    "곱창,막창,양"  → ["곱창", "막창", "양"]
    "파스타"         → ["파스타"]
    """
    def _strip(term: str) -> str:
        """접미사 제거. 결과가 빈 문자열이면 원본 반환."""
        for suffix in CATEGORY_STRIP_SUFFIXES:
            if term.endswith(suffix) and len(term) > len(suffix):
                return term[:-len(suffix)]
        return term

    terms = [t.strip() for t in category.split(",") if t.strip()]

    if len(terms) == 1:
        return [_strip(terms[0])]

    sub_terms = terms[1:]
    has_suffix = any(
        any(t.endswith(s) for s in CATEGORY_STRIP_SUFFIXES)
        for t in sub_terms
    )

    if has_suffix:
        return [_strip(t) for t in sub_terms]   # 대분류 제거 + 접미사 strip
    else:
        return [_strip(t) for t in terms]        # 동등한 항목 → 전부 사용


def _build_candidates(
    terms:        list[str],
    neighborhood: str,
    city:         str,
    locations:    list[dict],
) -> list[str]:
    """term + 지역 정보 조합으로 후보 키워드 리스트 생성 (중복 제거)."""
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(kw: str) -> None:
        if kw not in seen:
            candidates.append(kw)
            seen.add(kw)

    for term in terms:
        if neighborhood:
            _add(f"{neighborhood} {term}")
        if city:
            _add(f"{city} {term}")

        _add(f"{term} 맛집")
        if neighborhood:
            _add(f"{neighborhood} {term} 맛집")
        if city:
            _add(f"{city} {term} 맛집")

        for situation in SITUATION_WORDS:
            if neighborhood:
                _add(f"{neighborhood} {term} {situation}")
            if city:
                _add(f"{city} {term} {situation}")

        for loc in locations:
            name = loc["name"]
            loc_type = loc["type"]
            if loc_type == "station":
                _add(f"{name} {term}")
                _add(f"{name} 맛집")
                _add(f"{name} 근처 맛집")
                _add(f"{name} 근처 {term}")
            elif loc_type == "landmark":
                _add(f"{name} {term}")
                _add(f"{name} 맛집")

    if neighborhood:
        _add(f"{neighborhood} 맛집")
    if city:
        _add(f"{city} 맛집")

    for situation in SITUATION_WORDS:
        if neighborhood:
            _add(f"{neighborhood} {situation}")
        if city:
            _add(f"{city} {situation}")

    return candidates


def generate_base_keywords(
    place_info: dict,
    place_id:   int | None = None,
    round_no:   int = 1,
) -> list[dict]:
    """
    지역+업종 조합 기반 기본 키워드를 생성한다.

    Parameters
    ----------
    place_info : dict
        get_place_info() 반환값
        {"name": str, "category": str, "neighborhood": str, "city": str}
    place_id : int | None
        keyword_related 조회용. None이면 연관검색어 통합 스킵.
    round_no : int
        1 → 후보 생성만 (검색량 없이 score=None)
        2 → 검색량 기반 점수 계산 + 필터링 적용

    Returns
    -------
    list[dict]  score 내림차순 정렬
        Round 1: [{"keyword": str, "score": None, "source": "base",
                   "monthly_search_volume": 0}, ...]
        Round 2: 검색량 없거나 threshold 미만 탈락 후
                 [{"keyword": str, "score": float, "source": "base",
                   "monthly_search_volume": int}, ...]
    """
    if not place_info:
        return []

    category     = (place_info.get("category") or "").strip()
    neighborhood = (place_info.get("neighborhood") or "").strip()
    city_raw     = (place_info.get("city") or "").strip()           # 예: "강남" (접미사 제거된 값)
    city_full    = f"{city_raw}구" if city_raw and not city_raw.endswith("구") else city_raw

    if not category:
        return []

    terms      = _parse_category_terms(category)
    locations  = LOCATION_MAP.get(city_full, [])
    candidates = _build_candidates(terms, neighborhood, city_raw, locations)

    related_keywords: list[dict] = []
    if place_id:
        related_keywords = get_related_keywords_for_place(
            place_id=place_id,
            city=city_raw,
            neighborhood=neighborhood,
            top_n=RELATED_TOP_N,
        )

    if round_no == 1:
        result = [
            {
                "keyword":               kw,
                "score":                 None,
                "source":                "base",
                "monthly_search_volume": 0,
            }
            for kw in candidates
        ]
        for item in related_keywords:
            result.append({
                "keyword":               item["keyword"],
                "score":                 None,
                "source":                "base_related",
                "monthly_search_volume": item["monthly_search_volume"],
                "competitive_level":     item.get("competitive_level", "낮음"),
            })
        return result

    volumes: dict[str, int] = get_keyword_monthly_search(candidates)

    valid = [
        (kw, volumes[kw])
        for kw in candidates
        if volumes.get(kw, 0) > 0
    ]

    if not valid:
        # 연관검색어만이라도 반환
        return _score_related(related_keywords)

    max_vol = max(vol for _, vol in valid)

    base_result = []
    for kw, vol in valid:
        score = round(vol / max_vol, 4)
        if score < BASE_SCORE_THRESHOLD:
            continue
        base_result.append({
            "keyword":               kw,
            "score":                 score,
            "source":                "base",
            "monthly_search_volume": vol,
        })

    related_result = _score_related(related_keywords)

    return sorted(base_result + related_result, key=lambda x: -x["score"])


def _score_related(related_keywords: list[dict]) -> list[dict]:
    """검색량 정규화 후 RELATED_SCORE_CAP 상한을 적용해 점수 부여."""
    if not related_keywords:
        return []

    max_vol = max(item["monthly_search_volume"] for item in related_keywords)
    if max_vol == 0:
        return []

    result = []
    for item in related_keywords:
        score = round((item["monthly_search_volume"] / max_vol) * RELATED_SCORE_CAP, 4)
        result.append({
            "keyword":               item["keyword"],
            "score":                 score,
            "source":                "base_related",
            "monthly_search_volume": item["monthly_search_volume"],
            "competitive_level":     item.get("competitive_level", "낮음"),
        })
    return result
