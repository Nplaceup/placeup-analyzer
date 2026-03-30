import json
from pathlib import Path
from app.core.config import SENTIMENT_DICT_PATH


class SentimentAnalyzer:
    def __init__(self):
        self.sentiment_dict = self._load_sentiment_dict()
    
    def _load_sentiment_dict(self):
        """
            감정사전 JSON 파일 읽기
            [반환 형태] {"맛있다" : 2, "불친절" : -2, ...}
        """
        path = SENTIMENT_DICT_PATH
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                print("감성 사전 로드 완료")
                return data
        except FileNotFoundError:
            print(f"경고: 감성사전 파일을 찾을 수 없음 -> {path}")
            return {}

    def get_pos_neg(self, keyword):
        """ 긍정/부정으로 분류해서 반환"""
    
    def get_score(self, keyword):
        """ 하나의 키워드에 대한 점수 반환 (점수를 가중치로 변환)"""
    
    def analyze(self, keywords):
        """ 리뷰 키워드 전체 분석 """
    