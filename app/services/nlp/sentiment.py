import re
import html
from transformers import pipeline
from kiwipiepy import Kiwi

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
    # ── 텍스트 정제 ──────────────────────────────────────────────────────────
    def _clean(self, text: str) -> str:
        text = html.unescape(text)
        text = text.replace("¶", " ")
        text = re.sub(r'[^가-힣\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    # ── 키워드별 감성 집계 ───────────────────────────────────────────────────
    def analyze(
        self,
        reviews: list,
        per_review: dict[int, dict],
        batch_size: int = 32,
        debug: bool = False,
    ) -> dict[str, float]:
        """
        키워드별 감성 점수 집계 (키워드 포함 문장만 분석).
        reviews    : [{"id": int, "content": str}, ...] 또는 ORM 객체 리스트
        per_review : {review_id: Counter(keyword → count)}
        반환       : {keyword: 문장 단위 감성 점수의 빈도 가중 평균}
        """
        target_ids = set(per_review.keys())
        target_reviews = [
            r for r in reviews
            if (r["id"] if isinstance(r, dict) else r.id) in target_ids
        ]

        if not target_reviews:
            return {}

        kiwi = _get_kiwi()

        entries: list[tuple[str, int, str]] = []       # (kw, review_id, cleaned_sent)
        review_kw_counts: dict[tuple[str, int], int] = {}

        for r in target_reviews:
            review_id = r["id"] if isinstance(r, dict) else r.id
            content   = r["content"] if isinstance(r, dict) else r.content
            counter   = per_review.get(review_id, {})
            if not counter:
                continue

            keywords = list(counter.keys())
            sents = [s.text for s in kiwi.split_into_sents(content)]

            for sent_text in sents:
                matched = [kw for kw in keywords if kw in sent_text]
                if not matched:
                    continue
                cleaned = self._clean(sent_text)[:512]
                for kw in matched:
                    entries.append((kw, review_id, cleaned))
                    review_kw_counts.setdefault((kw, review_id), counter[kw])

        if not entries:
            return {}

        # 동일 문장이 여러 키워드에 매칭될 수 있으므로 유니크 텍스트만 추론
        koelectra    = _get_koelectra()
        unique_texts = list(dict.fromkeys(t for _, _, t in entries))
        text_score:  dict[str, float] = {}
        for i in range(0, len(unique_texts), batch_size):
            batch = unique_texts[i : i + batch_size]
            for text, res in zip(batch, koelectra(batch)):
                text_score[text] = res["score"] if res["label"] == "LABEL_1" else -res["score"]

        inferred = [text_score[t] for _, _, t in entries]

        # (kw, review_id) → 문장 점수 목록
        kw_review_sents: dict[tuple[str, int], list[float]] = {}
        for (kw, review_id, _), score in zip(entries, inferred):
            kw_review_sents.setdefault((kw, review_id), []).append(score)

        if debug:
            neg = sum(1 for s in inferred if s < 0)
            pos = sum(1 for s in inferred if s > 0)
            print(f"\n  [DEBUG 요약] 긍정 문장={pos}  부정 문장={neg}  전체={len(inferred)}")

            neg_kw: dict[str, int] = {}
            for (kw, _, _), score in zip(entries, inferred):
                if score < 0:
                    neg_kw[kw] = neg_kw.get(kw, 0) + 1
            if neg_kw:
                top_neg = sorted(neg_kw.items(), key=lambda x: -x[1])[:15]
                print(f"  [DEBUG 부정 문장 출현 키워드 top15]")
                for kw, cnt in top_neg:
                    print(f"    {kw:<15} {cnt}회")

        score_sum:  dict[str, float] = {}
        weight_sum: dict[str, int]   = {}

        for (kw, review_id), sent_scores in kw_review_sents.items():
            avg_score = sum(sent_scores) / len(sent_scores)
            count = review_kw_counts[(kw, review_id)]
            score_sum[kw]  = score_sum.get(kw, 0.0) + avg_score * count
            weight_sum[kw] = weight_sum.get(kw, 0) + count

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

