from collections import Counter

# ── 파이프라인 모듈 ─────────────────────────────────────────────────────────
from app.services.nlp.nlp_preprocessing import ReviewPreprocessor         # STAGE 1  (clean_text 전처리)
from app.services.nlp.review_tfidf_analyze import ReviewTfidfAnalyzer     # STAGE 1  (형태소 분석) + STAGE 1b (TF-IDF)
from app.services.nlp.keyword_normalizer import KeywordNormalizer          # STAGE 1a (표현 통일)
from app.services.nlp.ngram import NgramExtractor                          # STAGE 2  (N-gram PMI)
from app.services.nlp.keyword_merger import merge_keywords, summarize_merge_result  # STAGE 2.5 (외부 키워드 결합)
from app.services.nlp.sentiment import SentimentAnalyzer                  # STAGE 2.7 (감성 분석)
from app.services.scoring.keyword_scorer import keywordScorer              # STAGE 3  (스코어링)
from app.output.keyword_formatter import expand_nlp_keywords, attach_inducement  # STAGE 3.5 / 4

# ── 분석 모듈 ───────────────────────────────────────────────────────────────
from app.services.analysis.user_type_classifier import classify_user_type, get_module_weights
from app.services.analysis.base_keyword_generator import generate_base_keywords   # 모듈1
from app.services.analysis.competitor_analyzer import analyze_competitors          # 모듈3
from app.services.analysis.keyword_blender import blend_keywords

# ── 파이프라인 제어 플래그 ───────────────────────────────────────────────────
from app.core.config import USE_BIGRAM

# ── 데이터 필터 ─────────────────────────────────────────────────────────────
from app.data.blocklist import KEYWORD_BLOCKLIST                           # STAGE 1a (범용어 제거)

# ── DB ─────────────────────────────────────────────────────────────────────
from app.db.repository import (
    get_reviews, get_review_dates, get_place_info,
    create_recommend_keywords_table, upsert_recommend_keywords,
    get_recommend_keywords,
    create_competitor_analysis_table, upsert_competitor_analysis,
    upsert_seo_result,
)
from app.services.scoring.place_scorer import PlaceScorer
from app.services.scoring.place_feedback import PlaceFeedback
from app.services.scoring.place_summary import PlaceSummary
import redis
import json
import time

