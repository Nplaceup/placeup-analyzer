# Layer 3 전용 — scoring 이후
# 역할: 키워드에 의미 태그 부여
#       사전 있음 → 즉시 반환
#       사전 없음 → 유사도 기반 fallback

from sentence_transformers import SentenceTransformer, util
from app.data.semantic_dictionary import SEMANTIC_DICTIONARY, SemanticTag, get_semantic_tag


class SemanticMapper:
    """
    scored keyword 하나를 받아 SemanticTag 부여.
    - 1차: semantic_dictionary 직접 조회
    - 2차: SentenceTransformer 유사도 기반 매핑
    - 실패: category="기타", property="미분류" 반환
    """

    def __init__(
        self,
        model_name: str = "snunlp/KR-SBERT-V40K-klueNLI-augSTS",
        threshold: float = 0.55
    ):
        self.threshold = threshold
        self.model = SentenceTransformer(model_name)

        # 비교 후보: 사전의 모든 키워드 (대표형만)
        # 동의어 포함 안 함 — Layer 2에서 이미 대표형으로 통일됨
        self.candidates = list(SEMANTIC_DICTIONARY.keys())
        self.candidate_embeddings = self.model.encode(
            self.candidates,
            convert_to_tensor=True
        )

    def tag(self, keyword: str) -> dict:
        """
        입력:  "육즙"
        출력:  {
                "keyword":      "육즙",
                "category":     "Product",
                "property":     "식감/풍미",
                "mapping_type": "dictionary" | "semantic" | "unmapped"
                "similarity":   1.0 | 0.0~1.0 | float
               }
        """

        # 1차: 사전 직접 조회
        tag: SemanticTag | None = get_semantic_tag(keyword)

        if tag is not None:
            return {
                "keyword":      keyword,
                "category":     tag.category,
                "property":     tag.property,
                "mapping_type": "dictionary",
                "similarity":   1.0
            }

        # 2차: 유사도 기반 fallback
        keyword_emb = self.model.encode(keyword, convert_to_tensor=True)
        similarities = util.cos_sim(keyword_emb, self.candidate_embeddings)[0]
        best_idx = int(similarities.argmax())
        best_score = float(similarities[best_idx])

        if best_score >= self.threshold:
            matched = self.candidates[best_idx]
            matched_tag = SEMANTIC_DICTIONARY[matched]
            return {
                "keyword":      keyword,
                "category":     matched_tag.category,
                "property":     matched_tag.property,
                "mapping_type": "semantic",
                "similarity":   round(best_score, 4)
            }

        # fallback 실패 (threshold 미달)
        return {
            "keyword":      keyword,
            "category":     "미분류",   # CategoryMapper.CATEGORY_DEFAULT 키와 통일
            "property":     "",
            "mapping_type": "unmapped",
            "similarity":   round(best_score, 4)
        }

    def tag_batch(self, scored_keywords: list[dict]) -> list[dict]:
        """
        팀원 _calc_score() 반환값을 그대로 받아 태그 부여.

        입력:
            [
                {"keyword": "육즙", "score": 0.82, "breakdown": {...}},
                ...
            ]
        출력:
            [
                {
                    "keyword":      "육즙",
                    "score":        0.82,
                    "breakdown":    {...},
                    "category":     "Product",
                    "property":     "식감/풍미",
                    "mapping_type": "dictionary",
                    "similarity":   1.0
                },
                ...
            ]
        """
        results = []

        for item in scored_keywords:
            tagged = self.tag(item["keyword"])
            results.append({
                **item,       # keyword, score, breakdown 그대로 유지
                **tagged      # category, property, mapping_type, similarity 추가
            })

        return results