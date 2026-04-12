# STAGE 1 (형태소 분석) + STAGE 1b (TF-IDF 계산)
#
# ─ 역할 ──────────────────────────────────────────────────────────────────────
# ReviewPreprocessor(clean_text) 이후 단계:
#   1. extract_keywords()      : Okt POS 태깅 → Counter  (STAGE 1)
#   2. extract_per_review()    : 리뷰 목록 → {review_id: Counter}
#   3. compute_tfidf()         : per_review Counter → {keyword: tfidf_score} (STAGE 1b)
#
# ─ TF-IDF 계산 방식 ─────────────────────────────────────────────────────────
# 문서 단위: 리뷰 1개 = 1 document
# TF(t, d)  = count(t, d) / total_tokens(d)    (리뷰 내 정규화 빈도)
# IDF(t)    = log(N / df(t) + 1)               (역문서빈도, 스무딩)
# TF-IDF(t) = Σ TF(t,d) * IDF(t)              (전체 리뷰 합산)


import math
from collections import Counter
from konlpy.tag import Okt

from app.services.nlp.nlp_preprocessing import ReviewPreprocessor


class ReviewTfidfAnalyzer:

    def __init__(self):
        self.preprocessor = ReviewPreprocessor()
        self.stopwords    = self.preprocessor.stopwords
        self.okt          = Okt()

    # ── STAGE 1: 형태소 분석 ────────────────────────────────────────────────
    def extract_keywords(self, text: str) -> Counter:
        """
        리뷰 텍스트 1개 → 명사·형용사 Counter.
        clean_text() 후 Okt POS 태깅, 불용어·단어 1자 제거.

        반환: Counter({"육즙": 3, "파스타": 2, ...})
        """
        if not text or not isinstance(text, str):
            return Counter()

        clean      = self.preprocessor.clean_text(text)
        pos_result = self.okt.pos(clean, stem=True)

        keywords = [
            word for word, pos in pos_result
            if pos in ("Noun", "Adjective")
            and word not in self.stopwords
            and len(word) > 1
        ]
        return Counter(keywords)

    def extract_per_review(self, reviews: list) -> dict[int, Counter]:
        """
        리뷰 목록 → {review_id: Counter}.
        ngram.py, keyword_scorer 등과 공유하는 기본 입력 형식.

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
    def compute_tfidf(self, per_review: dict[int, Counter]) -> dict[str, float]:
        """
        per_review Counter → {keyword: tfidf_score}.
        keyword_scorer._calc_score()의 tfidf 인자로 바로 전달 가능.

        Parameters
        ----------
        per_review : dict[int, Counter]
            extract_per_review() 반환값.
            {review_id: Counter(keyword → count)}

        Returns
        -------
        dict[str, float]
            {"파스타": 0.312, "육즙": 0.278, ...}
        """
        n_docs = len(per_review)
        if n_docs == 0:
            return {}

        # 문서 빈도 (df): 키워드가 등장한 리뷰 수
        df: dict[str, int] = Counter()
        for counter in per_review.values():
            for keyword in counter:
                df[keyword] += 1

        # IDF 사전 계산
        idf: dict[str, float] = {
            kw: math.log(n_docs / (count + 1))
            for kw, count in df.items()
        }

        # TF-IDF 합산 (리뷰 전체 합산)
        tfidf_scores: dict[str, float] = {}

        for counter in per_review.values():
            total_tokens = sum(counter.values())
            if total_tokens == 0:
                continue

            for keyword, count in counter.items():
                tf  = count / total_tokens
                tfidf_scores[keyword] = tfidf_scores.get(keyword, 0.0) + tf * idf[keyword]

            

        return {kw: round(score, 6) for kw, score in tfidf_scores.items()}
