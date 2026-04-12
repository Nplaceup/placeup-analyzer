import re
import os
import html
from app.core.config import STOPWORDS_PATH
from konlpy.tag import Okt
from collections import Counter


class ReviewAnalyzer:
    def __init__(self):
        self.okt = Okt()
        # 불용어 txt 불러오기
        self.stopwords = self._load_stopwords()

    def _load_stopwords(self):
        try:
            with open(STOPWORDS_PATH, "r", encoding="utf-8") as f:
                words = [line.strip() for line in f if line.strip()]
            print(f"불용어 {len(words)}개 로드 완료")
            return words
        except FileNotFoundError:
            print(f"경고 : 불용어 파일을 찾을 수 없음 -> {STOPWORDS_PATH}")
            return []  # 파일 없어도 분석은 작동

    # 1. 리뷰 전처리
    def clean_text(self, text):
        if not text:
            return ""

        text = html.unescape(text)
        # 문장 구분자 공백으로 치환
        text = text.replace("¶", " ")
        # 이모지 및 특수문자 제거 (한글, 공백만)
        text = re.sub(r'[^가-힣\s]', ' ', text)
        # 연속된 공백 축소
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    # 2. 형태소 분석
    def extract_keywords(self, text):
        # 예외처리 (빈텍스트, None, 숫자만 있는 경우 등)
        if not text or not isinstance(text, str):
            return Counter()

        clean = self.clean_text(text)

        # 품사 태깅 ('먹었어요' -> '먹다' 원형 복원)
        pos_result = self.okt.pos(clean, stem=True)

        # 의미 있는 품사(명사, 형용사)만 추출하고 불용어 제거
        keywords = [
            word for word, pos in pos_result
            if pos in ['Noun', 'Adjective']
            and word not in self.stopwords
            and len(word) > 1
        ]
        return Counter(keywords)  # 키워드 빈도 반환 (ex. "유명한" : 3, "주차장" : 1)
