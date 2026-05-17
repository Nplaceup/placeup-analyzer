# Nplaceup · NLP 키워드 추천 파이프라인

네이버 플레이스 리뷰 텍스트를 분석해 매장별 검색 노출 개선에 유효한 키워드를 자동 추천하는 NLP 파이프라인

---

## 분석 파이프라인

```
리뷰 텍스트 (place_reviews)
       │
       ▼
  STAGE 1   형태소 분석 + TF-IDF        Okt POS 태깅 → 명사·형용사 추출 → TF-IDF 가중치 계산
  STAGE 1.5  텍스트 정제                 범용어 제거(blocklist) · 동의어 통일(synonym_dict)
  STAGE 2   N-gram 추출                 Bigram PMI 필터링 → TF-IDF 스케일 정규화 병합
  STAGE 2.5 외부 키워드 결합            플레이스 순위 데이터 + NLP 결과 → CASE A / B / C 분류 (진행중)
  STAGE 3   복합 스코어링               TF-IDF · 감성 · 최신성 · 일관성 가중 합산
  STAGE 4   키워드 포맷                 카테고리 분류(KR-SBERT) → 유도어 결합
  STAGE 5   DB 저장                     recommend_keywords 테이블 upsert
       │
       ▼
  추천 키워드 (recommend_keywords)
```

---

## 핵심 분석 방법론

### TF-IDF (STAGE 1)

리뷰 1개를 document 단위로 취급해 키워드 중요도를 산출합니다.

```
TF(t, d)  = count(t, d) / total_tokens(d)
IDF(t)    = log( N / (df(t) + 1) )
TF-IDF(t) = Σ TF(t, d) × IDF(t)
```

### Bigram PMI 필터링 (STAGE 2)

단어 시퀀스에서 슬라이딩 윈도우로 2-gram을 추출한 뒤 3단계 허들로 유의미한 복합어만 선별합니다.

```
PMI(w1, w2) = log2( P(w1,w2) / (P(w1) × P(w2)) )
```

| 허들 | 기준값 | 목적 |
|---|---|---|
| `min_count` | ≥ 2 | 희소 bigram 제거 |
| `df_min` | ≥ 3 | 단일 리뷰 반복 노이즈 제거 |
| `pmi_threshold` | > 1.0 | 우연 조합 대비 2배 이상 유의미한 복합어만 통과 |

PMI 값은 `(pmi / max_pmi) × max_tfidf` 로 정규화해 unigram 점수 스케일에 맞게 병합합니다.

### 외부 키워드 결합 — CASE A / B / C (STAGE 2.5)

NLP 추출 결과와 네이버 플레이스 실제 순위 데이터를 교집합 기준으로 3가지 케이스로 분류합니다.

| CASE | 조건 | 처리 방식 |
|---|---|---|
| A | NLP ∩ 순위 데이터 | NLP 점수 유지 + 순위 메타데이터 결합 |
| B | 순위 데이터 only | 검색량 기반 합성 점수 부여 (상한 70% cap) |
| C | NLP only | NLP 점수 그대로 유지 |

`is_opportunity` 플래그: 월간 검색량 ≥ 1,000 이고 현재 순위 10위 밖인 키워드를 기회 키워드로 자동 식별합니다.

### 복합 스코어링 (STAGE 3)

```
score = TF-IDF(0.40) + sentiment(0.25) + recency(0.20) + consistency(0.15)
```

| 지표 | 가중치 | 산출 방식 |
|---|---|---|
| TF-IDF | 40% | 정규화된 TF-IDF 점수 |
| sentiment | 25% | 감성 점수 −1-1 → 0-1 정규화 (미연동 시 기본값 1.0) |
| recency | 20% | 경과 개월 감쇠: `1 / (1 + months × 0.1)` |
| consistency | 15% | 언급 리뷰 수 / 전체 리뷰 수 |

### 카테고리 분류 및 유도어 결합 (STAGE 4)

1. `semantic_dictionary` 직접 조회
2. 미등록 키워드 → KR-SBERT 유사도 fallback (`SemanticMapper`, threshold=0.55)
3. `CategoryMapper` 로 `keyword_purpose` 결정 (`search` | `marketing`)
4. `search` 키워드에 `inducement_dict` 유도어 결합 (예: "파스타" → "파스타 맛집")

---

## 프로젝트 구조

```
app/
├── db/
│   ├── database.py              # ReadSession / WriteSession 분리
│   └── repository.py            # RDS 조회 · recommend_keywords upsert
├── data/                        # 정적 사전 데이터
│   ├── blocklist.py             # 범용어 목록
│   ├── synonym_dict.txt         # 동의어 → 대표형
│   ├── semantic_dictionary.py   # 키워드 → 카테고리 매핑
│   ├── inducement_dict.py       # 유도어 사전
│   └── SentiWord_info.json      # 감성 사전 (Phase 2 예정)
├── services/
│   ├── nlp/
│   │   ├── nlp_preprocessing.py    # 텍스트 전처리
│   │   ├── review_tfidf_analyze.py # 형태소 분석 · TF-IDF
│   │   ├── keyword_normalizer.py   # 동의어 정규화
│   │   ├── ngram.py                # Bigram PMI
│   │   ├── keyword_merger.py       # 외부 키워드 결합 (CASE A/B/C)
│   │   ├── semantic_mapper.py      # KR-SBERT 분류
│   │   └── category_mapper.py      # purpose 결정
│   └── scoring/
│       └── keyword_scorer.py       # 복합 점수 산출
└── output/
    └── keyword_formatter.py        # 유도어 결합 · 최종 포맷
```

---

## 출력 스키마 — `recommend_keywords`

| 컬럼 | 설명 |
|---|---|
| `keyword` | 최종 키워드 (유도어 결합형 포함) |
| `score` | 최종 복합 점수 |
| `tfidf_score` / `recency_score` / `consistency_score` | 지표별 점수 |
| `case_type` | A / B / C |
| `rank_no` / `rank_no_change` | 현재 순위 · 변동 |
| `monthly_search_volume` | 월간 검색량 |
| `competition_level` | 높음 / 중간 / 낮음 |
| `is_opportunity` | 기회 키워드 여부 |
| `category` / `keyword_purpose` | 의미 분류 결과 |

---

## 기술 스택

| 분류 | 사용 기술 |
|---|---|
| 형태소 분석 | KoNLPy (Okt) |
| 의미 유사도 | Sentence-Transformers (KR-SBERT) |
| DB | PostgreSQL · SQLAlchemy |
| 언어 | Python 3.11 |

---

## 향후 계획

- STAGE 3.5 의미 중복 키워드 병합 (`semantic_dedup`)
- 로직 튜닝을 통해 결과값 개선
- `get_keyword_trend()` · `get_competitor_ranks()` · `get_gap_keywords()` 구현
- FastAPI 엔드포인트 연동
- 감성 사전(`SentiWord_info.json`) 실연결
