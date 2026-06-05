# 유도어 사전 — STAGE 3.5 (NLP 키워드 검색형 확장) 전용
#
# ─ 역할 ──────────────────────────────────────────────────────────────────────
# purpose = "search" 키워드에 결합할 유도어 목록을 카테고리별로 관리.
# purpose 결정 자체는 CategoryMapper(category_mapper.py)에서 담당.
# 이 파일은 "어떤 유도어를 붙일 것인가"만 정의.
#
# ─ 현재 search 대상 ───────────────────────────────────────────────────────────
# 음식 카테고리(메뉴명)만 search — 나머지는 CategoryMapper에서 marketing 처리
#
# ─ 사용 위치 ─────────────────────────────────────────────────────────────────
# keyword_formatter.py → expand_nlp_keywords()


INDUCEMENT_BY_CATEGORY: dict[str, list[str]] = {
    "음식": ["맛집", "추천"],
}


def get_inducements(category: str, prop: str = "") -> list[str]:
    """카테고리 기반으로 유도어 목록 반환."""
    return INDUCEMENT_BY_CATEGORY.get(category, [])
