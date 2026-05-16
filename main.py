from collections import Counter
from app.services.nlp.nlp_engine import ReviewAnalyzer
from app.services.nlp.ngram import NgramExtractor
from app.services.scoring.keyword_scorer import keywordScorer
from app.output.keyword_formatter import attach_inducement
from app.db.repository import (
    get_reviews, get_review_dates,
    create_recommend_keywords_table, upsert_recommend_keywords,
)
from app.services.scoring.seo_scorer import SEOScorer
from app.db.repository import get_recommend_keywords
import redis
import json

r = redis.Redis(host='localhost', port=6379, db=0)

def json_serial(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    raise TypeError(f'Object of type {type(obj)} is not JSON serializable')

def run(place_id: int):

    reviews = get_reviews(place_id)
    review_dates = get_review_dates(place_id)

    # ------------------------- 1-gram & TF-IDF -------------------------
    analyzer    = ReviewAnalyzer()
    result = analyzer.analyze_reviews(reviews)

    # ------------------------- 2-gram (PMI 필터링 포함) -------------------------
    n_gram = NgramExtractor(analyzer)
    bigrams_per_review = n_gram.extract_biagrams_per_review(reviews)

    unigram_counts = Counter()
    for counter in result["per_review"].values():
        unigram_counts.update(counter)

    filtered_bigrams = n_gram.compute_pmi(
        bigrams_per_review,
        unigram_counts,
        min_count=3,
        pmi_threshold=0.0
    )
    
    merged_tfidf = dict(result["tfidf"])
    merged_tfidf.update(dict(filtered_bigrams))

    valid_bigrams = set(filtered_bigrams.keys())

    merged_per_review = {}
    for review_id, counter in result["per_review"].items():
        merged = Counter(counter)
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
        sentiment= None
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
    scored_map = {item["keyword"]: item["breakdown"] for item in scored}
    upserted = upsert_recommend_keywords(place_id, formatted, scored_map)
    print(f"\n[완료] place_id={place_id} 키워드 {upserted}개 DB 저장")

    # ------------- STAGE 6. SEO Score 산출 ──────────────────────────────────
    keywords = get_recommend_keywords(place_id)
    seo_scorer = SEOScorer()
    seo_result = seo_scorer.calc_score(keywords)

    print(f"\n{'='*60}")
    print(f"  STAGE 6 · SEO Score 산출")
    print('='*60)
    print(f"  SEO 점수 : {seo_result['total']}점  {seo_result['grade']}")
    b = seo_result["breakdown"]
    print(f"  키워드 최적화  : {b['keyword_optimization']:.1f} / 40")
    print(f"  리뷰 품질      : {b['review_quality']:.1f} / 30")
    print(f"  검색 노출 현황 : {b['search_exposure']:.1f} / 20")
    print(f"  경쟁 포지셔닝  : {b['competition']:.1f} / 10")

    # ------------- Redis 저장 (변경) ──────────────────────────────────────────
    # 1. 추천 키워드: keyword 문자열만 추출
    keyword_list = [item["keyword"] for item in formatted]
    result_data = {
        "place_id": place_id,
        "keywords": keyword_list
    }

    # 2. 결과 저장 (TTL 1시간)
    r.set(
        f"result:{place_id}",
        json.dumps(result_data, ensure_ascii=False),
        ex=3600
    )

    # 3. SEO 점수 저장 (기존 유지)
    r.set(f"seo:{place_id}", json.dumps(seo_result, ensure_ascii=False))

    # 4. Backend에 완료 알림 발행
    r.publish("analysis:done", json.dumps({
        "place_id": place_id,
        "status": "success"
    }))
    print(f"\n[Redis] place_id={place_id} 데이터 저장 및 알림 발행 완료")


def listen_queue():
    """Backend가 큐에 넣은 작업을 대기하며 처리"""
    print("[Worker] 분석 큐 대기 중...")
    while True:
        _, data = r.brpop("analysis:queue")
        payload = json.loads(data)
        place_id = payload["place_id"]
        print(f"[Worker] place_id={place_id} 분석 시작")
        try:
            run(place_id)
        except Exception as e:
            r.publish("analysis:done", json.dumps({
                "place_id": place_id,
                "status": "error",
                "message": str(e)
            }))


if __name__ == "__main__":
    create_recommend_keywords_table()
    listen_queue()