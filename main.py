from app.services.nlp.nlp_engine import ReviewAnalyzer
from app.services.nlp.ngram import NgramExtractor
from app.services.scoring.keyword_scorer import keywordScorer
from app.db.repository import get_reviews, get_review_dates

def run(place_id: int):

    reviews = get_reviews(place_id)
    review_dates = get_review_dates(place_id)

    analyzer    = ReviewAnalyzer()
    extractor   = NgramExtractor(analyzer) 
    scorer      = keywordScorer()

    # 1-gram
    result = analyzer.analyze_reviews(reviews)

    # 2-gram
    n_gram_per_review = extractor.extract_biagrams_per_review(reviews)

    # merge (우선, 동일 풀에서 점수 산출 -> 추후, 풀 분리하여 점수 튜닝할 예정)
    for review_id, counter in n_gram_per_review.items():
        result['per_review'][review_id] += counter

    # re-calculate of TF-IDF
    combined_tfidf = analyzer._calculate_tfidf(result['per_review'])

    scored = scorer._calc_score(
        tfidf= dict(combined_tfidf),
        per_review= result["per_review"],
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
    run(place_id=167)

