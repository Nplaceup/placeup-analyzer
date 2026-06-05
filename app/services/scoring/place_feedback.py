from app.services.nlp.sentiment import SentimentAnalyzer

class PlaceFeedback:
    """
    플레이스 운영 개선 피드백 생성기

    피드백 소스
    ─────────────────────────────────────
    ① 매장 정보 완성도 기반   places 테이블 데이터
    ② 리뷰 내용 기반          place_reviews 원본 텍스트
    ③ 경쟁업체 분석 기반      competitor_analyzer 결과
    ─────────────────────────────────────
    출력: 총평 1개 + 매장 정보 기반 최대 3개 + 리뷰 기반 최대 3개 + 경쟁업체 기반 최대 3개
    """

    REVIEW_KEYWORD_THRESHOLD = 0.2

    def __init__(self):
        self._sentiment = SentimentAnalyzer()  # 한 번만 생성

    def generate(
        self,
        place_score_result: dict,
        reviews:            list[dict],
        competitor_result:  dict = None,
    ) -> dict:
        b = place_score_result["breakdown"]

        summary               = self._make_summary(place_score_result)
        completeness_feedback = self._completeness_based_feedback(b)
        review_feedback       = self._review_based_feedback(reviews)
        competitor_feedback   = self._competitor_based_feedback(competitor_result or {})

        return {
            "summary":             summary,
            "seo_feedback":        completeness_feedback[:3],
            "review_feedback":     review_feedback[:3],
            "competitor_feedback": competitor_feedback[:3],
        }

    # ── 총평 ──────────────────────────────────────────────────────────────
    def _make_summary(self, place_score_result: dict) -> str:
        total = place_score_result["total"]
        grade = place_score_result["grade"]

        if total >= 80:
            return f"플레이스가 잘 관리되고 있어요! ({total}점 {grade}) 현재 상태를 유지하면서 추천 키워드를 소개글에 활용해보세요."
        elif total >= 60:
            return f"플레이스 관리 상태가 보통이에요. ({total}점 {grade}) 몇 가지 항목을 개선하면 더 많은 고객에게 노출될 수 있어요."
        elif total >= 40:
            return f"플레이스 관리가 미흡해요. ({total}점 {grade}) 아래 개선사항을 참고해서 플레이스를 보완해보세요."
        else:
            return f"플레이스 관리가 취약해요. ({total}점 {grade}) 기본적인 매장 정보 등록부터 시작해보세요."

    # ── ① 매장 정보 완성도 기반 피드백 ───────────────────────────────────
    def _completeness_based_feedback(self, breakdown: dict) -> list[str]:
        feedbacks = []

        place_completeness = breakdown.get("place_completeness", 0)

        if place_completeness < 15:
            feedbacks.append("소개글이 없어요. 매장 소개글을 작성하면 고객에게 더 잘 노출될 수 있어요.")

        if place_completeness < 30:
            feedbacks.append("메뉴 정보가 부족해요. 메뉴판을 등록하면 고객 유입에 도움이 돼요.")

        if place_completeness < 40:
            feedbacks.append("사진이 부족해요. 매장 사진을 추가하면 고객의 관심을 높일 수 있어요.")

        if breakdown.get("review_quality", 0) < 30:
            feedbacks.append("리뷰 품질 점수가 낮아요. 리뷰 이벤트를 진행하거나 방문 고객에게 리뷰 작성을 유도해보세요.")

        return feedbacks

    # ── ② 리뷰 내용 기반 피드백 ───────────────────────────────────────────
    def _review_based_feedback(self, reviews: list[dict]) -> list[str]:
        feedbacks = []
        total = len(reviews)

        if total == 0:
            return ["리뷰 데이터가 없어요. 리뷰 이벤트를 진행해보세요."]

        if total < 10:
            feedbacks.append("리뷰가 부족해요. 리뷰 이벤트나 방문 고객에게 리뷰 작성을 유도해보세요.")

        def keyword_ratio(keywords: list[str]) -> float:
            """
            키워드 포함 문장만 감성 분석 → 부정(-0.3 미만)인 리뷰 비율 반환.
            키워드가 아예 없는 리뷰는 카운트에서 제외.
            """
            negative_count = 0
            for r in reviews:
                content = r["content"]
                if not any(kw in content for kw in keywords):
                    continue
                score = self._sentiment.analyze_review(content, target_keywords=keywords)
                if score < -0.3:
                    negative_count += 1
            return negative_count / total

        if keyword_ratio(["주차"]) >= self.REVIEW_KEYWORD_THRESHOLD:
            feedbacks.append("주차 관련 언급이 많아요. 주차 안내 정보를 플레이스에 추가해보세요.")

        if keyword_ratio(["웨이팅", "대기"]) >= self.REVIEW_KEYWORD_THRESHOLD:
            feedbacks.append("대기 관련 언급이 많아요. 웨이팅 안내 문구나 예약 시스템 도입을 고려해보세요.")

        if keyword_ratio(["비싸", "가격", "값"]) >= self.REVIEW_KEYWORD_THRESHOLD:
            feedbacks.append("가격 관련 언급이 많아요. 가성비를 강조하는 키워드나 세트 메뉴 홍보를 고려해보세요.")

        if keyword_ratio(["불친절", "불편", "실망"]) >= self.REVIEW_KEYWORD_THRESHOLD:
            feedbacks.append("서비스 관련 부정적 리뷰가 있어요. 서비스 품질 개선이 필요할 수 있어요.")

        if not feedbacks:
            feedbacks.append("리뷰에서 특별한 개선 사항이 발견되지 않았어요. 현재 상태를 유지해보세요.")

        return feedbacks

    # ── ③ 경쟁업체 분석 기반 피드백 ──────────────────────────────────────
    def _competitor_based_feedback(self, competitor_result: dict) -> list[str]:
        feedbacks = []

        advantage_keywords = competitor_result.get("advantage_keywords", [])
        category_gap       = competitor_result.get("category_gap", {})

        if advantage_keywords:
            top3 = ", ".join(advantage_keywords[:3])
            feedbacks.append(f"리뷰에서 자주 언급된 강점 키워드예요. ({top3}) 소개글과 메뉴 설명, 리뷰에 적극 활용해보세요.")

        for cat, v in category_gap.items():
            if v["competitor_avg"] > 0 and v["mine"] < v["competitor_avg"]:
                feedbacks.append(
                    f"'{cat}' 관련 키워드가 경쟁업체 대비 부족해요. "
                    f"(내 매장 {v['mine']}개 vs 경쟁업체 평균 {v['competitor_avg']}개) "
                    f"관련 키워드를 보완해보세요."
                )

        if not feedbacks:
            if competitor_result.get("competitor_count", 0) == 0:
                feedbacks.append("아직 비교할 경쟁업체 데이터가 없어요. 더 많은 데이터가 쌓이면 경쟁 분석이 제공될 예정이에요.")
            else:
                feedbacks.append("경쟁업체 대비 뚜렷한 개선 사항이 없어요. 현재 키워드 전략을 유지해보세요.")

        return feedbacks