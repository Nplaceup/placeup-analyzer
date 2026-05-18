class SEOFeedback:
    """
    SEO 피드백 생성기

    피드백 소스
    ─────────────────────────────────────
    ① SEO Score 기반   recommend_keywords 데이터
    ② 리뷰 내용 기반   place_reviews 원본 텍스트 (body 컬럼)
    ─────────────────────────────────────
    출력: 총평 1개 + SEO 기반 최대 3개 + 리뷰 기반 최대 3개 = 총 최대 7개
    """

    # 리뷰 키워드 등장 비율 기준 (전체 리뷰의 5% 이상이면 "자주 등장"으로 판단)
    REVIEW_KEYWORD_THRESHOLD = 0.05

    def generate(self, seo_result: dict, reviews: list[dict]) -> dict:
        """
        SEO 피드백 생성

        Parameters
        ----------
        seo_result : SEOScorer.calc_score() 반환값
            {
                "total": int,
                "grade": str,
                "breakdown": {
                    "keyword_optimization": float,
                    "keyword_optimization_detail": {
                        "search_ratio": float,      # 검색용 키워드 비율 점수
                        "diversity": float          # 카테고리 다양성 점수
                    },
                    "review_quality": float,
                    "search_exposure": float,
                    "competition": float
                }
            }
        reviews : place_reviews 테이블 결과 (list[dict])
            [{"id": int, "body": str, ...}, ...]

        Returns
        -------
        {
            "summary":         str,         # 총평
            "seo_feedback":    list[str],   # SEO 기반 피드백 (최대 3개)
            "review_feedback": list[str]    # 리뷰 기반 피드백 (최대 3개)
        }
        """
        b = seo_result["breakdown"]

        summary         = self._make_summary(seo_result)
        seo_feedback    = self._seo_based_feedback(b)
        review_feedback = self._review_based_feedback(reviews)

        return {
            "summary":         summary,
            "seo_feedback":    seo_feedback[:3],
            "review_feedback": review_feedback[:3],
        }

    # ── 총평 ──────────────────────────────────────────────────────────────
    def _make_summary(self, seo_result: dict) -> str:
        total = seo_result["total"]
        grade = seo_result["grade"]

        if total >= 80:
            return f"현재 SEO 상태가 우수해요! ({total}점 {grade}) 지금의 키워드 전략을 유지하면서 기회 키워드를 적극 활용해보세요."
        elif total >= 60:
            return f"SEO 상태가 보통이에요. ({total}점 {grade}) 몇 가지 항목을 개선하면 검색 노출을 높일 수 있어요."
        elif total >= 40:
            return f"SEO 상태가 미흡해요. ({total}점 {grade}) 아래 개선사항을 참고해서 키워드 전략을 보완해보세요."
        else:
            return f"SEO 상태가 취약해요. ({total}점 {grade}) 기본적인 키워드 세팅부터 시작해보세요."

    # ── ① SEO Score 기반 피드백 ───────────────────────────────────────────
    def _seo_based_feedback(self, breakdown: dict) -> list[str]:
        feedbacks = []

        detail             = breakdown.get("keyword_optimization_detail", {})
        search_ratio_score = detail.get("search_ratio", breakdown["keyword_optimization"] / 2)
        diversity_score    = detail.get("diversity",    breakdown["keyword_optimization"] / 2)

        # 검색용 키워드 비율 낮음
        if search_ratio_score < 10:
            feedbacks.append("검색용 키워드 비율이 낮아요. 지역+업종 키워드(예: '강남 카페')를 추가해보세요.")

        # 카테고리 다양성 부족
        if diversity_score < 10:
            feedbacks.append("키워드 카테고리가 다양하지 않아요. 메뉴·분위기·서비스 등 다양한 카테고리 키워드를 추가해보세요.")

        # 리뷰 품질 낮음
        if breakdown["review_quality"] < 15:
            feedbacks.append("리뷰 품질 점수가 낮아요. 리뷰 이벤트를 진행하거나 방문 고객에게 리뷰 작성을 유도해보세요.")

        # 검색 노출 낮음
        if breakdown["search_exposure"] < 5:
            feedbacks.append("상위 노출 키워드가 부족해요. 경쟁도가 낮은 키워드를 집중 공략해보세요.")

        # 기회 키워드 존재
        if breakdown.get("has_opportunity"):
            feedbacks.append("기회 키워드가 있어요! 해당 키워드를 소개글과 리뷰에 적극 활용해보세요.")

        # 경쟁도 낮은 키워드 부족
        if breakdown["competition"] < 5:
            feedbacks.append("경쟁도가 낮은 키워드가 부족해요. 틈새 키워드를 발굴해서 현실적으로 이길 수 있는 싸움을 해보세요.")

        return feedbacks

    # ── ② 리뷰 내용 기반 피드백 ───────────────────────────────────────────
    def _review_based_feedback(self, reviews: list[dict]) -> list[str]:
        feedbacks = []
        total = len(reviews)

        if total == 0:
            return ["리뷰 데이터가 없어요. 리뷰 이벤트를 진행해보세요."]

        # 리뷰 수 부족
        if total < 10:
            feedbacks.append("리뷰가 부족해요. 리뷰 이벤트나 방문 고객에게 리뷰 작성을 유도해보세요.")

        # NOTE: 현재 단순 키워드 등장 횟수 기반으로 판단
        # 감성 분석 미연동 상태라 긍정 리뷰도 카운트될 수 있음
        # TODO: Phase 2 감성 분석 연동 후 부정 리뷰만 필터링하도록 교체 예정
        def keyword_ratio(keywords: list[str]) -> float:
            count = sum(
                1 for r in reviews
                if any(kw in r["body"] for kw in keywords)
            )
            return count / total

        # 주차 관련
        if keyword_ratio(["주차"]) >= self.REVIEW_KEYWORD_THRESHOLD:
            feedbacks.append("주차 관련 언급이 많아요. 주차 안내 정보를 플레이스에 추가해보세요.")

        # 웨이팅 관련
        if keyword_ratio(["웨이팅", "대기"]) >= self.REVIEW_KEYWORD_THRESHOLD:
            feedbacks.append("대기 관련 언급이 많아요. 웨이팅 안내 문구나 예약 시스템 도입을 고려해보세요.")

        # 가격 관련
        if keyword_ratio(["비싸", "가격", "값"]) >= self.REVIEW_KEYWORD_THRESHOLD:
            feedbacks.append("가격 관련 언급이 많아요. 가성비를 강조하는 키워드나 세트 메뉴 홍보를 고려해보세요.")

        # 서비스 관련
        if keyword_ratio(["불친절", "불편", "실망"]) >= self.REVIEW_KEYWORD_THRESHOLD:
            feedbacks.append("서비스 관련 부정적 리뷰가 있어요. 서비스 품질 개선이 필요할 수 있어요.")

        return feedbacks