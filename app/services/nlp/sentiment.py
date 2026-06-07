import re
import html
import json
from app.core.config import SENTIMENT_DICT_PATH
from transformers import pipeline
from kiwipiepy import Kiwi

_SENTIMENT_CACHE: dict[str, int] | None = None
_KIWI_INSTANCE:      Kiwi | None = None
_KOELECTRA_INSTANCE              = None


def _get_kiwi() -> Kiwi:
    """Kiwi 인스턴스 싱글톤 — 초기화 비용이 크므로 한 번만 생성."""
    global _KIWI_INSTANCE
    if _KIWI_INSTANCE is None:
        _KIWI_INSTANCE = Kiwi()
    return _KIWI_INSTANCE


def _get_koelectra():
    """KoELECTRA 싱글톤 — SentimentAnalyzer 복수 생성 시 모델 중복 로드 방지."""
    global _KOELECTRA_INSTANCE
    if _KOELECTRA_INSTANCE is None:
        _KOELECTRA_INSTANCE = pipeline(
            "text-classification",
            model="WhitePeak/bert-base-cased-Korean-sentiment",
        )
    return _KOELECTRA_INSTANCE


class SentimentAnalyzer:
    def __init__(self):
        self.sentiment_dict = self._load_sentiment_dict()

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
        result = _get_koelectra()(self._clean(sentence)[:512])[0]
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
        batch_size: int = 32,
    ) -> dict[str, float]:
        """
        키워드별 감성 점수 집계.
        reviews     : [{"id": int, "content": str}, ...] 또는 ORM 객체 리스트
        per_review  : {review_id: Counter(keyword → count)}
        반환        : {keyword: 리뷰 감성 점수의 빈도 가중 평균}

        per_review에 있는 리뷰만 배치 추론 — 전체 리뷰가 아닌 NLP 처리된 리뷰만 대상.
        """
        # per_review에 있는 리뷰만 추론 대상
        target_ids = set(per_review.keys())
        target_reviews = [
            r for r in reviews
            if (r["id"] if isinstance(r, dict) else r.id) in target_ids
        ]

        # 텍스트 정제 + (review_id, cleaned_text) 목록 구성
        id_text_pairs: list[tuple[int, str]] = []
        for r in target_reviews:
            review_id = r["id"] if isinstance(r, dict) else r.id
            content   = r["content"] if isinstance(r, dict) else r.content
            cleaned   = self._clean(content)[:512]
            id_text_pairs.append((review_id, cleaned))

        # 배치 추론
        koelectra = _get_koelectra()
        review_scores: dict[int, float] = {}
        for i in range(0, len(id_text_pairs), batch_size):
            batch = id_text_pairs[i : i + batch_size]
            texts = [t for _, t in batch]
            results = koelectra(texts)
            for (review_id, _), result in zip(batch, results):
                label = result["label"]
                score = result["score"]
                review_scores[review_id] = score if label == "LABEL_1" else -score

        score_sum: dict[str, float] = {}
        weight_sum: dict[str, int] = {}

        for review_id, review_score in review_scores.items():
            counter = per_review.get(review_id, {})
            for keyword, count in counter.items():
                score_sum[keyword]  = score_sum.get(keyword, 0.0) + review_score * count
                weight_sum[keyword] = weight_sum.get(keyword, 0) + count

        return {
            kw: round(score_sum[kw] / weight_sum[kw], 4)
            for kw in score_sum
            if weight_sum[kw] > 0
        }

    # ── 피드백용 배치 감성 분석 ──────────────────────────────────────────────
    def batch_analyze_by_keywords(
        self,
        reviews: list,
        keyword_groups: list[list[str]],
        batch_size: int = 32,
    ) -> list[float]:
        """
        여러 키워드 그룹에 대해 부정 감성 리뷰 비율을 배치로 계산.
        keyword_groups : [["주차"], ["웨이팅", "대기"], ...]
        반환           : 각 그룹의 (부정 리뷰 수 / 전체 리뷰 수)

        단건 4회 호출 대신 전체 문장을 한 번에 배치 추론해 속도 절감.
        """
        total = len(reviews)
        if total == 0 or not keyword_groups:
            return [0.0] * len(keyword_groups)

        kiwi = _get_kiwi()
        all_keywords = {kw for grp in keyword_groups for kw in grp}

        # 리뷰당 Kiwi 분리 1회 → 분리된 문장을 모든 그룹에 재사용
        entries: list[tuple[int, int, str]] = []  # (grp_idx, rev_idx, cleaned_sent)
        for rev_idx, r in enumerate(reviews):
            content = r["content"] if isinstance(r, dict) else r.content
            if not any(kw in content for kw in all_keywords):
                continue
            sents = [s.text for s in kiwi.split_into_sents(content)]
            for grp_idx, keywords in enumerate(keyword_groups):
                for sent_text in sents:
                    if any(kw in sent_text for kw in keywords):
                        entries.append((grp_idx, rev_idx, self._clean(sent_text)[:512]))

        if not entries:
            return [0.0] * len(keyword_groups)

        # 배치 추론
        koelectra = _get_koelectra()
        texts = [t for _, _, t in entries]
        inferred: list[float] = []
        for i in range(0, len(texts), batch_size):
            for res in koelectra(texts[i: i + batch_size]):
                s = res["score"] if res["label"] == "LABEL_1" else -res["score"]
                inferred.append(s)

        # (grp_idx, rev_idx) → 문장 점수 목록
        grp_rev_scores: dict[tuple[int, int], list[float]] = {}
        for (grp_idx, rev_idx, _), score in zip(entries, inferred):
            grp_rev_scores.setdefault((grp_idx, rev_idx), []).append(score)

        # 그룹별 부정 비율 (문장 평균 < -0.3 → 부정 리뷰)
        ratios: list[float] = []
        for grp_idx in range(len(keyword_groups)):
            negative_count = sum(
                1 for rev_idx in range(total)
                if (ss := grp_rev_scores.get((grp_idx, rev_idx)))
                and sum(ss) / len(ss) < -0.3
            )
            ratios.append(negative_count / total)

        return ratios

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