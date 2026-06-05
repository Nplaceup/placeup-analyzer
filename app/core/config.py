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
# 임시값 — 검증 후 업종별 최적화 예정
USER_TYPE_THRESHOLDS = {
    "cold_start":   5,   # 리뷰 수 ≤ 5  → cold_start
    "early_growth": 50,  # 리뷰 수 ≤ 50 → early_growth
    # 초과 → "active"
}

# ── 모듈별 블렌딩 가중치 ─────────────────────────────────────────────────────
# 임시값 — 검증 후 조정 예정
# nlp 가중치가 0.00인 cold_start는 NLP 파이프라인 자체를 스킵
MODULE_WEIGHTS: dict[str, dict[str, float]] = {
    "cold_start":   {"base": 0.50, "nlp": 0.00, "competitor": 0.50},
    "early_growth": {"base": 0.40, "nlp": 0.25, "competitor": 0.35},
    "active":       {"base": 0.35, "nlp": 0.40, "competitor": 0.25},
}

# ── 경쟁업체 분석 파라미터 ───────────────────────────────────────────────────
COMPETITOR_LIMIT     = 10  # 리뷰수 내림차순 상위 N개 경쟁업체 선택
MIN_COMPETITOR_COUNT = 2   # 갭/순위역전 키워드 인정 최소 등장 업체 수

# ── CASE B 합성 점수 캡 ──────────────────────────────────────────────────────
# 순위만 있는 키워드가 NLP 키워드를 밀어내지 않도록 상한 적용
CASE_B_SCORE_CAP = 0.7

# ── 블렌딩 최종 추출 수 ──────────────────────────────────────────────────────
BLEND_TOP_N = 30

# ── N-gram bigram 스킵 플래그 ─────────────────────────────────────────────────
# 슬라이딩 윈도우 방식이 의미 없는 복합 표현을 생성하는 오염 문제로 임시 비활성화
# True  → PMI 필터 bigram을 STAGE 2에서 파이프라인에 포함
# False → STAGE 2 전체 스킵, TF-IDF 단어만으로 STAGE 2.5 진입
USE_BIGRAM = False

# ── 모듈1 관련 상수 ───────────────────────────────────────────────────────────
# keyword_related 키워드 점수 상한 (검색량 정규화 후 이 값을 곱해 캡 적용)
RELATED_SCORE_CAP = 0.9

# keyword_related 위치 필터 top N
RELATED_TOP_N = 10

# Round 2에서 검색량 기반 정규화 점수 하한 — 미만이면 탈락
BASE_SCORE_THRESHOLD = 0.1