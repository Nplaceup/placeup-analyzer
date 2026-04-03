from collections import Counter


class NgramExtractor:
    def __init__(self, analyzer):
        """
        ReviewAnalyzer 인스턴스를 받아 okt · stopwords · clean_text 공유
        """
        self.analyzer = analyzer

    def extract_bigrams(self, text: str) -> Counter:
        cleaned     = self.analyzer.clean_text(text)
        pos_result  = self.analyzer.okt.pos(cleaned, stem=True)

        # 불용어를 제외한, 명사만 추출
        nouns = [
            w for w, p in pos_result
            if p == "Noun"
            and w not in self.analyzer.stopwords
            and len(w) > 1
        ]

        biagrams = Counter()
        # 명사 리스트에서 슬라이딩 윈도우로 2-gram 생성 (추후 보완)
        for i in range(len(nouns) - 1):
            biagrams[f"{nouns[i]} {nouns[i+1]}"] += 1

        return biagrams
    
    def extract_biagrams_per_review(self, reviews: list) -> dict:
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