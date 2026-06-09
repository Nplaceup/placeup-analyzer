import math
from collections import Counter

from app.services.nlp.review_tfidf_analyze import ReviewTfidfAnalyzer
from app.services.nlp.keyword_normalizer import KeywordNormalizer
from app.services.nlp.keyword_merger import merge_keywords, summarize_merge_result, get_competition_level, COMPETITION_THRESHOLDS
from app.services.nlp.sentiment import SentimentAnalyzer
from app.services.scoring.keyword_scorer import keywordScorer
from app.output.keyword_formatter import expand_nlp_keywords, attach_inducement

from app.services.analysis.user_type_classifier import classify_user_type, get_module_weights
from app.services.analysis.base_keyword_generator import generate_base_keywords
from app.services.analysis.competitor_analyzer import analyze_competitors
from app.services.analysis.keyword_blender import blend_keywords

from app.core.config import CASE_B_GUARANTEED_TOP_N
from app.data.blocklist import KEYWORD_BLOCKLIST

from app.db.repository import (
    get_reviews, get_review_dates, get_place_info,
    create_recommend_keywords_table, upsert_recommend_keywords,
    upsert_seo_result, get_keyword_monthly_search,
)
from app.services.scoring.place_scorer import PlaceScorer
from app.services.scoring.place_feedback import PlaceFeedback
from app.services.scoring.place_summary import PlaceSummary
from app.db.repository import get_recommend_keywords
import redis
import json
import time
import os

