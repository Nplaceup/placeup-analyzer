# 모듈 블렌딩
#
# ─ 역할 ──────────────────────────────────────────────────────────────────────
# 모듈1(기본 키워드) / 모듈2(NLP) / 모듈3(경쟁업체)의 결과를
# 사용자 유형별 가중치로 합산해 최종 키워드 리스트를 생성한다.
#
# ─ 점수 합산 규칙 ────────────────────────────────────────────────────────────
# 1. 각 모듈 점수를 모듈 내 최대값으로 0~1 정규화
# 2. 정규화 점수 × 모듈 가중치 = 기여 점수
# 3. 동일 키워드가 복수 모듈에서 등장하면 최고 기여 점수 유지 (source="multi")
# 4. 최고 점수 내림차순 정렬 → 상위 BLEND_TOP_N개 반환
#
# ─ 파이프라인 위치 ───────────────────────────────────────────────────────────
# 모듈1 / (모듈2) / 모듈3 → [keyword_blender] → STAGE 4 (attach_inducement)

from app.core.config import BLEND_TOP_N


def blend_keywords(
    base_keywords:     list[dict],
    nlp_keywords:      list[dict],
    competitor_result: dict,
    weights:           dict[str, float],
    top_n:             int = BLEND_TOP_N,
) -> list[dict]:
    """
    3개 모듈 결과를 가중치로 합산해 최종 키워드 리스트 반환.
    각 모듈 점수를 모듈 내 최대값으로 0~1 정규화 후 가중치 적용.
    동일 키워드 복수 등장 시 최고 기여 점수 유지 (source="multi").
    """
    competitor_keywords: list[dict] = (
        competitor_result.get("gap_keywords", []) +
        competitor_result.get("rank_gap_keywords", [])
    )

    modules = [
        (base_keywords,       weights.get("base",       0.0)),
        (nlp_keywords,        weights.get("nlp",        0.0)),
        (competitor_keywords, weights.get("competitor", 0.0)),
    ]

    merged: dict[str, dict] = {}

    for kw_list, weight in modules:
        if not kw_list or weight == 0.0:
            continue

        # round=1 base 키워드는 score=None → 0.0으로 처리
        valid_scores = [item["score"] for item in kw_list if item["score"] is not None]
        max_score = max(valid_scores) if valid_scores else 1.0
        if max_score == 0:
            max_score = 1.0

        for item in kw_list:
            kw             = item["keyword"]
            raw_score      = item["score"] if item["score"] is not None else 0.0
            weighted_score = round((raw_score / max_score) * weight, 6)

            if kw not in merged:
                merged[kw] = {**item, "score": weighted_score}
            else:
                # 중복 등장: 최고 점수 유지, monthly_search_volume은 더 큰 값 유지
                if weighted_score > merged[kw]["score"]:
                    merged[kw] = {**item, "score": weighted_score, "source": "multi"}
                else:
                    merged[kw]["source"] = "multi"
                prev_vol = merged[kw].get("monthly_search_volume", 0)
                curr_vol = item.get("monthly_search_volume", 0)
                if curr_vol > prev_vol:
                    merged[kw]["monthly_search_volume"] = curr_vol

    for item in merged.values():
        item["score"] = round(item["score"], 4)

    return sorted(merged.values(), key=lambda x: -x["score"])[:top_n]