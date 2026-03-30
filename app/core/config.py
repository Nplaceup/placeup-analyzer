import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent  # app/ 기준

os.environ['JAVA_HOME'] = os.getenv('JAVA_HOME', '')

STOPWORDS_PATH = BASE_DIR / "data" / "stopwords.txt"
SENTIMENT_DICT_PATH = BASE_DIR / "data" / "SentiWord_info.json"

DB_URL = (
    f"postgresql://"
    f"{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}"
    f"/{os.getenv('DB_NAME')}"
)