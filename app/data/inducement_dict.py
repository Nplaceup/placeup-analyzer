# 유도어 사전 — STAGE 4 (유도어 결합) 전용
#
# ─ 역할 ──────────────────────────────────────────────────────────────────────
# purpose = "search" 키워드에 결합할 유도어 목록을 카테고리별로 관리.
# purpose 결정 자체는 CategoryMapper(category_mapper.py)에서 담당.
# 이 파일은 "어떤 유도어를 붙일 것인가"만 정의.
#
# ─ 사용 위치 ─────────────────────────────────────────────────────────────────
# keyword_formatter.py → attach_inducement()


INDUCEMENT_BY_CATEGORY: dict[str, list[str]] = {
    "음식": [
        "맛집", "추천", "가성비", "현지인맛집",
        "웨이팅", "후기좋은", "데이트", "혼밥",
    ],
    "장소": [
        "가볼만한곳", "추천", "핫플", "명소",
        "데이트", "놀거리",
    ],
    # 아래 카테고리는 purpose=search인 경우가 있으나
    # NO_INDUCEMENT_PROPERTY 로직으로 유도어 스킵됨 → 빈 리스트
    "맛":     [],
    "서비스": [],
    "분위기": [],
    "미분류": [],
}

# purpose=search이나 유도어 결합이 의미 없는 property 목록
# CategoryMapper 이후 이 목록에 해당하면 유도어 스킵
NO_INDUCEMENT_PROPERTY: set[str] = {
    "식감/풍미",  # "바삭 맛집" → 어색
    "온도",        # "뜨겁다 맛집" → 비문
    "양",          # "양많음 맛집" → 어색
    "친절도",      # "친절 맛집" → 어색
    "가성비",      # 이미 검색어 완결형
    "청결",        # "청결 맛집" → 어색
    "편의/주차",   # "주차 맛집" → 비문
    "위치",        # "역근처 맛집"은 이미 완결형
    "충성도",
    "특별한날",
}


def get_inducements(category: str, prop: str = "") -> list[str]:
    """
    카테고리 + property 기반으로 유도어 목록 반환.
    NO_INDUCEMENT_PROPERTY에 해당하면 빈 리스트 반환.
    """
    if prop in NO_INDUCEMENT_PROPERTY:
        return []
    return INDUCEMENT_BY_CATEGORY.get(category, [])
