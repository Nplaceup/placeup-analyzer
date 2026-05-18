from typing import Optional


class SEOScorer:
    """
    매장 단위 SEO 점수 계산기 (0~100점)

    점수 구성
    ─────────────────────────────────────
    ① 키워드 최적화     40점  검색용 키워드 비율 + 카테고리 다양성
    ② 리뷰 기반 품질    30점  평균 키워드 점수 + 일관성
    ③ 검색 노출 현황    20점  상위 노출 키워드 수 + 기회 키워드
    ④ 경쟁 포지셔닝     10점  경쟁도 낮은 키워드 비율
    ─────────────────────────────────────
    입력: recommend_keywords 테이블 결과 (list[dict])
    출력: {"total": int, "breakdown": dict, "grade": str}
    """

    def calc_score(self, keywords: list[dict]) -> dict:
        """
        매장 전체 SEO 점수 산출
        {
            "total":     int,        # 최종 점수 (0~100)
            "grade":     str,        # 🟢 우수 / 🟡 보통 / 🟠 미흡 / 🔴 취약
            "breakdown": {
                "keyword_optimization": float,   # ① 최대 40
                "review_quality":       float,   # ② 최대 30
                "search_exposure":      float,   # ③ 최대 20
                "competition":          float,   # ④ 최대 10
            }
        }
        """
        if not keywords:
            return self._empty_result()

        total = len(keywords)

        s1 = self._keyword_optimization(keywords, total)
        s2 = self._review_quality(keywords, total)
        s3 = self._search_exposure(keywords, total)
        s4 = self._competition(keywords, total)

        final = round(s1 + s2 + s3 + s4)

        return {
            "total": final,
            "grade": self._grade(final),
            "breakdown": {
                "keyword_optimization": round(s1, 2),
                "review_quality":       round(s2, 2),
                "search_exposure":      round(s3, 2),
                "competition":          round(s4, 2),
            }
        }


    # ① 키워드 최적화 (40점)
    def _keyword_optimization(self, keywords: list[dict], total: int) -> float:
        """
        검색용 키워드 비율 (20점) + 카테고리 다양성 (20점)
        """
        # 검색용 키워드 비율
        search_count = sum(1 for k in keywords if k.get("keyword_purpose") == "search")
        search_score = (search_count / total) * 20

        # 카테고리 다양성 (최대 5종류 기준)
        categories = set(k.get("category", "미분류") for k in keywords)
        diversity_score = min(len(categories) / 5, 1.0) * 20

        return search_score + diversity_score


    # ② 리뷰 기반 품질 (30점)
    def _review_quality(self, keywords: list[dict], total: int) -> float:
        """
        평균 키워드 점수 (20점) + 평균 일관성 점수 (10점)
        """
        avg_score = sum(k.get("score", 0.0) for k in keywords) / total
        avg_consistency = sum(k.get("consistency_score", 0.0) for k in keywords) / total

        return avg_score * 20 + avg_consistency * 10

    # ③ 검색 노출 현황 (20점)
    def _search_exposure(self, keywords: list[dict], total: int) -> float:
        """
        상위 10위 이내 키워드 수 (10점) + 기회 키워드 수 (10점)
        - 순위 데이터가 있는 키워드끼리만 비교
        - 순위 데이터 자체가 없으면 top_score 5점 (중간값) 부여
        """
        ranked = [k for k in keywords if k.get("rank_no") is not None]

        if not ranked:
            # 순위 데이터가 아예 없으면 중간값
            top_score = 5.0
        else:
            top_count = sum(1 for k in ranked if k["rank_no"] <= 10)
            # 순위 데이터 있는 것 중 30% 이상이 10위 이내면 만점
            top_score = min(top_count / max(len(ranked) * 0.3, 1), 1.0) * 10

        opportunity_count = sum(1 for k in keywords if k.get("is_opportunity"))
        opportunity_score = min(opportunity_count / 2, 1.0) * 10

        return top_score + opportunity_score

    # ④ 경쟁 포지셔닝 (10점)
    def _competition(self, keywords: list[dict], total: int) -> float:
        """
        경쟁도 낮은 키워드 비율 (10점)
        현실적으로 이길 수 있는 키워드를 보유하고 있는가
        """
        low_count = sum(1 for k in keywords if k.get("competition_level") == "낮음")
        return (low_count / total) * 10

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
                "keyword_optimization": 0,
                "review_quality":       0,
                "search_exposure":      0,
                "competition":          0,
            }
        }