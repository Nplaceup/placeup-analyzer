from collections import Counter

# ── 파이프라인 모듈 ─────────────────────────────────────────────────────────
from app.services.nlp.nlp_preprocessing import ReviewPreprocessor         # STAGE 1  (clean_text 전처리)
from app.services.nlp.review_tfidf_analyze import ReviewTfidfAnalyzer     # STAGE 1  (형태소 분석) + STAGE 1b (TF-IDF)
from app.services.nlp.keyword_normalizer import KeywordNormalizer          # STAGE 1a (표현 통일)
from app.services.nlp.ngram import NgramExtractor                          # STAGE 2  (N-gram PMI)
from app.services.nlp.keyword_merger import merge_keywords, summarize_merge_result  # STAGE 2.5 (외부 키워드 결합)
from app.services.scoring.keyword_scorer import keywordScorer              # STAGE 3  (스코어링)
from app.output.keyword_formatter import attach_inducement                 # STAGE 4  (카테고리 태깅 + 유도어 결합)

# ── 데이터 필터 ─────────────────────────────────────────────────────────────
from app.data.blocklist import KEYWORD_BLOCKLIST                           # STAGE 1a (범용어 제거)

# ── DB ─────────────────────────────────────────────────────────────────────
from app.db.repository import (
    get_reviews, get_review_dates, get_place_info,
    create_recommend_keywords_table, upsert_recommend_keywords,
)


# ── 디버그 출력 헬퍼 ─────────────────────────────────────────────────────────
def _print_counter_sample(title: str, counter: Counter, top: int = 15):
    print(f"\n  [{title}] 상위 {top}개")
    for kw, cnt in counter.most_common(top):
        print(f"    {kw:<18} {cnt}")

def _sep(label: str):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)


