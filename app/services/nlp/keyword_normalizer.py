# POS 태깅 직후, TF-IDF 이전: 표현 통일만 담당 (의미 해석·정보 손실 없음)

from collections import Counter
from app.data.expression_dictionary import get_representative


class KeywordNormalizer:
    """Counter를 받아 대표형으로 교체. 미등록 토큰은 원형 통과. 동일 대표형 빈도 합산."""

    def normalize(self, keyword_counter: Counter) -> Counter:
        normalized: Counter = Counter()

        for token, count in keyword_counter.items():
            representative = get_representative(token)
            normalized[representative] += count

        return normalized