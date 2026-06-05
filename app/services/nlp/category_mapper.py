# Layer 4 전용 — semantic_mapper 이후
# 역할: SemanticTag의 category/property 기반으로
#       keyword_purpose 결정 (search / marketing)

class CategoryMapper:

    PURPOSE_RULES: dict[tuple, str] = {

        # 음식
        ("음식", "메뉴명/육류"):    "search",
        ("음식", "메뉴명/해산물"):  "search",
        ("음식", "메뉴명/면류"):    "search",
        ("음식", "메뉴명/밥류"):    "search",
        ("음식", "메뉴명/국찌개"):  "search",
        ("음식", "메뉴명/음료"):    "search",
        ("음식", "메뉴명/디저트"):  "search",
        ("음식", "메뉴명/한식"):    "search",
        ("음식", "이용방식"):       "search",

        # 맛
        ("맛", "일반맛"):    "marketing",
        ("맛", "식감/풍미"): "marketing",
        ("맛", "온도"):      "marketing",
        ("맛", "양"):        "marketing",

        # 서비스
        ("서비스", "친절도"): "marketing",
        ("서비스", "속도"):   "marketing",
        ("서비스", "전문성"): "marketing",
        ("서비스", "편의"):   "marketing",
        ("서비스", "혼잡도"): "marketing",
        ("서비스", "가성비"): "marketing",

        # 분위기
        ("분위기", "감성"): "marketing",
        ("분위기", "뷰"):   "marketing",
        ("분위기", "소음"): "marketing",

        # 장소
        ("장소", "청결"):      "marketing",
        ("장소", "편의/주차"): "marketing",
        ("장소", "편의/시설"): "marketing",
        ("장소", "공간"):      "marketing",
        ("장소", "위치"):      "marketing",

        # 미분류
        ("미분류", "충성도"):   "marketing",
        ("미분류", "특별한날"): "marketing",
    }

    CATEGORY_DEFAULT: dict[str, str] = {
        "음식":   "search",
        "맛":     "marketing",
        "서비스": "marketing",
        "분위기": "marketing",
        "장소":   "marketing",
        "미분류": "marketing",
    }

    def assign_purpose(self, item: dict) -> dict:
        category = item.get("category", "미분류")
        prop     = item.get("property", "")

        purpose = self.PURPOSE_RULES.get((category, prop))
        if purpose is None:
            purpose = self.CATEGORY_DEFAULT.get(category, "marketing")

        return {**item, "keyword_purpose": purpose}

    def assign_batch(self, tagged_keywords: list[dict]) -> list[dict]:
        return [self.assign_purpose(item) for item in tagged_keywords]