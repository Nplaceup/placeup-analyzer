import re
import html
import json
from app.core.config import SENTIMENT_DICT_PATH

# 모듈 단위 캐시 — 인스턴스를 여러 번 생성해도 JSON을 한 번만 읽음
_SENTIMENT_CACHE: dict[str, int] | None = None


class SentimentAnalyzer:
    def __init__(self):
        self.sentiment_dict = self._load_sentiment_dict()

    # ── 사전 로드 ────────────────────────────────────────────────────────────
    def _load_sentiment_dict(self) -> dict[str, int]:
        """
        SentiWord JSON 로드: [{word, word_root, polarity}]
        → {단일토큰: polarity_int}

        인덱싱 규칙
        - word_root 우선: 단일 토큰이면 등록, 충돌 시 절댓값 큰 쪽 유지
        - word 보조: 단일 토큰이고 아직 없으면 등록
        - polarity == 0 항목 제외
        """
        global _SENTIMENT_CACHE
        if _SENTIMENT_CACHE is not None:
            return _SENTIMENT_CACHE

        try:
            with open(SENTIMENT_DICT_PATH, "r", encoding="utf-8") as f:
                raw: list[dict] = json.load(f)
        except FileNotFoundError:
            print(f"경고: 감성사전 파일을 찾을 수 없음 → {SENTIMENT_DICT_PATH}")
            _SENTIMENT_CACHE = {}
            return _SENTIMENT_CACHE

        result: dict[str, int] = {}
        for entry in raw:
            score = int(entry["polarity"])
            if score == 0:
                continue
            root = entry.get("word_root", "").strip()
            word = entry.get("word", "").strip()

            if root and " " not in root:
                if root not in result or abs(score) > abs(result[root]):
                    result[root] = score

            if word and " " not in word and word not in result:
                result[word] = score

        print(f"감성 사전 로드 완료 ({len(result)}개 항목)")
        _SENTIMENT_CACHE = result
        return _SENTIMENT_CACHE

    # ── 텍스트 정제 (ReviewPreprocessor 의존 없이 경량 처리) ─────────────────
    def _clean(self, text: str) -> str:
        text = html.unescape(text)
        text = text.replace("¶", " ")
        text = re.sub(r'[^가-힣\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    # ── 리뷰 단위 감성 점수 ──────────────────────────────────────────────────
    def analyze_review(self, text: str) -> float:
        """
        리뷰 텍스트 1개 → 감성 점수.
        정제 후 토큰 단위 polarity 평균 (매칭 어휘 없으면 0.0).

        반환 범위: -2.0 ~ 2.0
        """
        if not text:
            return 0.0
        tokens = self._clean(text).split()
        scores = [self.sentiment_dict[t] for t in tokens if t in self.sentiment_dict]
        return round(sum(scores) / len(scores), 4) if scores else 0.0

    # ── 키워드별 감성 집계 ───────────────────────────────────────────────────
    def analyze(
        self,
        reviews: list,
        per_review: dict[int, dict],
    ) -> dict[str, float]:
        """
        키워드별 감성 점수 집계.

        reviews     : [{"id": int, "content": str}, ...] 또는 ORM 객체 리스트
        per_review  : {review_id: Counter(keyword → count)}  ← extract_per_review() 결과
        반환        : {keyword: 리뷰 감성 점수의 빈도 가중 평균}
        """
        score_sum: dict[str, float] = {}
        weight_sum: dict[str, int] = {}

        for review in reviews:
            if isinstance(review, dict):
                review_id = review["id"]
                content   = review["content"]
            else:
                review_id = review.id
                content   = review.content

            review_score = self.analyze_review(content)
            counter = per_review.get(review_id, {})

            for keyword, count in counter.items():
                score_sum[keyword]  = score_sum.get(keyword, 0.0) + review_score * count
                weight_sum[keyword] = weight_sum.get(keyword, 0) + count

        return {
            kw: round(score_sum[kw] / weight_sum[kw], 4)
            for kw in score_sum
            if weight_sum[kw] > 0
        }

    # ── 단일 키워드 유틸 ─────────────────────────────────────────────────────
    def get_score(self, keyword: str) -> int:
        """키워드의 polarity 점수 반환 (사전에 없으면 0)."""
        return self.sentiment_dict.get(keyword, 0)

    def get_pos_neg(self, keyword: str) -> str:
        """키워드를 'positive' / 'negative' / 'neutral' 로 분류."""
        score = self.get_score(keyword)
        if score > 0:
            return "positive"
        if score < 0:
            return "negative"
        return "neutral"