def run(place_id: int):

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 0 · DB 조회
    # ══════════════════════════════════════════════════════════════════════
    reviews      = get_reviews(place_id)
    review_dates = get_review_dates(place_id)
    place_info   = get_place_info(place_id)   # 지역/업종 컨텍스트

    if not reviews:
        print(f"[SKIP] place_id={place_id} 리뷰 없음")
        return

    _sep(f"STAGE 0 · DB 조회 — place_id={place_id}")
    print(f"  리뷰 수        : {len(reviews)}개")
    print(f"  날짜 매핑 수   : {len(review_dates)}개")
    if place_info:
        print(f"  매장명         : {place_info['name']}")
        print(f"  업종           : {place_info['category']}")
        print(f"  동네/역세권    : {place_info['neighborhood'] or '(미설정)'}")
        print(f"  시/구          : {place_info['city']}")
    else:
        print(f"  place_info     : 조회 실패 (지역/업종 결합 스킵)")
    print(f"  리뷰 샘플 (3개):")
    for r in reviews[:3]:
        body = r["content"][:60].replace("\n", " ")
        print(f"    id={r['id']} | {body}...")

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 1 · 형태소 분석
    # ReviewTfidfAnalyzer: ReviewPreprocessor.clean_text → Okt POS 태깅
    # 반환: {review_id: Counter(keyword → count)}
    # ══════════════════════════════════════════════════════════════════════
    analyzer   = ReviewTfidfAnalyzer()
    per_review = analyzer.extract_per_review(reviews)

    _sep("STAGE 1 · 형태소 분석 (Okt POS)")
    total_tokens_s1 = sum(sum(c.values()) for c in per_review.values())
    unique_kw_s1    = len(set(kw for c in per_review.values() for kw in c))
    print(f"  리뷰별 Counter 수  : {len(per_review)}개")
    print(f"  전체 토큰 수       : {total_tokens_s1}개")
    print(f"  고유 키워드 수     : {unique_kw_s1}개")
    # 전체 합산 후 상위 출력
    all_s1: Counter = Counter()
    for c in per_review.values():
        all_s1.update(c)
    _print_counter_sample("전체 합산 키워드", all_s1, top=20)

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 1a · KEYWORD_BLOCKLIST 필터 + KeywordNormalizer
    # 1) 범용 상위 개념어 제거 (blocklist.py)
    # 2) 동의어 → 대표형 통일, Counter 빈도 합산 (expression_dictionary.py)
    # ══════════════════════════════════════════════════════════════════════
    normalizer = KeywordNormalizer()

    per_review_clean: dict[int, Counter] = {}
    blocklist_removed: Counter = Counter()   # 제거된 키워드 집계
    for review_id, counter in per_review.items():
        # 1) 블랙리스트 제거
        removed   = Counter({kw: cnt for kw, cnt in counter.items()
                             if kw in KEYWORD_BLOCKLIST})
        filtered  = Counter({kw: cnt for kw, cnt in counter.items()
                             if kw not in KEYWORD_BLOCKLIST})
        blocklist_removed.update(removed)
        # 2) 표현 통일 (존맛탱→맛있다, 친절하다→친절 ...)
        per_review_clean[review_id] = normalizer.normalize(filtered)

    _sep("STAGE 1a · BLOCKLIST 필터 + 표현 통일")
    total_tokens_clean = sum(sum(c.values()) for c in per_review_clean.values())
    unique_kw_clean    = len(set(kw for c in per_review_clean.values() for kw in c))
    print(f"  블랙리스트 제거 키워드 ({len(blocklist_removed)}종):")
    for kw, cnt in blocklist_removed.most_common():
        print(f"    '{kw}' × {cnt}회 제거")
    print(f"  정제 후 전체 토큰 수  : {total_tokens_clean}개 (제거 전 {total_tokens_s1}개)")
    print(f"  정제 후 고유 키워드   : {unique_kw_clean}개 (제거 전 {unique_kw_s1}개)")
    all_clean: Counter = Counter()
    for c in per_review_clean.values():
        all_clean.update(c)
    _print_counter_sample("정제 후 합산 키워드", all_clean, top=20)

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 1b · TF-IDF 계산
    # STAGE 1a 통과 후 정제된 Counter 기반으로 계산
    # 반환: {keyword: tfidf_score}
    # ══════════════════════════════════════════════════════════════════════
    tfidf = analyzer.compute_tfidf(per_review_clean)

    _sep("STAGE 1b · TF-IDF")
    print(f"  TF-IDF 키워드 수 : {len(tfidf)}개")
    print(f"  score=0 키워드   : {sum(1 for v in tfidf.values() if v == 0.0)}개  "
          f"(df=N 인 경우 IDF=0, 정상)")
    print(f"\n  {'키워드':<18} {'TF-IDF':>8}")
    print(f"  {'-'*28}")
    for kw, score in sorted(tfidf.items(), key=lambda x: -x[1])[:20]:
        print(f"  {kw:<18} {score:>8.5f}")

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
        min_count=2,       # 전체 등장 횟수 ≥ 2
        df_min=2,          # 등장 리뷰 수 ≥ 2 (단일 리뷰 반복 제거)
        pmi_threshold=1.0, # log2 기준 우연보다 2배 이상 유의미한 조합만 통과
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

    _sep("STAGE 2 · N-gram PMI")
    all_bigrams_raw: Counter = Counter()
    for c in bigrams_per_review.values():
        all_bigrams_raw.update(c)
    # 단계별 탈락 현황 출력
    cnt_min  = sum(1 for v in all_bigrams_raw.values() if v >= 2)
    bigram_df_debug: Counter = Counter()
    for c in bigrams_per_review.values():
        for bg in c:
            bigram_df_debug[bg] += 1
    cnt_df   = sum(1 for bg, v in all_bigrams_raw.items()
                   if v >= 2 and bigram_df_debug[bg] >= 2)
    print(f"  전체 bigram 후보        : {len(all_bigrams_raw):>4}개")
    print(f"  min_count≥2 통과        : {cnt_min:>4}개")
    print(f"  + df_min≥2 통과         : {cnt_df:>4}개  (단일 리뷰 반복 제거 후)")
    print(f"  + PMI>1.0 최종 통과     : {len(filtered_bigrams):>4}개")
    if filtered_bigrams:
        print(f"\n  {'bigram':<22} {'PMI':>6}  df  →  {'정규화 TF-IDF':>12}")
        print(f"  {'-'*52}")
        for bg, pmi in sorted(filtered_bigrams.items(), key=lambda x: -x[1])[:15]:
            df_val = bigram_df_debug[bg]
            print(f"  {bg:<22} {pmi:>6.4f}  {df_val:>2}  →  {normalized_bigrams[bg]:>12.6f}")
    else:
        print("  ※ PMI 통과 bigram 없음")

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 2.5 · 외부 키워드 결합 (RDS rankings 기반 CASE A/B/C 분류)
    # ══════════════════════════════════════════════════════════════════════
    merged_tfidf, merged_per_review, keyword_meta = merge_keywords(
        place_id       = place_id,
        nlp_tfidf      = merged_tfidf,
        nlp_per_review = merged_per_review,
    )

    _sep("STAGE 2.5 · 외부 키워드 결합")
    summarize_merge_result(keyword_meta, merged_tfidf)

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

    _sep("STAGE 3 · 스코어링")
    print(f"  채점 키워드 수 : {len(scored)}개")
    print(f"\n  {'키워드':<18} {'최종':>6}  {'TF-IDF':>7}  {'감성':>6}  {'최신성':>6}  {'일관성':>6}")
    print(f"  {'-'*62}")
    for item in scored[:25]:
        b = item["breakdown"]
        print(
            f"  {item['keyword']:<18} {item['score']:>6.4f}  "
            f"{b['tfidf']:>7.4f}  {b['sentiment']:>6.4f}  "
            f"{b['recency']:>6.4f}  {b['consistency']:>6.4f}"
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
    formatted = attach_inducement(scored, top_n=20, use_similarity=True)

    # ── keyword_meta 결합 (STAGE 2.5 메타데이터 → formatted 각 항목에 주입) ──────
    # 유도어 결합형(is_induced=True): 마지막 토큰이 유도어이므로 제거해 원본 키워드 복원
    #   예: "파스타 맛집" → "파스타", "루프탑 뷰 맛집" → "루프탑 뷰"
    # 원본(is_induced=False): keyword 그대로 기준
    for item in formatted:
        base_kw = (
            " ".join(item["keyword"].split()[:-1])
            if item["is_induced"]
            else item["keyword"]
        )
        meta = keyword_meta.get(base_kw, {})
        item["case_type"]             = meta.get("case_type", "C")
        item["rank_no"]               = meta.get("rank_no")
        item["rank_no_change"]        = meta.get("rank_no_change", 0)
        item["monthly_search_volume"] = meta.get("monthly_search_volume", 0)
        item["mention_count"]         = meta.get("mention_count", 0)
        item["competition_level"]     = meta.get("competition_level", "낮음")
        item["is_opportunity"]        = meta.get("is_opportunity", False)

    _sep("STAGE 4 · 카테고리 태깅 + 유도어 결합")
    print(f"  입력 top-20 키워드 → 출력 {len(formatted)}개 (원본 + 유도어 결합형)")
    print(f"\n  {'키워드':<24} {'점수':>6}  {'카테고리':<8}  {'property':<14}  {'목적':<10}  ngram  induced  mapping")
    print(f"  {'-'*96}")
    for item in formatted:
        print(
            f"  {item['keyword']:<24} {item['base_score']:>6.4f}  "
            f"{item['category']:<8}  {item.get('property', ''):<14}  "
            f"{item['keyword_purpose']:<10}  "
            f"{'O' if item['is_ngram']   else 'X':^5}  "
            f"{'O' if item['is_induced'] else 'X':^7}  "
            f"{item.get('mapping_type', '')}"
        )

    # 미분류 키워드 별도 표시
    untagged = [it for it in formatted if not it["is_induced"] and it["category"] == "미분류"]
    if untagged:
        print(f"\n  ※ 미분류 키워드 {len(untagged)}개 (SemanticMapper Phase 2 대상):")
        for it in untagged:
            print(f"    - {it['keyword']}")

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 5 · DB upsert
    # ══════════════════════════════════════════════════════════════════════
    scored_map = {item["keyword"]: item["breakdown"] for item in scored}
    upserted   = upsert_recommend_keywords(place_id, formatted, scored_map)

    _sep(f"STAGE 5 · 완료")
    print(f"  place_id={place_id}  →  {upserted}개 키워드 DB 저장")


if __name__ == "__main__":
    create_recommend_keywords_table()  # 최초 1회만 실행 (테이블 없을 때)
    run(place_id=166)
