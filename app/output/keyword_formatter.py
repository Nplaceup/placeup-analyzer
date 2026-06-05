# STAGE 3.5: expand_nlp_keywords — 의미 태깅 + 메뉴 키워드 유도어 확장 (블렌더 투입 전)
# STAGE 4:   attach_inducement   — 블렌딩 결과 포맷팅 (NLP 항목 base_score 보완, base/competitor 의미 태깅)

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
    의미 태깅 + 메뉴 키워드 유도어 확장 (블렌더 투입 전, 모듈2 전용).
    유도어 조건: 사전 직접 매칭 OR mention_count >= 2 — 미충족 시 원본만 반환.
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
    블렌딩 결과 상위 top_n개에 최종 포맷 필드 부착 (유도어 추가 없음).
    NLP 항목: base_score 보완 / base·competitor 항목: 의미 태깅 + 포맷 부착.
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
