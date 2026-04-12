from collections import Counter
from app.services.nlp.nlp_engine import ReviewAnalyzer
from app.services.nlp.ngram import NgramExtractor
from app.services.scoring.keyword_scorer import keywordScorer
from app.output.keyword_formatter import attach_inducement
from app.db.repository import (
    get_reviews, get_review_dates,
    create_recommend_keywords_table, upsert_recommend_keywords,
)

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

    # ------------------------- 5. 점수 산출 ────────────────────────
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
    # ------------- 6. Formatter로 카테고리 분류 → 유도어 결합 ──────────────────
    formatted = attach_inducement(scored, top_n=20)

    print("\n=== 포맷팅 결과 ===")
    print(f"{'키워드':<20} {'점수':>6}  {'카테고리':<8}  {'목적':<10}  ngram  induced")
    print("-" * 70)
    for item in formatted:
        print(
            f"{item['keyword']:<20} {item['base_score']:>6.4f}  "
            f"{item['category']:<8}  {item['keyword_purpose']:<10}  "
            f"{'O' if item['is_ngram'] else 'X':^5}  "
            f"{'O' if item['is_induced'] else 'X':^7}"
        )

    # ------------- 7. 로컬 DB upsert ──────────────────────────────────────────
    # scored_map: keyword → breakdown (upsert 시 지표별 점수 저장용)
    scored_map = {item["keyword"]: item["breakdown"] for item in scored}
    upserted = upsert_recommend_keywords(place_id, formatted, scored_map)
    print(f"\n[완료] place_id={place_id} 키워드 {upserted}개 DB 저장")

if __name__ == '__main__':
    #create_recommend_keywords_table()  # 최초 1회만 실행 (테이블 없을 때)
    run(place_id=167) # 테스트용 place_id, 실제론 매장별로 실행

