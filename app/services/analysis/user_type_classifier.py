# 사용자 유형 분류
#
# ─ 역할 ──────────────────────────────────────────────────────────────────────
# 리뷰 수를 기반으로 사용자 유형을 분류하고,
# 유형별 모듈 블렌딩 가중치를 반환한다.
#
# ─ 유형 정의 ─────────────────────────────────────────────────────────────────
# cold_start   : 리뷰 수 ≤ USER_TYPE_THRESHOLDS["cold_start"]  (기본 5)
# early_growth : 리뷰 수 ≤ USER_TYPE_THRESHOLDS["early_growth"] (기본 50)
# active       : 그 외
#
# ─ 경계값·가중치 출처 ────────────────────────────────────────────────────────
# app/core/config.py — USER_TYPE_THRESHOLDS, MODULE_WEIGHTS
# 코드 수정 없이 config만 변경해 파라미터 튜닝 가능.
#
# ─ 파이프라인 위치 ───────────────────────────────────────────────────────────
# STAGE 0 (reviews 조회) → [user_type_classifier] → main.py 분기

from app.core.config import USER_TYPE_THRESHOLDS, MODULE_WEIGHTS


def classify_user_type(review_count: int) -> str:
    """
    리뷰 수로 사용자 유형을 분류한다.

    Parameters
    ----------
    review_count : 매장의 총 리뷰 수

    Returns
    -------
    str  "cold_start" | "early_growth" | "active"
    """
    if review_count <= USER_TYPE_THRESHOLDS["cold_start"]:
        return "cold_start"
    if review_count <= USER_TYPE_THRESHOLDS["early_growth"]:
        return "early_growth"
    return "active"


def get_module_weights(user_type: str) -> dict[str, float]:
    """
    사용자 유형을 전달받아 해당하는 모듈 블렌딩 가중치를 반환한다.

    Parameters
    ----------
    user_type : classify_user_type() 반환값

    Returns
    -------
    dict  {"base": float, "nlp": float, "competitor": float}
          세 값의 합은 1.0.
          nlp=0.00인 cold_start는 main.py에서 NLP 파이프라인 자체를 스킵.

    Raises
    ------
    KeyError : 정의되지 않은 user_type 입력 시
    """
    return MODULE_WEIGHTS[user_type]
