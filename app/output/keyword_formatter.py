# STAGE 4: 유도어 결합 → 최종 키워드 포맷
#
# ─ 변경 이력 ──────────────────────────────────────────────────────────────────
# v1: CATEGORY_DICT + INDUCEMENT_TEMPLATE 기반 (카테고리 단위 purpose 결정)
# v2: SemanticMapper + CategoryMapper 기반 (category + property 단위 purpose 결정)
#     - 사전 직접 조회 → 유사도 fallback (SemanticMapper)
#     - PURPOSE_RULES[(category, property)] → purpose (CategoryMapper)
#     - 유도어 결합 대상·목록은 inducement_dict.py에서 관리
# v3: 지역/업종 기반 키워드 결합 추가
#     - attach_inducement(place_context=...) → 지역·업종 토큰 결합
#
# ─ 파이프라인 위치 ────────────────────────────────────────────────────────────
# STAGE 3 (keyword_scorer) → [STAGE 4] → STAGE 5 (DB upsert)

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


# ── 유도어 결합 (메인 함수) ─────────────────────────────────────────────────────
def attach_inducement(
    scored: list[dict],
    top_n: int = 20,
    use_similarity: bool = False,
) -> list[dict]:
    """
    STAGE 3 scorer 결과에서 상위 top_n개를 받아
    의미 태깅 → purpose 결정 → 유도어 결합 → 최종 키워드 리스트 반환.

    ※ 지역/업종 기반 키워드 결합은 STAGE 2.5 (keyword_merger.py) 담당.
       RDS rankings 데이터 기반 CASE A/B/C 로직으로 처리.
       결합 순서: "{지역/업종} {keyword}" (예: "강남 파스타", "이탈리안 맛집")

    Parameters
    ----------
    scored : list[dict]
        KeywordScorer._calc_score() 반환값
        [{"keyword": str, "score": float, "breakdown": dict, ...}, ...]
    top_n : int
        처리할 상위 키워드 수 (기본 20개)
    use_similarity : bool
        True면 미등록 키워드에 SentenceTransformer 유사도 fallback 적용.

    Returns
    -------
    list[dict]
        [
            {
                "keyword":          str,    # 원본 or 유도어 결합형
                "base_score":       float,  # 원본 score 상속
                "is_ngram":         bool,   # 공백 포함 여부
                "is_induced":       bool,   # 유도어 결합 여부
                "keyword_purpose":  str,    # "search" | "marketing"
                "category":         str,    # 의미 카테고리
                "property":         str,    # 세부 속성
                "mapping_type":     str,    # "dictionary" | "semantic" | "unmapped"
            },
            ...
        ]
    """
    result = []

    for item in scored[:top_n]:
        kw    = item["keyword"]
        score = item["score"]

        # 1단계: 의미 태깅 (category + property)
        tagged   = _tag_semantic(kw, use_similarity=use_similarity)
        category = tagged["category"]
        prop     = tagged["property"]

        # 2단계: purpose 결정 (CategoryMapper.PURPOSE_RULES)
        purpose = _category_mapper.assign_purpose({
            "category": category,
            "property": prop,
        })["keyword_purpose"]

        # 공통 베이스 필드
        base = {
            "base_score":      score,
            "is_induced":      False,
            "keyword_purpose": purpose,
            "category":        category,
            "property":        prop,
            "mapping_type":    tagged["mapping_type"],
        }

        # 3단계: 원본 키워드 행
        result.append({**base, "keyword": kw, "is_ngram": " " in kw})

        # 4단계: 유도어 결합 (purpose=search인 경우만)
        if purpose == "search":
            for word in get_inducements(category, prop):
                result.append({
                    **base,
                    "keyword":    f"{kw} {word}",
                    "is_ngram":   True,
                    "is_induced": True,
                })

    return result
