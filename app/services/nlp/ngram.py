from collections import Counter
import math

from app.services.nlp.review_tfidf_analyze import ReviewTfidfAnalyzer


class NgramExtractor:
    def __init__(self, analyzer: ReviewTfidfAnalyzer):
        """
        ReviewTfidfAnalyzer 인스턴스를 받아 okt · stopwords · clean_text 공유.
        (구 ReviewAnalyzer → ReviewTfidfAnalyzer로 교체)
        """
        self.analyzer = analyzer

    def extract_bigrams(self, text: str) -> Counter:
        cleaned     = self.analyzer.preprocessor.clean_text(text)   # ← ReviewPreprocessor 위임
        pos_result  = self.analyzer.okt.pos(cleaned, stem=True)

        # 불용어를 제외한, 명사만 추출
        nouns = [
            w for w, p in pos_result
            if p == "Noun"
            and w not in self.analyzer.stopwords
            and len(w) > 1
        ]

        bigrams = Counter()
        # 명사 리스트에서 슬라이딩 윈도우로 2-gram 생성
        for i in range(len(nouns) - 1):
            bigrams[f"{nouns[i]} {nouns[i+1]}"] += 1

        return bigrams

    def extract_bigrams_per_review(self, reviews: list) -> dict:
        """
        전체 리뷰에서 2-gram Counter 반환
        반환 형식: {review_id: Counter} ← per_review와 동일
        """
        per_review_ngram = {}
        for review in reviews:
            review_id = review["id"] if isinstance(review, dict) else review.id
            content   = review["content"] if isinstance(review, dict) else review.content
            per_review_ngram[review_id] = self.extract_bigrams(content)
        return per_review_ngram

    
    def aggregate_bigrams(self, bigrams_per_review: dict[int, Counter]) -> Counter:
        """
        extract_biagrams_per_review에서 반환된 {review_id: Counter}를 받아, 
        전체 코퍼스 단위로 합산

        Returns
        ----------------------
        전체 리뷰의 2-gram을 합산한 Counter({"루프탑 뷰": 5, "파스타 맛": 3, ...})
        """
        total = Counter()
        for counter in bigrams_per_review.values():
            total.update(counter)
        return total
    
    def compute_pmi(
            self, 
            bigram_per_review: dict[int, Counter],
            unigram_counts: Counter,
            min_count: int = 3,
            pmi_threshold: float = 0.0 # 데이터 결과 확인하면서 조정 예정 (0.5~1.0)
        ) -> Counter:
        """
        PMI 계산 공식:
        PMI(w1, w2) = log2( P(w1, w2) / (P(w1) * P(w2)) )
        - P(w1, w2) = bigram_counts[(w1, w2)] / total_bigrams (전체 bigram 중 (w1,w2)가 등장하는 비율)
        - P(w1) = unigram_counts[w1] / total_unigrams (전체 unigram 중 w1이 등장하는 비율)
        - P(w2) = unigram_counts[w2] / total_unigrams (전체 unigram 중 w2이 등장하는 비율)
        - PMI > 0  : 우연보다 더 자주 같이 등장 → 의미있는 복합어
        - PMI ≤ 0  : 우연 수준의 인접 → 제거 대상
        """
        bigram_counts = self.aggregate_bigrams(bigram_per_review)

        total_bigrams = sum(bigram_counts.values())
        total_unigrams = sum(unigram_counts.values())

        if total_bigrams == 0 or total_unigrams == 0:
            return Counter()  # 데이터 부족 시 빈 Counter 반환
        
        result = Counter()

        for bigram, count in bigram_counts.items():
            if count < min_count:
                continue  # 빈도가 낮은 bigram은 제거
            w1, w2 = bigram.split()
            if len(w1) <= 1 or len(w2) <= 1:
                continue  # 단어 길이가 1 이하인 경우 제거

            p_bigram = count / total_bigrams
            p_w1 = unigram_counts[w1] / total_unigrams
            p_w2 = unigram_counts[w2] / total_unigrams

            if p_w1 == 0 or p_w2 == 0:
                continue  # 단어가 unigram에서 등장하지 않는 경우 제거

            pmi = math.log2(p_bigram / (p_w1 * p_w2))
            
            if pmi > pmi_threshold:
                # PMI 기준을 만족하는 bigram만 결과에 포함
                # 기존 : 통과한 bigram의 빈도를 저장 (count)
                # 개선 : PMI 점수로 저장 → 점수 기반으로 중요도 산출 가능 (추후 추가개선 필요)
                result[bigram] = round(pmi, 4)

        return result