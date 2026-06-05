from collections import Counter
import math

from app.services.nlp.review_tfidf_analyze import ReviewTfidfAnalyzer


class NgramExtractor:
    """
    리뷰 텍스트에서 2-gram(Bigram)을 추출하고 PMI 필터링을 수행.
    ReviewTfidfAnalyzer 인스턴스를 주입받아 okt · stopwords · clean_text 공유.
    """

    def __init__(self, analyzer: ReviewTfidfAnalyzer):
        self.analyzer = analyzer

    def extract_bigrams(self, text: str) -> Counter:
        """
        리뷰 텍스트 1개 → 명사 Bigram Counter.
        clean_text() 후 Okt POS 태깅, 명사만 추출해 슬라이딩 윈도우로 2-gram 생성.
        
        - sprint 2까지는 슬라이딩 윈도우 방식 추출 후 PMI 필터링으로 유의미한 Bigram만 선별하는 방식으로 진행
        - 추후 더 정교한 추출 방식 도입 고려 중 -> 기존 방식의 한계 (pmi 사용에도 불구하고 여전히 노이즈 과도함)

        반환: Counter({"루프탑 뷰": 2, "파스타 맛": 1, ...})
        """
        cleaned = self.analyzer.preprocessor.clean_text(text)
        tokens  = self.analyzer.kiwi.tokenize(cleaned)

        nouns = [
            t.form for t in tokens
            if t.tag.startswith("N")
            and t.form not in self.analyzer.stopwords
            and len(t.form) > 1
        ]

        bigrams = Counter()
        for i in range(len(nouns) - 1):
            bigrams[f"{nouns[i]} {nouns[i+1]}"] += 1

        return bigrams

    def extract_bigrams_per_review(self, reviews: list) -> dict[int, Counter]:
        """
        전체 리뷰 목록 → {review_id: Counter}.
        반환 형식이 per_review(unigram)와 동일해 scorer와 호환됨.
        """
        per_review_ngram: dict[int, Counter] = {}
        for review in reviews:
            review_id = review["id"]      if isinstance(review, dict) else review.id
            content   = review["content"] if isinstance(review, dict) else review.content
            per_review_ngram[review_id] = self.extract_bigrams(content)
        return per_review_ngram

    def aggregate_bigrams(self, bigrams_per_review: dict[int, Counter]) -> Counter:
        """
        {review_id: Counter} → 전체 코퍼스 단위 합산 Counter.

        반환: Counter({"루프탑 뷰": 5, "파스타 맛": 3, ...})
        """
        total = Counter()
        for counter in bigrams_per_review.values():
            total.update(counter)
        return total

    def compute_pmi(
        self,
        bigram_per_review: dict[int, Counter],
        unigram_counts:    Counter,
        min_count:         int   = 2,
        df_min:            int   = 3,
        pmi_threshold:     float = 2.0,
    ) -> Counter:
        """
        PMI 계산 후 유의미한 Bigram만 반환.

        PMI(w1, w2) = log2( P(w1,w2) / (P(w1) × P(w2)) )

        허들 3단계
        ──────────────────────────────────────────────────────────
        1. min_count      최소 등장 횟수 (기본 2)
        2. df_min         최소 등장 리뷰 수 (기본 3) — 단일 리뷰 반복 제거
        3. pmi_threshold  PMI 최솟값 (기본 2.0 = 우연보다 4배 이상 유의미)
        ──────────────────────────────────────────────────────────

        반환: Counter({bigram: pmi_score, ...})
        """
        bigram_counts = self.aggregate_bigrams(bigram_per_review)

        # 문서 빈도(df): bigram이 등장한 리뷰 수
        bigram_df: Counter = Counter()
        for counter in bigram_per_review.values():
            for bigram in counter:
                bigram_df[bigram] += 1

        total_bigrams  = sum(bigram_counts.values())
        total_unigrams = sum(unigram_counts.values())

        if total_bigrams == 0 or total_unigrams == 0:
            return Counter()

        result = Counter()

        for bigram, count in bigram_counts.items():
            # ① 전체 빈도 허들
            if count < min_count:
                continue
            # ② 문서 빈도 허들 (단일 리뷰 반복 제거)
            if bigram_df[bigram] < df_min:
                continue

            w1, w2 = bigram.split()
            if len(w1) <= 1 or len(w2) <= 1:
                continue

            p_bigram = count / total_bigrams
            p_w1     = unigram_counts[w1] / total_unigrams
            p_w2     = unigram_counts[w2] / total_unigrams

            if p_w1 == 0 or p_w2 == 0:
                continue

            pmi = math.log2(p_bigram / (p_w1 * p_w2))

            # ③ PMI 허들 (2.0 = 우연보다 4배 이상 유의미)
            if pmi > pmi_threshold:
            
                result[bigram] = round(pmi, 4)

        return result
