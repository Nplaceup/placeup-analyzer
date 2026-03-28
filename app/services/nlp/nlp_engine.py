import pandas as pd
import re                               
import os
import html
import math
from app.core.config import STOPWORDS_PATH
from pathlib import Path
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
             return []  #파일 없어도 분석은 작동

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
            
            clean_text = self.clean_text(text)

            # 품사 태깅 ('먹었어요' -> '먹다' 원형 복원)
            pos_result = self.okt.pos(clean_text, stem=True)

            # 의미 있는 품사(명사, 형용사)만 추출하고 불용어 제거
            keywords = [
                word for word, pos in pos_result 
                if pos in ['Noun', 'Adjective']  
                and word not in self.stopwords   
                and len(word) > 1                
            ]
            return Counter(keywords)             # 키워드 빈도 반환 (ex. "유명한" : 3, "주차장" : 1)

    def analyze_reviews(self, reviews):
        
        #   [reviews] => [{"id}, 6088, "content": "..."}, ...]
        #   [반환 형태] => {"total_keywords": Counter, "per_review": {id: Counter}, "tfidf": {word: score}}
        
        per_review = {}

        # 모든 리뷰에서 각 id와 content를 분리 추출, 리뷰별 키워드 추출/카운팅
        for review in reviews:
            review_id = review.id if hasattr(review, 'id') else review.get("id")
            content = review.content if hasattr(review, 'content') else review.get("content", "")
            per_review[review_id] = self.extract_keywords(content)

        # 전체 키워드 빈도 합산
        total_keywords = Counter()
        for counter in per_review.values():
             total_keywords += counter

        # TF-IDF 계산
        tfidf_scores = self._calculate_tfidf(per_review)

        return {
             "total_keywords" : total_keywords,
             "per_review" : per_review,
             "tfidf" : tfidf_scores
        }
    
    # 3. TF-IDF
    def _calculate_tfidf(self, per_review):
        
        #   TF = 특정 리뷰에서 단어 등장 횟수 / 해당 리뷰 전체 단어 수
        #   IDF = log(전체 리뷰 수 / 단어 등장한 리뷰 수)
        
        total_docs = len(per_review)

        if total_docs == 0:
             return {}
        
        doc_frequency = Counter()
        for counter in per_review.values():
            for word in counter.keys():
                doc_frequency[word] += 1

        tfidf_total = Counter()

        for counter in per_review.values():
            total_words_in_doc = sum(counter.values())      # 해당 리뷰 키워드의 개수
            if total_words_in_doc == 0:
                continue
            for word, count in counter.items():
                tf = count / total_words_in_doc
                idf = math.log(total_docs / doc_frequency[word])
                tfidf_total[word] += round(tf * idf, 4)
        
        return tfidf_total
