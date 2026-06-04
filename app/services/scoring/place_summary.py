class PlaceSummary:
    """
    플레이스 분석 요약 생성기

    recommend_keywords 테이블의 category 컬럼 기반으로
    카테고리별 대표 키워드를 묶어 요약 제공

    출력 예시:
    📊 플레이스 분석 요약
    🍖 메뉴/음식: 삼겹살, 냉삼, 차돌
    😋 맛: 육즙, 고소, 바삭
    🏠 분위기: 조용, 아늑
    👍 서비스: 친절, 빠름
    """

    CATEGORY_EMOJI = {
        "음식":  "🍖",
        "맛":   "😋",
        "분위기": "🏠",
        "서비스": "👍",
        "미분류": "📌",
    }

    # 카테고리별 최대 키워드 수
    MAX_KEYWORDS_PER_CATEGORY = 5

    def generate(self, keywords: list[dict]) -> dict:
        """
        카테고리별 대표 키워드 요약 생성

        Parameters
        ----------
        keywords : recommend_keywords 테이블 결과 (list[dict])
            score 내림차순 정렬 상태

        Returns
        -------
        {
            "summary": dict,   # {category: [keyword, ...]}
            "text":    str,    # 출력용 텍스트
        }
        """
        if not keywords:
            return {"summary": {}, "text": "분석된 키워드가 없어요."}

        # category별로 키워드 묶기 (score 높은 순, 유도어 제외)
        category_map: dict[str, list[str]] = {}

        for kw in keywords:
            category = kw.get("category", "미분류")
            keyword  = kw.get("keyword", "")

            # 유도어 결합형 제외 (is_induced=True)
            if kw.get("is_induced"):
                continue

            if category not in category_map:
                category_map[category] = []

            if len(category_map[category]) < self.MAX_KEYWORDS_PER_CATEGORY:
                category_map[category].append(keyword)

        # 텍스트 생성
        lines = ["📊 플레이스 분석 요약"]
        for category, kw_list in category_map.items():
            if not kw_list:
                continue
            emoji = self.CATEGORY_EMOJI.get(category, "📌")
            lines.append(f"{emoji} {category}: {', '.join(kw_list)}")

        return {
            "summary": category_map,
            "text":    "\n".join(lines),
        }