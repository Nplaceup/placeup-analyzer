# Layer 2 전용 — pos_tagging 직후, TF-IDF 이전
# 역할: 표현 통일만. 의미 해석 없음. 정보 손실 없음.

from collections import Counter
from app.data.expression_dictionary import get_representative


class KeywordNormalizer:
    """
    토큰 리스트를 받아 대표형으로 교체.
    - 사전 있음 → 대표형으로 교체
    - 사전 없음 → 원형 그대로 통과 (절대 삭제 안 함)
    - 점수(count) 합산: 같은 대표형으로 묶이면 빈도 합산
    """

    def normalize(self, keyword_counter: Counter) -> Counter:
        """
        입력: Counter({"존맛": 3, "맛나다": 1, "친절하다": 2})
        출력: Counter({"맛있다": 4, "친절": 2})

        팀원 extract_keywords() 반환값을 그대로 받음.
        """
        normalized: Counter = Counter()

        for token, count in keyword_counter.items():
            representative = get_representative(token)
            normalized[representative] += count

        return normalized