# ── Redis 연결 ──────────────────────────────────────────────────────────────
r = redis.Redis(
    host='localhost',
    port=6379,
    db=0,
    socket_keepalive=True,
    socket_connect_timeout=5,
    retry_on_timeout=True,
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


def run(place_id: int, round_no: int = 1):

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 0 · DB 조회
    # ══════════════════════════════════════════════════════════════════════
    reviews      = get_reviews(place_id)
    review_dates = get_review_dates(place_id)
    place_info   = get_place_info(place_id)   # 지역/업종 컨텍스트

    if not reviews:
        print(f"[SKIP] place_id={place_id} 리뷰 없음")
        return

    _sep(f"STAGE 0 · DB 조회 — place_id={place_id}, round={round_no}")
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
    for review in reviews[:3]:
        body = review["content"][:60].replace("\n", " ")
        print(f"    id={review['id']} | {body}...")

    # ══════════════════════════════════════════════════════════════════════
    # 사용자 유형 분류 + 모듈1 (기본 키워드)
    # ══════════════════════════════════════════════════════════════════════
    user_type = classify_user_type(len(reviews))
    weights   = get_module_weights(user_type)
    base_kws  = generate_base_keywords(place_info, place_id=place_id, round_no=round_no) if place_info else []

    _sep(f"사용자 유형 분류 + 모듈1 · 기본 키워드")
    print(f"  사용자 유형    : {user_type}")
    print(f"  모듈 가중치    : base={weights['base']}  nlp={weights['nlp']}  competitor={weights['competitor']}")
    print(f"  기본 키워드    : {len(base_kws)}개")
    for item in base_kws[:10]:
        score_str = f"{item['score']:.4f}" if item["score"] is not None else "None"
        print(f"    {item['keyword']:<22} 검색량={item['monthly_search_volume']:>8,}  score={score_str}")

    # ══════════════════════════════════════════════════════════════════════
    # 모듈2 · NLP 파이프라인 (cold_start는 리뷰 부족으로 스킵)
    # STAGE 1 → 1a → 1b → 2 → 2.5 → 3
    # ══════════════════════════════════════════════════════════════════════
    nlp_keywords: list[dict] = []
    keyword_meta: dict       = {}
    scored:       list[dict] = []

    if user_type == "cold_start":
        _sep("모듈2 · NLP 스킵 (cold_start — 리뷰 부족)")
        print(f"  리뷰 수 {len(reviews)}개 ≤ 기준치 → NLP 파이프라인 생략")
    else:

    # ── STAGE 1 ───────────────────────────────────────────────────────────
    # ReviewTfidfAnalyzer: ReviewPreprocessor.clean_text → Okt POS 태깅
    # 반환: {review_id: Counter(keyword → count)}
    # ─────────────────────────────────────────────────────────────────────
        analyzer   = ReviewTfidfAnalyzer()
        per_review = analyzer.extract_per_review(reviews)

        _sep("STAGE 1 · 형태소 분석 (Okt POS)")
        total_tokens_s1 = sum(sum(c.values()) for c in per_review.values())
        unique_kw_s1    = len(set(kw for c in per_review.values() for kw in c))
        print(f"  리뷰별 Counter 수  : {len(per_review)}개")
        print(f"  전체 토큰 수       : {total_tokens_s1}개")
        print(f"  고유 키워드 수     : {unique_kw_s1}개")
        all_s1: Counter = Counter()
        for c in per_review.values():
            all_s1.update(c)
        _print_counter_sample("전체 합산 키워드", all_s1, top=20)

        # ── STAGE 1a ──────────────────────────────────────────────────────
        # KEYWORD_BLOCKLIST 필터 + KeywordNormalizer
        # ─────────────────────────────────────────────────────────────────
        normalizer = KeywordNormalizer()

        per_review_clean: dict[int, Counter] = {}
        blocklist_removed: Counter = Counter()
        for review_id, counter in per_review.items():
            removed   = Counter({kw: cnt for kw, cnt in counter.items()
                                 if kw in KEYWORD_BLOCKLIST})
            filtered  = Counter({kw: cnt for kw, cnt in counter.items()
                                 if kw not in KEYWORD_BLOCKLIST})
            blocklist_removed.update(removed)
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

        # ── STAGE 1b ──────────────────────────────────────────────────────
        tfidf = analyzer.compute_tfidf(per_review_clean)

        _sep("STAGE 1b · TF-IDF")
        print(f"  TF-IDF 키워드 수 : {len(tfidf)}개")
        print(f"  score=0 키워드   : {sum(1 for v in tfidf.values() if v == 0.0)}개  "
              f"(df=N 인 경우 IDF=0, 정상)")
        print(f"\n  {'키워드':<18} {'TF-IDF':>8}")
        print(f"  {'-'*28}")
        for kw, score in sorted(tfidf.items(), key=lambda x: -x[1])[:20]:
            print(f"  {kw:<18} {score:>8.5f}")

        # ── STAGE 2 ───────────────────────────────────────────────────────
        # N-gram PMI 필터링  (USE_BIGRAM=False 이면 전체 스킵)
        # ─────────────────────────────────────────────────────────────────
        if USE_BIGRAM:
            ngram_extractor    = NgramExtractor(analyzer)
            bigrams_per_review = ngram_extractor.extract_bigrams_per_review(reviews)

            unigram_counts: Counter = Counter()
            for counter in per_review.values():
                unigram_counts.update(counter)

            filtered_bigrams = ngram_extractor.compute_pmi(
                bigrams_per_review,
                unigram_counts,
                min_count=2,
                df_min=3,
                pmi_threshold=2.0,
            )

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

        else:
            # USE_BIGRAM = False → bigram 없이 TF-IDF 단어만 STAGE 2.5로 전달
            merged_tfidf: dict               = dict(tfidf)
            merged_per_review: dict[int, Counter] = per_review_clean

            _sep("STAGE 2 · N-gram PMI [SKIPPED]")
            print(f"  USE_BIGRAM=False — 슬라이딩 윈도우 오염 문제로 bigram 스킵")
            print(f"  STAGE 2.5 입력: TF-IDF 단어 {len(merged_tfidf)}개")

        # ── STAGE 2.5 ─────────────────────────────────────────────────────
        # 외부 키워드 결합 (RDS rankings 기반 CASE A/B/C 분류)
        # ─────────────────────────────────────────────────────────────────
        merged_tfidf, merged_per_review, keyword_meta = merge_keywords(
            place_id       = place_id,
            nlp_tfidf      = merged_tfidf,
            nlp_per_review = merged_per_review,
        )

        _sep("STAGE 2.5 · 외부 키워드 결합")
        summarize_merge_result(keyword_meta, merged_tfidf)

        # ── STAGE 2.7 ─────────────────────────────────────────────────────
        # 감성 분석: 키워드별 리뷰 감성 점수 집계
        # SentimentAnalyzer.analyze() → -2~2, scorer 입력 범위 -1~1 로 정규화
        # ─────────────────────────────────────────────────────────────────
        sentiment_analyzer = SentimentAnalyzer()
        raw_sentiment      = sentiment_analyzer.analyze(reviews, merged_per_review)
        sentiment_scores   = {kw: score / 2 for kw, score in raw_sentiment.items()}

        _sep("STAGE 2.7 · 감성 분석")
        matched = sum(1 for v in sentiment_scores.values() if v != 0.0)
        print(f"  감성 매칭 키워드 : {matched}개 / 전체 {len(sentiment_scores)}개")
        pos = sum(1 for v in sentiment_scores.values() if v > 0)
        neg = sum(1 for v in sentiment_scores.values() if v < 0)
        print(f"  긍정 {pos}개 / 부정 {neg}개 / 중립 {len(sentiment_scores) - pos - neg}개")
        print(f"\n  {'키워드':<18} {'감성(-1~1)':>10}")
        print(f"  {'-'*30}")
        for kw, sc in sorted(sentiment_scores.items(), key=lambda x: -abs(x[1]))[:15]:
            bar = "+" * int(sc * 5) if sc > 0 else "-" * int(abs(sc) * 5)
            print(f"  {kw:<18} {sc:>+8.4f}  {bar}")

        # ── STAGE 3 ───────────────────────────────────────────────────────
        # 스코어링
        # ─────────────────────────────────────────────────────────────────
        scorer = keywordScorer()
        scored = scorer._calc_score(
            tfidf        = merged_tfidf,
            per_review   = merged_per_review,
            review_dates = review_dates,
            sentiment    = sentiment_scores,
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

        # ── STAGE 3.5 ─────────────────────────────────────────────────────
        # 모듈2 전용: 의미 태깅 + 메뉴 키워드 검색형 유도어 확장
        # 메뉴 키워드(purpose=search)  → 원본 + 유도어 결합형 모두 블렌더 투입
        # 나머지       (purpose=marketing) → 원본만 블렌더 투입
        # ─────────────────────────────────────────────────────────────────
        expanded     = expand_nlp_keywords(scored, use_similarity=True)
        nlp_keywords = [{**item, "source": "nlp"} for item in expanded]

        _sep("STAGE 3.5 · NLP 키워드 의미 태깅 + 메뉴 검색형 확장")
        search_kws    = [it for it in expanded if it["keyword_purpose"] == "search"]
        marketing_kws = [it for it in expanded if it["keyword_purpose"] == "marketing"]
        induced_kws   = [it for it in expanded if it["is_induced"]]
        print(f"  원본 scored     : {len(scored)}개")
        print(f"  확장 후 총 키워드 : {len(expanded)}개  "
              f"(search={len(search_kws)}, marketing={len(marketing_kws)}, "
              f"induced={len(induced_kws)})")
        if induced_kws:
            print(f"\n  [유도어 결합형 샘플]")
            for it in induced_kws[:8]:
                print(f"    {it['keyword']:<28}  {it['category']}/{it['property']}")

    # ══════════════════════════════════════════════════════════════════════
    # 모듈3 · 경쟁업체 분석
    # ══════════════════════════════════════════════════════════════════════
    my_keywords = (
        {item["keyword"] for item in nlp_keywords}
        | {item["keyword"] for item in base_kws}
    )
    competitor_result = (
        analyze_competitors(place_id, place_info, my_keywords)
        if place_info else
        {"gap_keywords": [], "rank_gap_keywords": [], "advantage_keywords": [], "category_gap": {}, "competitor_count": 0, "competitor_names": []}
    )

    _sep("모듈3 · 경쟁업체 분석")
    print(f"  경쟁업체 수         : {competitor_result['competitor_count']}개")
    print(f"  gap_keywords        : {len(competitor_result['gap_keywords'])}개")
    print(f"  rank_gap_keywords   : {len(competitor_result['rank_gap_keywords'])}개")
    print(f"  advantage_keywords  : {len(competitor_result['advantage_keywords'])}개")
    if competitor_result["category_gap"]:
        print(f"  카테고리 갭:")
        for cat, v in competitor_result["category_gap"].items():
            print(f"    {cat:<6}  내={v['mine']}  경쟁업체평균={v['competitor_avg']}")

    # ══════════════════════════════════════════════════════════════════════
    # Round 1 early return — 블렌딩/스코어링/DB upsert 불필요
    # 세 모듈 키워드를 중복 없이 수집해 Spring에 전달 (크롤링 대상 목록)
    # ══════════════════════════════════════════════════════════════════════
    if round_no == 1:
        seen: set[str] = set()
        kw_list: list[str] = []
        for kw in (
            [item["keyword"] for item in base_kws]
            + [item["keyword"] for item in nlp_keywords]
            + [item["keyword"] for item in competitor_result.get("gap_keywords", [])]
            + [item["keyword"] for item in competitor_result.get("rank_gap_keywords", [])]
        ):
            if kw not in seen:
                kw_list.append(kw)
                seen.add(kw)

        r.lpush("analysis:result:queue", json.dumps({
            "place_id": place_id,
            "round":    1,
            "keywords": kw_list,
        }, ensure_ascii=False))
        print(f"\n[Redis] Round 1 키워드 목록 전달 완료 — place_id={place_id}, {len(kw_list)}개")
        return

    # ══════════════════════════════════════════════════════════════════════
    # 블렌딩 · 모듈1 + 모듈2 + 모듈3 가중치 합산
    # ══════════════════════════════════════════════════════════════════════
    blended = blend_keywords(
        base_keywords     = base_kws,
        nlp_keywords      = nlp_keywords,
        competitor_result = competitor_result,
        weights           = weights,
    )

    _sep("블렌딩 결과")
    print(f"  최종 키워드 수 : {len(blended)}개  (가중치: base={weights['base']} / nlp={weights['nlp']} / competitor={weights['competitor']})")
    print(f"\n  {'키워드':<24} {'score':>6}  {'source':<12}  {'검색량':>8}")
    print(f"  {'-'*58}")
    for item in blended[:20]:
        print(
            f"  {item['keyword']:<24} {item['score']:>6.4f}  "
            f"{item['source']:<12}  "
            f"{item.get('monthly_search_volume', 0):>8,}"
        )

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 4 · 카테고리 태깅 + 유도어 결합
    # ══════════════════════════════════════════════════════════════════════
    formatted = attach_inducement(blended, top_n=len(blended), use_similarity=True)

    # ── keyword_meta 결합 (NLP 키워드에만 STAGE 2.5 메타데이터 존재) ──────────
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
        item["monthly_search_volume"] = item.get("monthly_search_volume") or meta.get("monthly_search_volume", 0)
        item["mention_count"]         = meta.get("mention_count", 0)
        item["competition_level"]     = meta.get("competition_level", "낮음")
        item["is_opportunity"]        = meta.get("is_opportunity", False)

    _sep("STAGE 4 · 의미 태깅 + 포맷팅")
    print(f"  입력 {len(blended)}개 → 출력 {len(formatted)}개")
    print(f"\n  {'키워드':<24} {'점수':>6}  {'카테고리':<8}  {'목적':<10}  {'source':<12}  induced")
    print(f"  {'-'*82}")
    for item in formatted:
        print(
            f"  {item['keyword']:<24} {item['base_score']:>6.4f}  "
            f"{item['category']:<8}  {item['keyword_purpose']:<10}  "
            f"{item.get('source', ''):<12}  "
            f"{'O' if item['is_induced'] else 'X':^7}"
        )

    # ------------- STAGE 5. 로컬 DB upsert ────────────────────────────────
    scored_map = {item["keyword"]: item["breakdown"] for item in scored}
    upserted = upsert_recommend_keywords(place_id, formatted, scored_map)
    print(f"\n[완료] place_id={place_id} 키워드 {upserted}개 DB 저장")

    upsert_competitor_analysis(place_id, competitor_result)
    print(f"[완료] place_id={place_id} 경쟁업체 분석 결과 DB 저장")



    # ══════════════════════════════════════════════════════════════════════
    # STAGE 6 · SEO Score 산출 + 저장 (round=2에서만 의미 있음)
    # ══════════════════════════════════════════════════════════════════════
    seo_result      = None
    feedback_result = None

    if round_no == 2:
        keywords        = get_recommend_keywords(place_id)
        place_scorer    = PlaceScorer()
        place_score_result   = place_scorer.calc_score(keywords, place_info, len(reviews))

        _sep("STAGE 6 · 플레이스 관리 점수 산출")
        print(f"  플레이스 관리 점수 : {place_score_result['total']}점  {place_score_result['grade']}")
        b = place_score_result["breakdown"]
        print(f"  매장 정보 완성도 : {b['place_completeness']:.1f} / 40")
        print(f"  리뷰 품질        : {b['review_quality']:.1f} / 60")

        # ── STAGE 7 · 플레이스 운영 개선 피드백 생성 ──────────────────────
        place_feedback_gen = PlaceFeedback()
        feedback_result    = place_feedback_gen.generate(place_score_result, reviews, competitor_result)

        _sep("STAGE 7 · 플레이스 운영 개선 피드백 생성")
        print(f"  총평 : {feedback_result['summary']}")
        print(f"\n  [매장 정보 완성도 기반 피드백]")
        for fb in feedback_result['seo_feedback']:
            print(f"    · {fb}")
        print(f"\n  [리뷰 기반 피드백]")
        for fb in feedback_result['review_feedback']:
            print(f"    · {fb}")
        print(f"\n  [경쟁업체 기반 피드백]")
        for fb in feedback_result['competitor_feedback']:
            print(f"    · {fb}")

        # ── STAGE 8.5 · 플레이스 분석 요약 생성 ──────────────────────────
        # place_summary를 먼저 생성한 뒤 feedback_result에 추가해야
        # upsert_seo_result() 저장 시 place_summary가 포함됨
        place_summary_gen = PlaceSummary()
        summary_result    = place_summary_gen.generate(keywords)

        _sep("STAGE 8.5 · 플레이스 분석 요약")
        print(summary_result["text"])

        feedback_result["place_summary"] = summary_result["summary"]

        # ── STAGE 8 · seo_results 테이블에 저장 ───────────────────────────
        upsert_seo_result(place_id, place_score_result, feedback_result)

        _sep("STAGE 8 · 플레이스 관리 점수 저장 완료")
        print(f"  place_id={place_id} 플레이스 관리 점수 저장")

    # ══════════════════════════════════════════════════════════════════════
    # STAGE 9 · Redis 큐에 완료 알림 적재 (Round 2 전용)
    # Round 1은 모듈3 완료 직후 early return으로 이미 처리됨
    # ══════════════════════════════════════════════════════════════════════
    result_data = {
        "place_id": place_id,
        "round":    2,
        "keywords": [
            {
                "keyword":             item["keyword"],
                "score":               item["base_score"],
                "monthlySearchVolume": item.get("monthly_search_volume", 0),
                "rankNo":              item.get("rank_no"),
                "competitionLevel":    item.get("competition_level", "낮음"),
                "isOpportunity":       item.get("is_opportunity", False),
            }
            for item in formatted
        ],
        "competitor": {
            "count": competitor_result.get("competitor_count", 0),
            "names": competitor_result.get("competitor_names", []),
            "gapKeywords": [
                {
                    "keyword":             kw["keyword"],
                    "category":            kw.get("category", "미분류"),
                    "monthlySearchVolume": kw.get("monthly_search_volume", 0),
                    "competitorCount":     kw.get("competitor_count", 0),
                }
                for kw in competitor_result.get("gap_keywords", [])
            ],
            "rankGapKeywords": [
                {
                    "keyword":             kw["keyword"],
                    "category":            kw.get("category", "미분류"),
                    "monthlySearchVolume": kw.get("monthly_search_volume", 0),
                    "myRankNo":            kw.get("my_rank_no"),
                    "competitorAvgRank":   kw.get("competitor_avg_rank"),
                    "rankGap":             kw.get("rank_gap"),
                }
                for kw in competitor_result.get("rank_gap_keywords", [])
            ],
            "advantageKeywords": [
                {
                    "keyword":             kw["keyword"],
                    "monthlySearchVolume": kw.get("monthly_search_volume", 0),
                }
                for kw in competitor_result.get("advantage_keywords", [])
            ],
            "categoryGap": {
                cat: {
                    "mine":          v["mine"],
                    "competitorAvg": v["competitor_avg"],
                }
                for cat, v in competitor_result.get("category_gap", {}).items()
            },
        },
        "seo": {
            "total":    place_score_result["total"],
            "grade":    place_score_result["grade"],
            "breakdown": {
                "placeCompleteness": place_score_result["breakdown"]["place_completeness"],
                "reviewQuality":     place_score_result["breakdown"]["review_quality"],
            },
        },
        "feedback": {
            "summary":           feedback_result["summary"],
            "seoFeedback":       feedback_result["seo_feedback"],
            "reviewFeedback":    feedback_result["review_feedback"],
            "competitorFeedback":feedback_result["competitor_feedback"],
        },
    }

    r.lpush(
        "analysis:result:queue",
        json.dumps(result_data, ensure_ascii=False)
    )
    print(f"\n[Redis] Round 2 결과 적재 완료 — place_id={place_id}, 키워드={len(formatted)}개")


def listen_queue():
    """Backend가 큐에 넣은 작업을 대기하며 처리"""
    print("[Worker] 분석 큐 대기 중...")
    while True:
        try:
            _, data = r.brpop("analysis:queue")
            payload  = json.loads(data)
            place_id = payload["place_id"]
            round_no = payload.get("round", 1)
            print(f"[Worker] place_id={place_id}, round={round_no} 분석 시작")
            try:
                run(place_id, round_no)
            except Exception as e:
                print(f"[Worker] 분석 실패 place_id={place_id}, round={round_no}, error={e}")
                r.lpush(
                    "analysis:result:queue",
                    json.dumps({
                        "place_id": place_id,
                        "round":    round_no,
                        "keywords": [],
                        "error":    str(e)
                    }, ensure_ascii=False)
                )
        except Exception as e:
            print(f"[Worker] 큐 오류: {e}")
            time.sleep(3)


if __name__ == "__main__":
    create_recommend_keywords_table()
    create_competitor_analysis_table()
    listen_queue()