# STAGE 1 — 기본 전처리 전용
#
# 역할: 텍스트 정제만 담당
# 형태소 분석 + TF-IDF 계산은 review_tfidf_analyze.py에서 담당.

import re
import html
from app.core.config import STOPWORDS_PATH


class ReviewPreprocessor:
    def __init__(self):
        self.stopwords = self._load_stopwords()

    def _load_stopwords(self) -> list[str]:
        try:
            with open(STOPWORDS_PATH, "r", encoding="utf-8") as f:
                words = [line.strip() for line in f if line.strip()]
            print(f"불용어 {len(words)}개 로드 완료")
            return words
        except FileNotFoundError:
            print(f"경고: 불용어 파일을 찾을 수 없음 → {STOPWORDS_PATH}")
            return []

    def clean_text(self, text: str) -> str:
        """
        HTML 특수문자 복원 → 구분자 정리 → 한글·공백만 남기기 → 연속 공백 축소.
        """
        if not text:
            return ""

        text = html.unescape(text)
        text = text.replace("¶", " ")                  # 문장 구분자 공백 치환
        text = re.sub(r'[^가-힣\s]', ' ', text)        # 한글·공백 외 제거
        text = re.sub(r'\s+', ' ', text).strip()       # 연속 공백 축소

        return text
