# 모듈1 · 지역+업종 기반 기본 키워드 생성
#
# ─ 역할 ──────────────────────────────────────────────────────────────────────
# place_info(category, neighborhood, city)를 조합해
# 기본 키워드 후보 목록을 생성한다.
#
# 리뷰 데이터 없이도 키워드를 제공할 수 있어
# cold_start 사용자(리뷰 ≤ 5개)의 핵심 데이터 소스가 된다.
#
# ─ Round 구조 ────────────────────────────────────────────────────────────────
# Round 1: 검색량 없이 후보 키워드 문자열 목록만 생성 → Spring 전달
# Round 2: Spring이 크롤링한 검색량 데이터로 점수 계산 + 필터링
#          - 검색량 없는 키워드 탈락
#          - BASE_SCORE_THRESHOLD 미만 점수 탈락
#
# ─ 조합 규칙 ─────────────────────────────────────────────────────────────────
# [지역 + 업종]
#   {동} {term} / {구} {term}
# [지역 + 맛집]
#   {동} 맛집 / {구} 맛집 / {term} 맛집
#   {동} {term} 맛집 / {구} {term} 맛집
# [지역 + 상황어]
#   {동/구} 데이트 / {동/구} 혼밥 / {동/구} 회식
#   {동/구} {term} 데이트 / {동/구} {term} 혼밥 / {동/구} {term} 회식
# [역 (station)]
#   {역} {term} / {역} 맛집 / {역} 근처 맛집 / {역} 근처 {term}
# [랜드마크 (landmark)]
#   {랜드마크} {term} / {랜드마크} 맛집
# [연관검색어 (keyword_related)]
#   rankings 기반 연관검색어 중 위치 필터 + 검색량 top 10
#
# ─ 파이프라인 위치 ───────────────────────────────────────────────────────────
# STAGE 0 (place_info 조회) → [모듈1] → keyword_blender

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
CATEGORY_STRIP_SUFFIXES = ["요리"]

# ── 상황어 목록 (유도어 폐기 후 보완 ──────────────────────────────────────────────
SITUATION_WORDS = ["데이트", "혼밥", "회식"]


# ── 카테고리 파싱 ─────────────────────────────────────────────────────────────
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
    terms = [t.strip() for t in category.split(",") if t.strip()]
    if len(terms) <= 1:
        return terms

    sub_terms = terms[1:]
    has_suffix = any(
        any(t.endswith(s) for s in CATEGORY_STRIP_SUFFIXES)
        for t in sub_terms
    )

    if has_suffix:
        # 대분류 제거 + 접미사 strip
        result = []
        for term in sub_terms:
            for suffix in CATEGORY_STRIP_SUFFIXES:
                if term.endswith(suffix) and len(term) > len(suffix):
                    term = term[:-len(suffix)]
                    break
            result.append(term)
        return result
    else:
        # 동등한 항목 → 전부 사용
        return terms


# ── 후보 키워드 조합 생성 ─────────────────────────────────────────────────────
def _build_candidates(
    terms:        list[str],
    neighborhood: str,
    city:         str,
    locations:    list[dict],   # LOCATION_MAP에서 조회한 역/랜드마크 목록
) -> list[str]:
    """
    term 목록 + 지역 정보를 조합해 후보 키워드 문자열 리스트 반환.
    중복 제거 후 반환.
    """
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(kw: str) -> None:
        if kw not in seen:
            candidates.append(kw)
            seen.add(kw)

    for term in terms:
        # [지역 + 업종]
        if neighborhood:
            _add(f"{neighborhood} {term}")
        if city:
            _add(f"{city} {term}")

        # [지역 + 맛집]
        _add(f"{term} 맛집")
        if neighborhood:
            _add(f"{neighborhood} {term} 맛집")
        if city:
            _add(f"{city} {term} 맛집")

        # [지역 + 상황어]
        for situation in SITUATION_WORDS:
            if neighborhood:
                _add(f"{neighborhood} {term} {situation}")
            if city:
                _add(f"{city} {term} {situation}")

        # [역/랜드마크]
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

    # [지역 + 맛집] (term 무관)
    if neighborhood:
        _add(f"{neighborhood} 맛집")
    if city:
        _add(f"{city} 맛집")

    # [지역 + 상황어] (term 무관)
    for situation in SITUATION_WORDS:
        if neighborhood:
            _add(f"{neighborhood} {situation}")
        if city:
            _add(f"{city} {situation}")

    return candidates


# ── 메인 함수 ─────────────────────────────────────────────────────────────────
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

    # ── 1. category 파싱 ──────────────────────────────────────────────────────
    terms = _parse_category_terms(category)

    # ── 2. 역/랜드마크 조회 (구 단위) ─────────────────────────────────────────
    locations = LOCATION_MAP.get(city_full, [])

    # ── 3. 패턴 조합 후보 생성 ────────────────────────────────────────────────
    candidates = _build_candidates(terms, neighborhood, city_raw, locations)

    # ── 4. keyword_related 연관검색어 통합 ────────────────────────────────────
    related_keywords: list[dict] = []
    if place_id:
        related_keywords = get_related_keywords_for_place(
            place_id=place_id,
            city=city_raw,
            neighborhood=neighborhood,
            top_n=RELATED_TOP_N,
        )

    # ── 5. Round 1: 점수 없이 후보 리스트만 반환 ──────────────────────────────
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

    # ── 6. Round 2: 검색량 조회 + 점수 계산 + 필터링 ─────────────────────────
    volumes: dict[str, int] = get_keyword_monthly_search(candidates)

    # 검색량 없는 후보 탈락
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

    # 연관검색어 점수 계산 (RELATED_SCORE_CAP 적용)
    related_result = _score_related(related_keywords)

    return sorted(base_result + related_result, key=lambda x: -x["score"])


def _score_related(related_keywords: list[dict]) -> list[dict]:
    """
    keyword_related 항목에 RELATED_SCORE_CAP 기반 점수 부여.
    검색량 정규화 후 RELATED_SCORE_CAP을 곱해 점수 상한 적용.
    """
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
