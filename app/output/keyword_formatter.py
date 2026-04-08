# scored에 있는 최종 키워드들의 상위 n개를 추출하여, 유도형 키워드를 결합 -> 검색형 키워드로 포맷팅
from app.data.category_dict import CATEGORY_DICT, INDUCEMENT_TEMPLATE, FALLBACK


# ── 카테고리 태깅 ───────────────────────────────────────────────────────────────
def _tag_category(keyword: str) -> str | None:
    """
    키워드(1-gram 또는 bigram)를 CATEGORY_DICT와 대조하여 카테고리 반환.
    bigram("루프탑 뷰")은 각 토큰을 분리하여 하나라도 매칭되면 해당 카테고리로 분류.
    여러 카테고리에 매칭될 경우 CATEGORY_DICT 선언 순서 우선.
    매칭 없으면 None → 호출부에서 FALLBACK 처리.
    """
    parts = keyword.split()
    for category, word_set in CATEGORY_DICT.items():
        if any(part in word_set for part in parts):
            return category
    return None


# ── 유도어 결합 (메인 함수) ─────────────────────────────────────────────────────
def attach_inducement(scored: list[dict], top_n: int = 20) -> list[dict]:
    """
    scorer._calc_score() 결과에서 상위 top_n개를 받아
    카테고리 분류 → 유도어 결합 → 최종 키워드 리스트 반환.

    Parameters
    ----------
    scored : list[dict]
        keywordScorer._calc_score() 반환값
        [{"keyword": str, "score": float, "breakdown": dict}, ...]
    top_n : int
        처리할 상위 키워드 수 (기본 20개)

    Returns
    -------
    list[dict]
        [
            {
                "keyword":          str,    # 키워드 (원본 or 유도어 결합형)
                "base_score":       float,  # 기반 점수 (원본 score 그대로 상속)
                "is_ngram":         bool,   # 공백 포함 여부 (bigram 또는 유도어 결합)
                "is_induced":       bool,   # 유도어 결합 여부
                "keyword_purpose":  str,    # "search" | "marketing"
                "category":         str,    # 분류 카테고리 ("미분류" 포함)
            },
            ...
        ]
    """
    result = []

    for item in scored[:top_n]:
        kw    = item["keyword"]
        score = item["score"]

        # 1단계: 카테고리 태깅
        category = _tag_category(kw)
        template = INDUCEMENT_TEMPLATE.get(category, FALLBACK) if category else FALLBACK

        purpose     = template["purpose"]
        inducements = template["inducements"]

        # 2단계: 원본 키워드 행 추가
        result.append({
            "keyword":         kw,
            "base_score":      score,
            "is_ngram":        " " in kw,
            "is_induced":      False,
            "keyword_purpose": purpose,
            "category":        category if category else "미분류",
        })

        # 3단계: 유도어 결합 행 추가 (search 카테고리만)
        for word in inducements:
            result.append({
                "keyword":         f"{kw} {word}",
                "base_score":      score,
                "is_ngram":        True,
                "is_induced":      True,
                "keyword_purpose": "search",
                "category":        category if category else "미분류",
            })

    return result
