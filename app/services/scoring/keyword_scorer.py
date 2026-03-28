from datetime import datetime
from collections import Counter
from typing import Optional

class keywordScorer:
    def __init__(self):
        # 지표별 가중치 설정
        self.weights = {
            "tfidf" :       0.40,       # TF-IDF
            "sentiment" :   0.25,       # 감정
            "recency"   :   0.20,       # 최신성
            "consistency":   0.15        # 일관성
        }
    def _calc_consistency(self, keyword, per_review, total_reviews):
        """ 여러 리뷰어가 각자 언급한 키워드일수록 높은 가중치"""
        mention_count = 0
        # 해당 키워드가 몇 개의 리뷰에 언급되었는지 카운트
        for review_id, counter in per_review.items():
            if keyword in counter:
                mention_count +=1
    
        return round(mention_count / total_reviews, 4)
    
    def _calc_recency(self, keyword, per_review, review_dates):
        """ 최근에 게시한 리뷰일수록 높은 가중치 """
        if not review_dates:
            return 1.0
        
        now = datetime.now()
        weighted_sum = 0
        count = 0

        for review_id, counter in per_review.items():
            if keyword not in counter:
                continue
            # 리뷰 게시 일자
            date = review_dates.get(review_id)

            if not date:
                continue
            # 경과 기간 단위 통일 (month)
            months_ago = (now.year - date.year) * 12 + (now.month - date.month)
            # 경과 개월수 증가 할수록 가중치 감소 (가치 하락)
            weight = 1 / (1 + months_ago * 0.1)
            weighted_sum += weight * counter[keyword]
            count += 1

        return round(weighted_sum / count, 4) if count > 0 else 0.0

    def _calc_score(
            self, 
            tfidf : dict, 
            per_review : dict, 
            review_dates : Optional[dict] = None,    # {review_id: datetime}
            sentiment : Optional[dict] = None       # {keyword: float}
        ) -> list:
        """
            최종 키워드 점수 산출
            - 반환 : [{"keyword" : str}, {"score" : float}, {"breakdown" : dict}, ...]
        """
        total_reviews = len(per_review)

        if total_reviews == 0:
            return []
        
        all_keywords = set(tfidf.keys())

        max_tfidf = max(tfidf.values()) if tfidf else 1

        results = []

        for keyword in all_keywords:
            tfidf_score = tfidf.get(keyword, 0) / max_tfidf

            if sentiment:
                raw = sentiment.get(keyword, 0.0)
                sentiment_score = (raw + 1) / 2
            else:
                sentiment_score = 1.0

            recency_score = self._calc_recency(keyword, per_review, review_dates)
            consistency_score = self._calc_consistency(keyword, per_review, total_reviews)

            final_score = (
                tfidf_score         * self.weights["tfidf"] +
                sentiment_score     * self.weights["sentiment"] +
                recency_score       * self.weights["recency"] +
                consistency_score   * self.weights["consistency"]
            )

            results.append({
                "keyword": keyword,
                "score": round(final_score, 4),
                "breakdown": {
                    "tfidf":       round(tfidf_score, 4),
                    "sentiment":   round(sentiment_score, 4),
                     "recency":     round(recency_score, 4),
                    "consistency": round(consistency_score, 4),
                }
            })
        # 점수 내림차순 정렬 
        return sorted(results, key=lambda x: x["score"], reverse=True)