# ── Redis 연결 ──────────────────────────────────────────────────────────────
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=int(os.getenv("REDIS_DB", "0")),
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
    place_info   = get_place_info(place_id)

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
    # 모듈2 · NLP 파이프라인
    # ══════════════════════════════════════════════════════════════════════
    nlp_keywords:  list[dict] = []
    marketing_kws: list[dict] = []
    keyword_meta:  dict       = {}
    scored:        list[dict] = []

    if user_type == "cold_start":
        _sep("모듈2 · NLP 스킵 (cold_start — 리뷰 부족)")
        print(f"  리뷰 수 {len(reviews)}개 ≤ 기준치 → NLP 파이프라인 생략")
    else:

    # ── STAGE 1 · 형태소 분석 ────────────────────────────────────────────────
        analyzer   = ReviewTfidfAnalyzer()
        per_review = analyzer.extract_per_review(reviews)

        _sep("STAGE 1 · 형태소 분석 (Kiwi POS)")
        total_tokens_s1 = sum(sum(c.values()) for c in per_review.values())
        unique_kw_s1    = len(set(kw for c in per_review.values() for kw in c))
        print(f"  리뷰별 Counter 수  : {len(per_review)}개")
        print(f"  전체 토큰 수       : {total_tokens_s1}개")
        print(f"  고유 키워드 수     : {unique_kw_s1}개")
        all_s1: Counter = Counter()
        for c in per_review.values():
            all_s1.update(c)
        _print_counter_sample("전체 합산 키워드", all_s1, top=20)

        # ── STAGE 1a · 블랙리스트 필터 + 표현 통일 ──────────────────────────
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

        # ── STAGE 1b · TF-IDF ────────────────────────────────────────────────
        tfidf = analyzer.compute_tfidf(per_review_clean)

        _sep("STAGE 1b · TF-IDF")
        print(f"  TF-IDF 키워드 수 : {len(tfidf)}개")
        print(f"  score=0 키워드   : {sum(1 for v in tfidf.values() if v == 0.0)}개  "
              f"(df=N 인 경우 IDF=0, 정상)")
        print(f"\n  {'키워드':<18} {'TF-IDF':>8}")
        print(f"  {'-'*28}")
        for kw, score in sorted(tfidf.items(), key=lambda x: -x[1])[:20]:
            print(f"  {kw:<18} {score:>8.5f}")

        # ── STAGE 2 · 외부 키워드 결합 ──────────────────────────────────────
        merged_tfidf, merged_per_review, keyword_meta = merge_keywords(
            place_id       = place_id,
            nlp_tfidf      = dict(tfidf),
            nlp_per_review = per_review_clean,
        )

        _sep("STAGE 2 · 외부 키워드 결합")
        summarize_merge_result(keyword_meta, merged_tfidf)

        # ── STAGE 2.5 · 감성 분석 ────────────────────────────────────────────
        sentiment_analyzer = SentimentAnalyzer()
        sentiment_scores   = sentiment_analyzer.analyze(reviews, merged_per_review)

        _sep("STAGE 2.5 · 감성 분석")
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

        # ── STAGE 3 · 스코어링 ───────────────────────────────────────────────
        scorer = keywordScorer()
        scored = scorer._calc_score(
            tfidf        = merged_tfidf,
            per_review   = merged_per_review,
            review_dates = review_dates,
            sentiment    = sentiment_scores,
        )

        _sep("STAGE 3 · 스코어링")
        print(f"  채점 키워드 수 : {len(scored)}개")
        print(f"\n  {'키워드':<22} {'최종':>6}  {'TF-IDF':>7}  {'감성':>6}  {'최신성':>6}  {'일관성':>6}")
        print(f"  {'-'*66}")
        for item in scored[:25]:
            b = item["breakdown"]
            print(
                f"  {item['keyword']:<22} {item['score']:>6.4f}  "
                f"{b['tfidf']:>7.4f}  {b['sentiment']:>6.4f}  "
                f"{b['recency']:>6.4f}  {b['consistency']:>6.4f}"
            )

        expanded = expand_nlp_keywords(scored, use_similarity=True, keyword_meta=keyword_meta)

        # 이용방식(혼밥/혼술)은 다이닝 스타일 → 고유 메뉴보다 낮은 우선순위
        for item in expanded:
            if item.get("property") == "이용방식":
                item["score"] = round(item["score"] * 0.5, 4)

        nlp_keywords = [
            {**item, "source": "nlp"}
            for item in expanded
            if item.get("keyword_purpose") != "marketing"
        ]

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
        marketing_non_trivial = [it for it in marketing_kws if not it.get("is_induced") and it.get("category","미분류") != "미분류"]
        if marketing_non_trivial:
            print(f"\n  [마케팅 키워드] ({len(marketing_non_trivial)}개 → Redis 전달)")
            for it in sorted(marketing_non_trivial, key=lambda x: -x["score"]):
                print(f"    {it['keyword']:<15} {it['category']:<8}/{it.get('property',''):<15}  score={it['score']:.4f}")

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
        {"gap_keywords": [], "rank_gap_keywords": [], "advantage_keywords": [], "category_gap": {}, "competitor_count": 0}
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
    # 블렌딩 · 모듈1 + 모듈2 + 모듈3 가중치 합산
    # ══════════════════════════════════════════════════════════════════════
    blended = blend_keywords(
        base_keywords     = base_kws,
        nlp_keywords      = nlp_keywords,
        competitor_result = competitor_result,
        weights           = weights,
    )

    # CASE B: 순위 키워드를 상위 N개 보장 삽입 — 점수 = (1/rank_no) * log(vol+1)
    if keyword_meta:
        ranked_b_kws = sorted(
            [
                (kw, meta) for kw, meta in keyword_meta.items()
                if meta["case_type"] == "B" and meta.get("rank_no") is not None
            ],
            key=lambda x: x[1]["rank_no"],
        )[:CASE_B_GUARANTEED_TOP_N]

        blended_kw_set = {item["keyword"] for item in blended}
        forced_items   = []
        for kw, meta in ranked_b_kws:
            if kw not in blended_kw_set:
                rank_no = meta["rank_no"]
                vol     = meta["monthly_search_volume"]
                ranked_b_score = round((1.0 / rank_no) * math.log(vol + 1), 6)
                forced_items.append({
                    "keyword":               kw,
                    "score":                 ranked_b_score,
                    "source":                "ranked_b",
                    "monthly_search_volume": vol,
                })

        if forced_items:
            from app.core.config import BLEND_TOP_N
            blended = list(blended)
            combined = forced_items + blended
            combined.sort(key=lambda x: -x["score"])
            blended = combined[:BLEND_TOP_N]
            print(f"\n  [CASE B 강제 삽입] {len(forced_items)}개: "
                  + ", ".join(f"{item['keyword']}({keyword_meta[item['keyword']]['rank_no']}위, score={item['score']:.4f})"
                              for item in forced_items))

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
    # STAGE 4 · 의미 태깅 + 포맷팅 + 검색량 가중 최종 정렬
    # ══════════════════════════════════════════════════════════════════════
    formatted = attach_inducement(blended, top_n=len(blended), use_similarity=True)

    # keyword_meta 결합
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

    # ── 검색량 후조회 ──────────────────────────────────────────────────────
    zero_vol_kws = [item["keyword"] for item in formatted if not item.get("monthly_search_volume")]
    if zero_vol_kws:
        extra_volumes = get_keyword_monthly_search(zero_vol_kws)
        filled_count = 0
        for item in formatted:
            if not item.get("monthly_search_volume") and item["keyword"] in extra_volumes:
                vol = extra_volumes[item["keyword"]]
                item["monthly_search_volume"] = vol
                item["competition_level"]     = get_competition_level(vol)
                item["is_opportunity"]        = (
                    vol >= COMPETITION_THRESHOLDS["중간"]
                    and (item.get("rank_no") is None or item["rank_no"] > 10)
                )
                filled_count += 1
        print(f"\n  [검색량 후조회] 대상={len(zero_vol_kws)}개, 채워진 키워드={filled_count}개")

    # 검색량 가중 최종 정렬: base_score(60%) + vol_normalized(40%)
    _LOG_MAX_VOL = math.log(200_000 + 1)
    for item in formatted:
        vol = item.get("monthly_search_volume") or 0
        vol_norm = math.log(vol + 1) / _LOG_MAX_VOL
        item["base_score"] = round(item["base_score"] * 0.6 + vol_norm * 0.4, 4)
    formatted.sort(key=lambda x: -x["base_score"])

    _sep("STAGE 4 · 최종 키워드")
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

    scored_map = {item["keyword"]: item["breakdown"] for item in scored}
    upsert_recommend_keywords(place_id, formatted, scored_map)

    if round_no == 2:
        keywords        = get_recommend_keywords(place_id)
        place_scorer    = PlaceScorer()
        place_score_result   = place_scorer.calc_score(keywords, place_info, len(reviews))

        _sep("STAGE 5 · 플레이스 관리 점수 산출")
        print(f"  플레이스 관리 점수 : {place_score_result['total']}점  {place_score_result['grade']}")
        b = place_score_result["breakdown"]
        print(f"  매장 정보 완성도 : {b['place_completeness']:.1f} / 40")
        print(f"  리뷰 품질        : {b['review_quality']:.1f} / 60")

        place_feedback_gen = PlaceFeedback()
        feedback_result    = place_feedback_gen.generate(place_score_result, reviews, competitor_result)

        _sep("STAGE 6 · 플레이스 운영 개선 피드백 생성")
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

        place_summary_gen = PlaceSummary()
        summary_result    = place_summary_gen.generate(keywords)
        feedback_result["place_summary"] = summary_result["summary"]

        _sep("STAGE 7 · 플레이스 분석 요약")
        print(summary_result["text"])

        upsert_seo_result(place_id, place_score_result, feedback_result)

    # ── Redis 큐에 완료 알림 적재 ────────────────────────────────────────────
    if round_no == 1:
        # round=1: 키워드 목록만 전달 — Spring이 순위 크롤링 후 round=2 재요청
        result_data = {
            "place_id":                place_id,
            "round":                   1,
            "keywords":                [item["keyword"] for item in formatted],
            "base_keyword_candidates": [item["keyword"] for item in base_kws if item.get("keyword")],
        }
    else:
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
                    "keywordPurpose":      item.get("keyword_purpose", "search"),
                    "isInduced":           item.get("is_induced", False),
                }
                for item in formatted
            ],
            "marketingKeywords": [
                {
                    "keyword":  item["keyword"],
                    "category": item.get("category", ""),
                    "property": item.get("property", ""),
                    "score":    item["score"],
                }
                for item in marketing_kws
                if not item.get("is_induced", False)
                and item.get("category", "미분류") != "미분류"
            ],
            "seo": {
                "total":    place_score_result["total"],
                "grade":    place_score_result["grade"],
                "breakdown": {
                    "placeCompleteness": place_score_result["breakdown"]["place_completeness"],
                    "reviewQuality":     place_score_result["breakdown"]["review_quality"],
                },
            },
            "feedback": {
                "summary":            feedback_result["summary"],
                "seoFeedback":        feedback_result["seo_feedback"],
                "reviewFeedback":     feedback_result["review_feedback"],
                "competitorFeedback": feedback_result["competitor_feedback"],
            },
        }

    r.lpush(
        "analysis:result:queue",
        json.dumps(result_data, ensure_ascii=False)
    )
    print(f"\n[Redis] 결과 적재 완료 place_id={place_id}, round={round_no}, 키워드={len(formatted)}개")


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
    listen_queue()
