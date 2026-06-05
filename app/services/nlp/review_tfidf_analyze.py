# STAGE 1 (Kiwi POS 태깅) + STAGE 1b (TF-IDF 계산)
#
# TF-IDF 계산 방식 (리뷰 1개 = 1 document):
#   TF(t,d)   = count(t,d) / total_tokens(d)
#   IDF(t)    = log(N / df(t) + 1)          ← +1 스무딩
#   TF-IDF(t) = Σ TF(t,d) × IDF(t)         ← 전체 리뷰 합산
#   min_df=2  : 1회 언급 단어·형태소 오류 차단

import math
from collections import Counter
from kiwipiepy import Kiwi

from app.services.nlp.nlp_preprocessing import ReviewPreprocessor


class ReviewTfidfAnalyzer:

    def __init__(self):
        self.preprocessor = ReviewPreprocessor()
        self.stopwords    = self.preprocessor.stopwords
        self.kiwi         = Kiwi()

    # ── STAGE 1: 형태소 분석 ────────────────────────────────────────────────
    def extract_keywords(self, text: str) -> Counter:
        """
        리뷰 텍스트 1개 → 명사 Counter.
        clean_text() 후 Kiwi POS 태깅, 불용어·1자 단어 제거.

        반환: Counter({"육즙": 3, "파스타": 2, ...})
        """
        if not text or not isinstance(text, str):
            return Counter()

        clean  = self.preprocessor.clean_text(text)
        tokens = self.kiwi.tokenize(clean)

        keywords = [
            t.form for t in tokens
            if t.tag.startswith("N")
            and t.form not in self.stopwords
            and len(t.form) > 1
        ]
        return Counter(keywords)

    def extract_per_review(self, reviews: list) -> dict[int, Counter]:
        """
        리뷰 목록 → {review_id: Counter}.

        reviews 원소: dict({"id": int, "content": str, ...})
                     또는 ORM 객체(.id, .content 속성)
        """
        per_review: dict[int, Counter] = {}

        for review in reviews:
            if isinstance(review, dict):
                review_id = review["id"]
                content   = review["content"]
            else:
                review_id = review.id
                content   = review.content

            per_review[review_id] = self.extract_keywords(content)

        return per_review

    # ── STAGE 1b: TF-IDF 계산 ───────────────────────────────────────────────
    def compute_tfidf(self, per_review: dict[int, Counter], min_df: int = 2) -> dict[str, float]:
        """per_review Counter → {keyword: tfidf_score}. min_df 미달 키워드 제외."""
        n_docs = len(per_review)
        if n_docs == 0:
            return {}

        df: dict[str, int] = Counter()
        for counter in per_review.values():
            for keyword in counter:
                df[keyword] += 1

        valid_kws = {kw for kw, count in df.items() if count >= min_df}

        idf: dict[str, float] = {
            kw: math.log(n_docs / (df[kw] + 1))
            for kw in valid_kws
        }

        tfidf_scores: dict[str, float] = {}

        for counter in per_review.values():
            total_tokens = sum(counter.values())
            if total_tokens == 0:
                continue

            for keyword, count in counter.items():
                if keyword not in valid_kws:
                    continue
                tf = count / total_tokens
                tfidf_scores[keyword] = tfidf_scores.get(keyword, 0.0) + tf * idf[keyword]

        return {kw: round(score, 6) for kw, score in tfidf_scores.items()}
