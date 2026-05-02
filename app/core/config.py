import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Nplaceup/ 기준

# RDS & 로컬 db 모두 .env 하나로 관리
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

os.environ['JAVA_HOME'] = os.getenv('JAVA_HOME', '')

APP_DIR = BASE_DIR / "app"
STOPWORDS_PATH = APP_DIR / "data" / "stopwords.txt"
SENTIMENT_DICT_PATH = APP_DIR / "data" / "SentiWord_info.json"

# 읽기용 - RDS (크롤링 데이터)
READ_DB_URL = (
    f"postgresql://"
    f"{os.getenv('READ_DB_USER')}:{os.getenv('READ_DB_PASSWORD')}"
    f"@{os.getenv('READ_DB_HOST')}:{os.getenv('READ_DB_PORT')}"
    f"/{os.getenv('READ_DB_NAME')}"
)

# 쓰기용 - 로컬 DB (분석 결과 적재)
WRITE_DB_URL = (
    f"postgresql://"
    f"{os.getenv('WRITE_DB_USER')}:{os.getenv('WRITE_DB_PASSWORD')}"
    f"@{os.getenv('WRITE_DB_HOST')}:{os.getenv('WRITE_DB_PORT')}"
    f"/{os.getenv('WRITE_DB_NAME')}"
)


# ── 사용자 유형 분류 경계값 ──────────────────────────────────────────────────
# 리뷰 수 기반으로 cold_start / early_growth / active 분류
# 임시값 — precision@K 검증 후 업종별 최적화 예정
USER_TYPE_THRESHOLDS = {
    "cold_start":   5,   # 리뷰 수 ≤ 5  → cold_start
    "early_growth": 50,  # 리뷰 수 ≤ 50 → early_growth
    # 초과 → "active"
}

# ── 모듈별 블렌딩 가중치 ─────────────────────────────────────────────────────
# 임시값 — precision@K 검증 후 조정 예정
# nlp 가중치가 0.00인 cold_start는 NLP 파이프라인 자체를 스킵
MODULE_WEIGHTS: dict[str, dict[str, float]] = {
    "cold_start":   {"base": 0.30, "nlp": 0.00, "competitor": 0.70},
    "early_growth": {"base": 0.30, "nlp": 0.40, "competitor": 0.30},
    "active":       {"base": 0.10, "nlp": 0.70, "competitor": 0.20},
}

# ── 경쟁업체 분석 파라미터 ───────────────────────────────────────────────────
COMPETITOR_LIMIT     = 20  # 비교할 최대 경쟁업체 수
MIN_COMPETITOR_COUNT = 2   # 갭/순위역전 키워드 인정 최소 등장 업체 수

# ── CASE B 합성 점수 캡 ──────────────────────────────────────────────────────
# 순위만 있는 키워드가 NLP 키워드를 밀어내지 않도록 상한 적용
CASE_B_SCORE_CAP = 0.7

# ── 블렌딩 최종 추출 수 ──────────────────────────────────────────────────────
BLEND_TOP_N = 30