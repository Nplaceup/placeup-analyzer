# 리뷰 수 기반 사용자 유형 분류 + 모듈 블렌딩 가중치 반환.
# 경계값·가중치는 config.py에서 관리 (코드 변경 없이 튜닝 가능).

from app.core.config import USER_TYPE_THRESHOLDS, MODULE_WEIGHTS


def classify_user_type(review_count: int) -> str:
    """리뷰 수 → "cold_start" | "early_growth" | "active"."""
    if review_count <= USER_TYPE_THRESHOLDS["cold_start"]:
        return "cold_start"
    if review_count <= USER_TYPE_THRESHOLDS["early_growth"]:
        return "early_growth"
    return "active"


def get_module_weights(user_type: str) -> dict[str, float]:
    """유형별 블렌딩 가중치 반환. cold_start는 nlp=0.00 → main.py가 NLP 스킵."""
    return MODULE_WEIGHTS[user_type]
