# "search" 키워드에 결합할 유도어 목록 (카테고리별).
# purpose 결정은 CategoryMapper 담당 — 이 파일은 "어떤 유도어를 붙일 것인가"만 정의.


INDUCEMENT_BY_CATEGORY: dict[str, list[str]] = {
    "음식": ["맛집", "추천"],
}


def get_inducements(category: str, prop: str = "") -> list[str]:
    """카테고리 기반으로 유도어 목록 반환."""
    return INDUCEMENT_BY_CATEGORY.get(category, [])
