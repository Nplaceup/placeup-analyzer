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
USER_TYPE_THRESHOLDS = {
    "cold_start":   5,
    "early_growth": 50,
}

# ── 모듈별 블렌딩 가중치 ─────────────────────────────────────────────────────
MODULE_WEIGHTS: dict[str, dict[str, float]] = {
    "cold_start":   {"base": 0.30, "nlp": 0.00, "competitor": 0.70},
    "early_growth": {"base": 0.30, "nlp": 0.40, "competitor": 0.30},
    "active":       {"base": 0.10, "nlp": 0.70, "competitor": 0.20},
}

# ── 경쟁업체 분석 파라미터 ───────────────────────────────────────────────────
COMPETITOR_LIMIT     = 10
MIN_COMPETITOR_COUNT = 2

# ── CASE B 합성 점수 캡 ──────────────────────────────────────────────────────
CASE_B_SCORE_CAP = 0.7

# ── 블렌딩 최종 추출 수 ──────────────────────────────────────────────────────
BLEND_TOP_N = 30

# ── CASE B 순위 키워드 보장 슬롯 ─────────────────────────────────────────────
# 블렌딩 결과와 무관하게 순위 있는 CASE B 키워드를 최대 N개 강제 포함
# 나머지 (BLEND_TOP_N - CASE_B_GUARANTEED_TOP_N)개는 기존 블렌딩 결과로 채움
CASE_B_GUARANTEED_TOP_N = 5

# ── N-gram bigram 스킵 플래그 ─────────────────────────────────────────────────
USE_BIGRAM = False

# ── 모듈1 관련 상수 ───────────────────────────────────────────────────────────
RELATED_SCORE_CAP = 0.9
RELATED_TOP_N = 10
BASE_SCORE_THRESHOLD = 0.1