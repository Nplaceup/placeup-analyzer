import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # app/ 기준

# RDS & 로컬 db 모두 .env 하나로 관리
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

os.environ['JAVA_HOME'] = os.getenv('JAVA_HOME', '')

STOPWORDS_PATH = BASE_DIR / "data" / "stopwords.txt"
SENTIMENT_DICT_PATH = BASE_DIR / "data" / "SentiWord_info.json"

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