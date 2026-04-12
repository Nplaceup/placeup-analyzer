from collections import Counter

# ── 파이프라인 모듈 ─────────────────────────────────────────────────────────
from app.services.nlp.nlp_preprocessing import ReviewPreprocessor         # STAGE 1  (clean_text 전처리)
from app.services.nlp.review_tfidf_analyze import ReviewTfidfAnalyzer     # STAGE 1  (형태소 분석) + STAGE 1b (TF-IDF)
from app.services.nlp.keyword_normalizer import KeywordNormalizer          # STAGE 1a (표현 통일)
from app.services.nlp.ngram import NgramExtractor                          # STAGE 2  (N-gram PMI)
from app.services.scoring.keyword_scorer import keywordScorer              # STAGE 3  (스코어링)
from app.output.keyword_formatter import attach_inducement                 # STAGE 4  (카테고리 태깅 + 유도어 결합)

# ── 데이터 필터 ─────────────────────────────────────────────────────────────
from app.data.blocklist import KEYWORD_BLOCKLIST                           # STAGE 1a (범용어 제거)

# ── DB ─────────────────────────────────────────────────────────────────────
from app.db.repository import (
    get_reviews, get_review_dates,
    create_recommend_keywords_table, upsert_recommend_keywords,
)


def run(place_id: int):

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 0 · DB 조회
    # ══════════════════════════════════════════════════════════════════════
    reviews      = get_reviews(place_id)
    review_dates = get_review_dates(place_id)
    # get_place_info(place_id) ← 구현 예정 (address, category 조회)

    if not reviews:
        print(f"[SKIP] place_id={place_id} 리뷰 없음")
        return

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 1 · 형태소 분석
    # ReviewTfidfAnalyzer: ReviewPreprocessor.clean_text → Okt POS 태깅
    # 반환: {review_id: Counter(keyword → count)}
    # ══════════════════════════════════════════════════════════════════════
    analyzer   = ReviewTfidfAnalyzer()
    per_review = analyzer.extract_per_review(reviews)

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 1a · KEYWORD_BLOCKLIST 필터 + KeywordNormalizer
    # 1) 범용 상위 개념어 제거 (blocklist.py)
    # 2) 동의어 → 대표형 통일, Counter 빈도 합산 (expression_dictionary.py)
    # ══════════════════════════════════════════════════════════════════════
    normalizer = KeywordNormalizer()

    per_review_clean: dict[int, Counter] = {}
    for review_id, counter in per_review.items():
        # 1) 블랙리스트 제거
        filtered = Counter({kw: cnt for kw, cnt in counter.items()
                            if kw not in KEYWORD_BLOCKLIST})
        # 2) 표현 통일 (존맛탱→맛있다, 친절하다→친절 ...)
        per_review_clean[review_id] = normalizer.normalize(filtered)

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 1b · TF-IDF 계산
    # STAGE 1a 통과 후 정제된 Counter 기반으로 계산
    # 반환: {keyword: tfidf_score}
    # ══════════════════════════════════════════════════════════════════════
    tfidf = analyzer.compute_tfidf(per_review_clean)

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 2 · N-gram (PMI 필터링)
    # ══════════════════════════════════════════════════════════════════════
    ngram_extractor    = NgramExtractor(analyzer)
    bigrams_per_review = ngram_extractor.extract_bigrams_per_review(reviews)

    # PMI 계산용 unigram 전체 합산 (STAGE 1 결과 기준, 정규화 전)
    # ※ bigram 추출은 원본 텍스트 기반(정규화 전) → unigram도 동일 기준으로 맞춤
    unigram_counts: Counter = Counter()
    for counter in per_review.values():
        unigram_counts.update(counter)

    filtered_bigrams = ngram_extractor.compute_pmi(
        bigrams_per_review,
        unigram_counts,
        min_count=3,       # 공동출현 3회 미만 제거
        pmi_threshold=0.0  # 우연 수준 이하 제거
    )

    # ── 1-gram + 2-gram 병합 ────────────────────────────────────────────
    # PMI 값(log₂ 스케일, 0~10+)을 TF-IDF 스케일로 정규화해 혼입 방지
    # → scorer의 max_tfidf 정규화 시 bigram이 unigram 점수를 잠식하지 않음
    if filtered_bigrams:
        max_pmi     = max(filtered_bigrams.values())
        max_tfidf_v = max(tfidf.values()) if tfidf else 1.0
        normalized_bigrams = {
            bg: round((pmi / max_pmi) * max_tfidf_v, 6)
            for bg, pmi in filtered_bigrams.items()
        }
    else:
        normalized_bigrams = {}

    merged_tfidf: dict = {**tfidf, **normalized_bigrams}

    valid_bigrams = set(filtered_bigrams.keys())
    merged_per_review: dict[int, Counter] = {}
    for review_id, counter in per_review_clean.items():
        merged = Counter(counter)
        merged.update({
            bg: cnt
            for bg, cnt in bigrams_per_review.get(review_id, {}).items()
            if bg in valid_bigrams
        })
        merged_per_review[review_id] = merged

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 2.5 · 외부 키워드 결합 (구현 예정)
    # keyword_merger.py · get_place_rankings() · get_keyword_search_volumes()
    # CASE A: NLP ∩ rankings  /  CASE B: rankings only  /  CASE C: NLP only
    # ══════════════════════════════════════════════════════════════════════
    # merged_tfidf, merged_per_review = keyword_merger(place_id, merged_tfidf, merged_per_review)

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 3 · 스코어링
    # ══════════════════════════════════════════════════════════════════════
    scorer = keywordScorer()
    scored = scorer._calc_score(
        tfidf        = merged_tfidf,
        per_review   = merged_per_review,
        review_dates = review_dates,
        sentiment    = None   # 감성 사전 완성 후 연결
    )

    print("=== 키워드 점수 ===")
    for item in scored[:10]:
        b = item["breakdown"]
        print(
            f"{item['keyword']:12} | "
            f"최종: {item['score']:.4f} | "
            f"TF-IDF: {b['tfidf']:.4f} | "
            f"감성: {b['sentiment']:.4f} | "
            f"최신성: {b['recency']:.4f} | "
            f"일관성: {b['consistency']:.4f}"
        )

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 3.5 · 유사도 매핑 (구현 예정)
    # SemanticMapper — 유사 키워드 중복 제거 후 top_n 전달
    # ══════════════════════════════════════════════════════════════════════
    # scored = semantic_dedup(scored)

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 4 · 카테고리 태깅 + 유도어 결합
    # semantic_dictionary → CategoryMapper → inducement_dict
    # ══════════════════════════════════════════════════════════════════════
    formatted = attach_inducement(scored, top_n=20)

    print("\n=== 포맷팅 결과 ===")
    print(f"{'키워드':<22} {'점수':>6}  {'카테고리':<8}  {'property':<14}  {'목적':<10}  ngram  induced")
    print("-" * 85)
    for item in formatted:
        print(
            f"{item['keyword']:<22} {item['base_score']:>6.4f}  "
            f"{item['category']:<8}  {item.get('property', ''):.<14}  "
            f"{item['keyword_purpose']:<10}  "
            f"{'O' if item['is_ngram']   else 'X':^5}  "
            f"{'O' if item['is_induced'] else 'X':^7}"
        )

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 5 · DB upsert
    # ══════════════════════════════════════════════════════════════════════
    scored_map = {item["keyword"]: item["breakdown"] for item in scored}
    upserted   = upsert_recommend_keywords(place_id, formatted, scored_map)
    print(f"\n[완료] place_id={place_id} 키워드 {upserted}개 DB 저장")


if __name__ == "__main__":
    # create_recommend_keywords_table()  # 최초 1회만 실행 (테이블 없을 때)
    run(place_id=166)
