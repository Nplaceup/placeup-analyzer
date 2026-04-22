from datetime import datetime
from collections import Counter
from typing import Optional


class keywordScorer:
    """
    키워드 복합 점수 계산기.

    지표별 가중치
    ─────────────────────────────────────
    tfidf       40%  리뷰 내 중요도
    sentiment   25%  긍정/부정 감성 (Phase 2 연동 전 기본 1.0)
    recency     20%  최신 리뷰 언급 여부
    consistency 15%  여러 리뷰어 분산 언급 여부
    ─────────────────────────────────────
    """

    def __init__(self):
        self.weights = {
            "tfidf":       0.40,
            "sentiment":   0.25,
            "recency":     0.20,
            "consistency": 0.15,
        }

    def _calc_consistency(self, keyword: str, per_review: dict, total_reviews: int) -> float:
        """
        여러 리뷰어가 각자 언급한 키워드일수록 높은 점수.
        mention_count / total_reviews (0~1)
        """
        mention_count = sum(
            1 for counter in per_review.values()
            if keyword in counter
        )
        return round(mention_count / total_reviews, 4)

    def _calc_recency(self, keyword: str, per_review: dict, review_dates: dict) -> float:
        """
        최근 리뷰에서 언급될수록 높은 점수.
        경과 개월 수에 반비례하는 감쇠 가중치 적용: 1 / (1 + months * 0.1)
        """
        if not review_dates:
            return 1.0

        now          = datetime.now()
        weighted_sum = 0.0
        count        = 0

        for review_id, counter in per_review.items():
            if keyword not in counter:
                continue

            date = review_dates.get(review_id)
            if not date:
                continue

            months_ago   = max((now.year - date.year) * 12 + (now.month - date.month), 0)
            weighted_sum += 1 / (1 + months_ago * 0.1)
            count        += 1

        return round(weighted_sum / count, 4) if count > 0 else 0.0

    def _calc_score(
        self,
        tfidf:        dict,
        per_review:   dict,
        review_dates: Optional[dict] = None,  # {review_id: datetime}
        sentiment:    Optional[dict] = None,  # {keyword: float}  ← Phase 2 연동
    ) -> list:
        """
        최종 키워드 점수 산출.

        Parameters
        ----------
        tfidf        : {keyword: tfidf_score}  — STAGE 2 merged_tfidf
        per_review   : {review_id: Counter}    — STAGE 2 merged_per_review
        review_dates : {review_id: datetime}   — 최신성 계산용
        sentiment    : {keyword: float (-1~1)} — 감성 점수 (None이면 중립 1.0 적용)

        Returns
        -------
        list[dict]  score 내림차순 정렬
            [{"keyword": str, "score": float, "breakdown": dict}, ...]
        """
        total_reviews = len(per_review)
        if total_reviews == 0:
            return []

        max_tfidf = max(tfidf.values()) if tfidf else 1.0
        results   = []

        for keyword in tfidf:
            tfidf_score = tfidf[keyword] / max_tfidf

            # 감성 점수: -1~1 → 0~1 정규화. 연동 전 기본값 1.0 (긍정 중립 처리)
            if sentiment:
                sentiment_score = (sentiment.get(keyword, 0.0) + 1) / 2
            else:
                sentiment_score = 1.0

            recency_score     = self._calc_recency(keyword, per_review, review_dates)
            consistency_score = self._calc_consistency(keyword, per_review, total_reviews)

            final_score = (
                tfidf_score       * self.weights["tfidf"]       +
                sentiment_score   * self.weights["sentiment"]   +
                recency_score     * self.weights["recency"]     +
                consistency_score * self.weights["consistency"]
            )

            results.append({
                "keyword": keyword,
                "score":   round(final_score, 4),
                "breakdown": {
                    "tfidf":       round(tfidf_score,       4),
                    "sentiment":   round(sentiment_score,   4),
                    "recency":     round(recency_score,     4),
                    "consistency": round(consistency_score, 4),
                },
            })

        return sorted(results, key=lambda x: x["score"], reverse=True)
