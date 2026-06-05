import re
import html
import json
from app.core.config import SENTIMENT_DICT_PATH
from transformers import pipeline
from kiwipiepy import Kiwi

_SENTIMENT_CACHE: dict[str, int] | None = None
_KIWI_INSTANCE: Kiwi | None = None


def _get_kiwi() -> Kiwi:
    """Kiwi 인스턴스 싱글톤 — 초기화 비용이 크므로 한 번만 생성."""
    global _KIWI_INSTANCE
    if _KIWI_INSTANCE is None:
        _KIWI_INSTANCE = Kiwi()
    return _KIWI_INSTANCE


class SentimentAnalyzer:
    def __init__(self):
        self.sentiment_dict = self._load_sentiment_dict()
        self._koelectra = pipeline(
            "text-classification",
            model="WhitePeak/bert-base-cased-Korean-sentiment"
        )

    # ── 사전 로드 ────────────────────────────────────────────────────────────
    def _load_sentiment_dict(self) -> dict[str, int]:
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

    # ── 텍스트 정제 ──────────────────────────────────────────────────────────
    def _clean(self, text: str) -> str:
        text = html.unescape(text)
        text = text.replace("¶", " ")
        text = re.sub(r'[^가-힣\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    # ── 단일 문장 감성분석기 호출 ─────────────────────────────────────────────
    def _score_sentence(self, sentence: str) -> float:
        result = self._koelectra(sentence[:512])[0]
        label = result["label"]
        score = result["score"]
        if label == "LABEL_1":   # positive
            return score
        else:                     # LABEL_0 = negative
            return -score

    # ── 리뷰 단위 감성 점수 ──────────────────────────────────────────────────
    def analyze_review(
        self,
        text: str,
        target_keywords: list[str] | None = None,
    ) -> float:
        """
        target_keywords 없음 → 기존 동작: 전체 텍스트를 KoELECTRA로 분석.
        target_keywords 있음 → Kiwi로 문장 분리 후,
                               키워드가 포함된 문장만 감성 분석해 평균 반환.
                               해당 문장이 없으면 0.0 반환.
        """
        if not text:
            return 0.0

        # ── 기존 동작 (하위 호환) ──────────────────────────────────────────
        if not target_keywords:
            return self._score_sentence(text)

        # ── 키워드 필터링 모드 ────────────────────────────────────────────
        kiwi = _get_kiwi()
        sentences = kiwi.split_into_sents(text)

        matched_scores: list[float] = []
        for sent in sentences:
            sent_text = sent.text
            # 키워드 중 하나라도 문장에 포함되면 분석 대상
            if any(kw in sent_text for kw in target_keywords):
                matched_scores.append(self._score_sentence(sent_text))

        if not matched_scores:
            return 0.0

        return round(sum(matched_scores) / len(matched_scores), 4)

    # ── 키워드별 감성 집계 ───────────────────────────────────────────────────
    def analyze(
        self,
        reviews: list,
        per_review: dict[int, dict],
    ) -> dict[str, float]:
        """
        키워드별 감성 점수 집계.
        reviews     : [{"id": int, "content": str}, ...] 또는 ORM 객체 리스트
        per_review  : {review_id: Counter(keyword → count)}
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
        return self.sentiment_dict.get(keyword, 0)

    def get_pos_neg(self, keyword: str) -> str:
        score = self.get_score(keyword)
        if score > 0:
            return "positive"
        if score < 0:
            return "negative"
        return "neutral"