from collections import Counter
from app.services.nlp.nlp_engine import ReviewAnalyzer
from app.services.nlp.ngram import NgramExtractor
from app.services.scoring.keyword_scorer import keywordScorer
from app.db.repository import get_reviews, get_review_dates

def run(place_id: int):

    reviews = get_reviews(place_id)
    review_dates = get_review_dates(place_id)

    # ------------------------- 1-gram & TF-IDF -------------------------
    analyzer    = ReviewAnalyzer()
    result = analyzer.analyze_reviews(reviews)

    # ------------------------- 2-gram (PMI 필터링 포함) -------------------------
    n_gram = NgramExtractor(analyzer)
    bigrams_per_review = n_gram.extract_biagrams_per_review(reviews)

    # PMI 계산용 unigram_counts: per_review를 전체 합산
    unigram_counts = Counter()
    for counter in result["per_review"].values():
        unigram_counts.update(counter)

    # ------------------------- PMI 필터링 → 의미있는 bigram만 남김 -----------------
    filtered_bigrams = n_gram.compute_pmi(
        bigrams_per_review,
        unigram_counts,
        min_count=3,       # 공동출현 3회 미만 제거
        pmi_threshold=0.0  # 우연 수준 이하 제거
    )
    
    # ------------------------- 4. 1-gram + 2-gram 병합 ────────────────────────
    # tfidf: 1-gram TF-IDF값에 PMI 통과한 bigram 빈도 합산
    merged_tfidf = dict(result["tfidf"])
    merged_tfidf.update(dict(filtered_bigrams))

    # per_review: 각 리뷰에서 PMI 통과한 bigram만 추가
    valid_bigrams = set(filtered_bigrams.keys())  # PMI 통과 bigram 집합

    merged_per_review = {}
    for review_id, counter in result["per_review"].items():
        merged = Counter(counter)  # 1-gram 복사
        # 해당 리뷰의 bigram 중 PMI 통과한 것만 추가
        valid_bg = {
            bg: cnt
            for bg, cnt in bigrams_per_review.get(review_id, {}).items()
            if bg in valid_bigrams
        }
        merged.update(valid_bg)
        merged_per_review[review_id] = merged

    # -- 점수 산출 --
    scorer      = keywordScorer()
    scored = scorer._calc_score(
        tfidf= dict(merged_tfidf),
        per_review= merged_per_review,
        review_dates= review_dates,         
        sentiment= None             # 사전 완성 후, 연결
    )

    print("=== 키워드 점수 ===")
    for item in scored:
        b = item['breakdown']
        print(
            f"{item['keyword']:10} | "
            f"최종: {item['score']:.4f} | "
            f"TF-IDF: {b['tfidf']:.4f} | "
            f"감성: {b['sentiment']:.4f} | "
            f"최신성: {b['recency']:.4f} | "
            f"일관성: {b['consistency']:.4f}"
        )
    
if __name__ == '__main__':
    run(place_id=166)

