# 모듈 블렌딩
#
# ─ 역할 ──────────────────────────────────────────────────────────────────────
# 모듈1(기본 키워드) / 모듈2(NLP) / 모듈3(경쟁업체)의 결과를
# 사용자 유형별 가중치로 합산해 최종 키워드 리스트를 생성한다.
#
# ─ 점수 합산 규칙 ────────────────────────────────────────────────────────────
# 1. 각 모듈 점수를 모듈 내 최대값으로 0~1 정규화
# 2. 정규화 점수 × 모듈 가중치 = 기여 점수
# 3. 동일 키워드가 복수 모듈에서 등장하면 기여 점수 합산 (source="multi")
# 4. 합산 점수 내림차순 정렬 → 상위 BLEND_TOP_N개 반환
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
    3개 모듈 결과를 가중치로 합산해 최종 키워드 리스트를 반환한다.

    Parameters
    ----------
    base_keywords : generate_base_keywords() 반환값
        [{"keyword", "score", "source": "base", "monthly_search_volume"}, ...]

    nlp_keywords : keywordScorer._calc_score() 반환값에 source 태그를 붙인 것
        [{"keyword", "score", "source": "nlp", "breakdown"}, ...]
        cold_start인 경우 빈 리스트.

    competitor_result : analyze_competitors() 반환값
        {
            "gap_keywords":      [...],   # blender 투입
            "rank_gap_keywords": [...],   # blender 투입
            ...                           # advantage/category_gap은 여기서 사용 안 함
        }

    weights : get_module_weights() 반환값
        {"base": float, "nlp": float, "competitor": float}

    top_n : 반환할 최대 키워드 수 (기본값 config.BLEND_TOP_N)

    Returns
    -------
    list[dict]  score 내림차순 정렬, 최대 top_n개
        [
            {
                "keyword":               str,
                "score":                 float,   # 최종 가중 합산 점수 (0~1)
                "source":                str,     # "base" | "nlp" | "competitor" | "multi"
                "monthly_search_volume": int,     # 있는 경우
                ...                               # 각 모듈의 원본 메타데이터 보존
            },
            ...
        ]
    """
    # 경쟁업체 투입 후보: gap + rank_gap 합산
    competitor_keywords: list[dict] = (
        competitor_result.get("gap_keywords", []) +
        competitor_result.get("rank_gap_keywords", [])
    )

    # 모듈별 (키워드 리스트, 가중치) 묶음
    modules = [
        (base_keywords,       weights.get("base",       0.0)),
        (nlp_keywords,        weights.get("nlp",        0.0)),
        (competitor_keywords, weights.get("competitor", 0.0)),
    ]

    # keyword → 누적 정보
    merged: dict[str, dict] = {}

    for kw_list, weight in modules:
        if not kw_list or weight == 0.0:
            continue

        # 모듈 내 정규화
        max_score = max(item["score"] for item in kw_list) or 1.0

        for item in kw_list:
            kw             = item["keyword"]
            weighted_score = round((item["score"] / max_score) * weight, 6)

            if kw not in merged:
                # 첫 등장: 원본 메타데이터 그대로 복사
                merged[kw] = {**item, "score": weighted_score}
            else:
                # 중복 등장: 점수 합산, source 갱신
                merged[kw]["score"] += weighted_score
                if merged[kw]["source"] != item.get("source"):
                    merged[kw]["source"] = "multi"
                # monthly_search_volume은 더 큰 값 유지
                prev_vol = merged[kw].get("monthly_search_volume", 0)
                curr_vol = item.get("monthly_search_volume", 0)
                if curr_vol > prev_vol:
                    merged[kw]["monthly_search_volume"] = curr_vol

    # score 최종 반올림
    for item in merged.values():
        item["score"] = round(item["score"], 4)

    return sorted(merged.values(), key=lambda x: -x["score"])[:top_n]
