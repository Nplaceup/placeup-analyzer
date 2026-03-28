import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent  # app/ 기준

STOPWORDS_PATH = BASE_DIR / "data" / "stopwords.txt"
SENTIMENT_DICT_PATH = BASE_DIR / "data" / "sentiment_dict.txt"