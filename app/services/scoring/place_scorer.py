class PlaceScorer:
    """
    매장 단위 플레이스 관리 점수 계산기 (0~100점)

    점수 구성
    ─────────────────────────────────────
    ① 매장 정보 완성도   40점  소개글/사진/메뉴 등록 여부
    ② 리뷰 품질         60점  리뷰 수 + 평균 점수 + 일관성
    ─────────────────────────────────────
    입력:
      - keywords    : recommend_keywords 테이블 결과 (list[dict])
      - place_info  : places 테이블 결과 (dict)
      - review_count: 리뷰 수 (int)
    출력: {"total": int, "breakdown": dict, "grade": str}
    """

    def calc_score(
        self,
        keywords:     list[dict],
        place_info:   dict,
        review_count: int,
    ) -> dict:

        s1 = self._place_completeness(place_info)
        s2 = self._review_quality(keywords, review_count)

        final = round(s1 + s2)

        return {
            "total": final,
            "grade": self._grade(final),
            "breakdown": {
                "place_completeness": round(s1, 2),
                "review_quality":     round(s2, 2),
            }
        }

    # ① 매장 정보 완성도 (40점)
    def _place_completeness(self, place_info: dict) -> float:
        """
        소개글 (15점) + 메뉴 (15점) + 사진 (10점)
        ※ 크롤링 데이터 들어오기 전까지 임시값 사용
        """
        score = 0.0

        # 소개글 여부 (15점)
        description = place_info.get("description")
        if description:
            score += 15.0

        # 메뉴 여부 (15점)
        menu_list = place_info.get("menu_list")
        if menu_list:
            score += 15.0

        # 사진 리뷰 수 (10점) — 10개 이상이면 만점
        image_review_count = place_info.get("image_review_count", 0) or 0
        score += min(image_review_count / 10, 1.0) * 10

        return score

    # ② 리뷰 품질 (60점)
    def _review_quality(self, keywords: list[dict], review_count: int) -> float:
        """
        리뷰 수 (20점) + 평균 키워드 점수 (20점) + 평균 일관성 (20점)
        """
        # 리뷰 수 (20점) — 100개 이상이면 만점
        review_score = min(review_count / 100, 1.0) * 20

        if not keywords:
            return review_score

        total = len(keywords)

        # 평균 키워드 점수 (20점)
        avg_score = sum(k.get("score", 0.0) for k in keywords) / total
        keyword_score = avg_score * 20

        # 평균 일관성 점수 (20점)
        avg_consistency = sum(k.get("consistency_score", 0.0) for k in keywords) / total
        consistency_score = avg_consistency * 20

        return review_score + keyword_score + consistency_score

    # 등급 판정
    def _grade(self, score: int) -> str:
        if score >= 80:
            return "🟢 우수"
        elif score >= 60:
            return "🟡 보통"
        elif score >= 40:
            return "🟠 미흡"
        else:
            return "🔴 취약"

    def _empty_result(self) -> dict:
        return {
            "total": 0,
            "grade": "🔴 취약",
            "breakdown": {
                "place_completeness": 0,
                "review_quality":     0,
            }
        }