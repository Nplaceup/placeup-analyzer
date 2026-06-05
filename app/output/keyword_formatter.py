# STAGE 3.5 + STAGE 4: NLP 확장 → 최종 키워드 포맷
#
# ─ 변경 이력 ──────────────────────────────────────────────────────────────────
# v1: CATEGORY_DICT + INDUCEMENT_TEMPLATE 기반 (카테고리 단위 purpose 결정)
# v2: SemanticMapper + CategoryMapper 기반 (category + property 단위 purpose 결정)
# v3: 지역/업종 기반 키워드 결합 추가
# v4: 유도어 결합 → 모듈2 내부(STAGE 3.5)로 이동
#     - expand_nlp_keywords() : 모듈2 전용 — 메뉴 키워드 검색형 확장
#     - attach_inducement()   : 블렌딩 결과 포맷팅 전용 (유도어 재추가 없음)
#       NLP 항목(keyword_purpose 있음) → base_score 보완만
#       base / competitor 항목         → 의미 태깅 + 포맷
#
# ─ 파이프라인 위치 ────────────────────────────────────────────────────────────
# STAGE 3 → expand_nlp_keywords [STAGE 3.5] → blender → attach_inducement [STAGE 4]

from app.data.inducement_dict import get_inducements
from app.data.semantic_dictionary import get_semantic_tag, SemanticTag
from app.services.nlp.category_mapper import CategoryMapper
from app.services.nlp.semantic_mapper import SemanticMapper

_category_mapper = CategoryMapper()

# SemanticMapper는 SentenceTransformer 로딩 비용이 있으므로 모듈 수준 싱글턴
_semantic_mapper: SemanticMapper | None = None


def _get_semantic_mapper() -> SemanticMapper:
    global _semantic_mapper
    if _semantic_mapper is None:
        _semantic_mapper = SemanticMapper()
    return _semantic_mapper


# ── 카테고리 + property 태깅 ─────────────────────────────────────────────────
def _tag_semantic(keyword: str, use_similarity: bool = False) -> dict:
    """
    keyword → {category, property, mapping_type, similarity}

    1차: semantic_dictionary 직접 조회 (빠름)
    2차: use_similarity=True일 때 SentenceTransformer 유사도 fallback
    미등록 + similarity=False: category="미분류", property=""
    """
    tag: SemanticTag | None = get_semantic_tag(keyword)

    if tag is not None:
        return {
            "category":     tag.category,
            "property":     tag.property,
            "mapping_type": "dictionary",
            "similarity":   1.0,
        }

    if use_similarity:
        result = _get_semantic_mapper().tag(keyword)
        return {
            "category":     result["category"],
            "property":     result["property"],
            "mapping_type": result["mapping_type"],
            "similarity":   result["similarity"],
        }

    return {
        "category":     "미분류",
        "property":     "",
        "mapping_type": "unmapped",
        "similarity":   0.0,
    }


def _assign_purpose(category: str, prop: str) -> str:
    return _category_mapper.assign_purpose(
        {"category": category, "property": prop}
    )["keyword_purpose"]


# ── 모듈2 전용: 의미 태깅 + 메뉴 키워드 검색형 확장 (STAGE 3.5) ──────────────
def expand_nlp_keywords(
    scored: list[dict],
    use_similarity: bool = False,
    keyword_meta: dict | None = None,
) -> list[dict]:
    """
    STAGE 3 scorer 결과를 받아 의미 태깅 + 메뉴 키워드 검색형 유도어 확장.
    블렌더 투입 전에 호출 (모듈2 내부 전용).

    유도어 결합 조건 (OR):
      - semantic_dictionary 직접 매칭 (사전 등록 확실한 메뉴명)
      - mention_count >= 2 (2명 이상 리뷰어가 독립적으로 언급)
    위 조건 미충족 시 원본 키워드만 반환 (증폭 차단).

    Parameters
    ----------
    scored        : keywordScorer._calc_score() 반환값
    use_similarity: 미등록 키워드 SemanticMapper fallback 여부
    keyword_meta  : merge_keywords() 반환값 — mention_count 조회용

    Returns
    -------
    list[dict]  — 원본 scored 필드 + keyword_purpose / category / property /
                  mapping_type / is_induced 추가
    """
    result       = []
    keyword_meta = keyword_meta or {}

    for item in scored:
        kw = item["keyword"]

        tagged   = _tag_semantic(kw, use_similarity=use_similarity)
        category = tagged["category"]
        prop     = tagged["property"]
        purpose  = _assign_purpose(category, prop)

        base = {
            **item,
            "keyword_purpose": purpose,
            "category":        category,
            "property":        prop,
            "mapping_type":    tagged["mapping_type"],
            "is_induced":      False,
        }

        result.append({**base, "keyword": kw})

        if purpose == "search":
            is_dict_match  = tagged["mapping_type"] == "dictionary"
            mention_count  = keyword_meta.get(kw, {}).get("mention_count", 0)
            should_induce  = is_dict_match or mention_count >= 2

            if should_induce:
                for word in get_inducements(category, prop):
                    result.append({**base, "keyword": f"{kw} {word}", "is_induced": True})

    return result


# ── 블렌딩 결과 포맷팅 전용 (STAGE 4) ────────────────────────────────────────
def attach_inducement(
    blended: list[dict],
    top_n: int = 20,
    use_similarity: bool = False,
) -> list[dict]:
    """
    블렌딩 결과에서 상위 top_n개를 받아 최종 포맷 필드를 부착한다.
    유도어 추가는 하지 않음 — 이미 expand_nlp_keywords()에서 완료.

    - NLP 항목 (keyword_purpose 있음): base_score 보완
    - base / competitor 항목          : 의미 태깅 + 포맷 필드 부착

    Parameters
    ----------
    blended       : blend_keywords() 반환값
    top_n         : 처리할 상위 키워드 수
    use_similarity: base/competitor 미등록 키워드 SemanticMapper fallback 여부

    Returns
    -------
    list[dict]
        [
            {
                "keyword":         str,
                "base_score":      float,
                "is_induced":      bool,
                "keyword_purpose": str,
                "category":        str,
                "property":        str,
                "mapping_type":    str,
                ...  # 원본 메타데이터 보존
            },
            ...
        ]
    """
    result = []

    for item in blended[:top_n]:
        kw    = item["keyword"]
        score = item["score"]

        if "keyword_purpose" in item:
            # NLP 출처: expand_nlp_keywords()에서 이미 태깅/확장됨
            result.append({**item, "base_score": score})
        else:
            # base / competitor 출처: 의미 태깅 + 포맷 (유도어 추가 없음)
            tagged   = _tag_semantic(kw, use_similarity=use_similarity)
            category = tagged["category"]
            prop     = tagged["property"]
            source   = item.get("source", "")

            # 순위 기반·지역+업종 기반 키워드는 검색 의도가 명확 → 항상 search
            if source in ("ranked_b", "ranked_a", "base_related", "base_location"):
                purpose = "search"
            else:
                purpose = _assign_purpose(category, prop)

            result.append({
                **item,
                "base_score":      score,
                "is_induced":      False,
                "keyword_purpose": purpose,
                "category":        category,
                "property":        prop,
                "mapping_type":    tagged["mapping_type"],
            })

    return result
