# placeup-analyzer

네이버 플레이스 리뷰 및 순위 데이터를 분석하여 SEO 키워드를 추천하고, 플레이스 관리 점수와 운영 개선 피드백을 제공하는 데이터 파이프라인 서비스입니다.

---

## 주요 기능

- **키워드 추천**: 리뷰 텍스트 NLP 분석, 지역/업종 기반 키워드, 경쟁업체 데이터를 블렌딩하여 검색 최적화 키워드 추천
- **플레이스 관리 점수 산출**: 매장 정보 완성도 + 리뷰 품질을 기반으로 0~100점 점수화
- **운영 개선 피드백**: 점수 기반 + 리뷰 감성 분석 기반의 구체적인 개선 방향 제시
- **경쟁업체 분석**: 동일 업종/지역 경쟁 매장과의 키워드 갭 분석

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| 언어 | Python 3.11+ |
| 형태소 분석 | kiwipiepy (Kiwi) |
| TF-IDF | scikit-learn |
| 감성 분석 | KoELECTRA (`WhitePeak/bert-base-cased-Korean-sentiment`) |
| 의미 유사도 | SentenceTransformers (`snunlp/KR-SBERT-V40K-klueNLI-augSTS`) |
| DB | PostgreSQL (SQLAlchemy) |
| 메시징 | Redis |
| 환경 관리 | python-dotenv |

---

## 프로젝트 구조

```
placeup-analyzer/
├── main.py                          # 파이프라인 진입점 + Redis 큐 워커
├── app/
│   ├── core/
│   │   └── config.py                # 환경변수, 파이프라인 파라미터 설정
│   ├── data/
│   │   ├── blocklist.py             # 불용어 목록 (범용어, 리뷰 문체 노이즈 등)
│   │   ├── expression_dictionary.py # 표현 통일 사전 (예: 존맛 → 맛있다)
│   │   ├── semantic_dictionary.py   # 의미 태그 사전 (예: 육즙 → 맛/식감/풍미)
│   │   ├── inducement_dict.py       # 유도어 사전 (음식 카테고리: 맛집, 추천)
│   │   └── landmark_dict.py         # 랜드마크/역세권 사전 (모듈1 기본 키워드 생성용)
│   ├── db/
│   │   ├── database.py              # DB 엔진 및 세션 설정 (Read/Write 분리)
│   │   └── repository.py            # DB 조회/저장 함수 모음
│   ├── services/
│   │   ├── analysis/
│   │   │   ├── user_type_classifier.py    # 리뷰 수 기반 사용자 유형 분류
│   │   │   ├── base_keyword_generator.py  # 모듈1: 지역+업종 기반 기본 키워드 생성
│   │   │   ├── competitor_analyzer.py     # 모듈3: 경쟁업체 키워드 갭 분석
│   │   │   └── keyword_blender.py         # 모듈1/2/3 가중치 블렌딩
│   │   ├── nlp/
│   │   │   ├── nlp_preprocessing.py       # 텍스트 전처리 (특수문자, 이모지 제거)
│   │   │   ├── review_tfidf_analyze.py    # 형태소 분석 (Kiwi POS) + TF-IDF 계산
│   │   │   ├── keyword_normalizer.py      # 표현 통일 (expression_dictionary 기반)
│   │   │   ├── keyword_merger.py          # NLP 키워드 + 순위 데이터 결합 (CASE A/B/C)
│   │   │   ├── semantic_mapper.py         # SBERT 유사도 기반 의미 태그 매핑
│   │   │   ├── category_mapper.py         # keyword_purpose 결정 (search / marketing)
│   │   │   └── sentiment.py               # KoELECTRA 기반 감성 분석 (문장 단위)
│   │   └── scoring/
│   │       ├── keyword_scorer.py          # 키워드 복합 점수 계산
│   │       ├── place_scorer.py            # 플레이스 관리 점수 산출 (0~100)
│   │       ├── place_feedback.py          # 운영 개선 피드백 생성
│   │       └── place_summary.py           # 키워드 기반 플레이스 요약 생성
│   └── output/
│       └── keyword_formatter.py           # 의미 태깅 + 유도어 결합 + 최종 정렬
```

---

## 파이프라인 흐름

```
STAGE 0     DB 조회 (리뷰, 순위, 매장 정보)
              ↓
            사용자 유형 분류 (cold_start / early_growth / active)
              → 리뷰 수에 따라 모듈 가중치 자동 조정
              ↓
모듈 1      지역 + 업종 기반 기본 키워드 생성
              ↓
모듈 2      NLP 파이프라인  ← cold_start 시 스킵
            ├─ STAGE 1    형태소 분석 (Kiwi POS) → 리뷰별 Counter
            ├─ STAGE 1a   불용어 제거 + 표현 통일
            ├─ STAGE 1b   TF-IDF 계산
            ├─ STAGE 2    외부 순위 데이터 결합 (CASE A / B / C 분류)
            ├─ STAGE 2.5  KoELECTRA 감성 분석 (문장 단위, 배치 처리)
            └─ STAGE 3    키워드 복합 점수 산출 + 의미 태깅 + 유도어 확장
              ↓
모듈 3      경쟁업체 키워드 갭 분석
              ↓
            블렌딩  (모듈1 / 모듈2 / 모듈3 가중치 합산)
              ↓
STAGE 4     최종 키워드 정렬 (base_score 60% + 검색량 40%)
              ↓
            DB 저장 (recommend_keywords)
              ↓  ← round=2 에서만 실행
STAGE 5     플레이스 관리 점수 산출
STAGE 6     운영 개선 피드백 생성
STAGE 7     플레이스 분석 요약
              ↓
            Redis 결과 적재 → Spring Backend 전달
```

---

## 핵심 로직 상세

### 사용자 유형 분류

리뷰 수를 기준으로 유형을 나누고, 각 모듈의 가중치를 자동 조정합니다.

| 유형 | 조건 | base | nlp | competitor |
|------|------|------|-----|------------|
| cold_start | 리뷰 10개 미만 | 0.6 | 0.0 | 0.4 |
| early_growth | 리뷰 10~49개 | 0.3 | 0.4 | 0.3 |
| active | 리뷰 50개 이상 | 0.1 | 0.7 | 0.2 |

리뷰가 충분할수록 NLP 가중치가 높아지고, 초기 매장은 지역/업종 기반 기본 키워드에 더 의존합니다.

---

### CASE A / B / C 키워드 분류

외부 순위 데이터와 NLP 결과를 결합할 때 세 가지 케이스로 분류합니다.

| 케이스 | 조건 | 처리 방식 |
|--------|------|-----------|
| CASE A | NLP 추출 ∩ 순위 추적 | TF-IDF 점수 유지 + 순위/검색량 메타 결합 |
| CASE B | 순위 추적 전용 (리뷰 미언급) | 합성 점수 부여 `(1/rank) × log(vol+1)` |
| CASE C | NLP 추출 전용 (순위 없음) | TF-IDF 점수 그대로 사용 |

CASE B 키워드 중 상위 N개는 블렌딩 후 강제 삽입하여 검색량 높은 키워드 누락을 방지합니다.

---

### 키워드 복합 점수 (keywordScorer)

네 가지 지표를 가중 합산하여 최종 점수를 산출합니다.

| 지표 | 가중치 | 설명 |
|------|--------|------|
| TF-IDF | 40% | 리뷰 전체 대비 해당 매장에서의 키워드 중요도 |
| 감성 | 25% | KoELECTRA 문장 단위 감성 점수 (−1~1 → 0~1 정규화) |
| 최신성 | 20% | 최근 리뷰 언급 여부 (경과 개월 반비례 감쇠: `1/(1 + months × 0.1)`) |
| 일관성 | 15% | 여러 리뷰어가 독립적으로 언급한 비율 (`언급 리뷰 수 / 전체 리뷰 수`) |

---

### 감성 분석 (SentimentAnalyzer)

KoELECTRA 모델을 사용하며 세 가지 최적화가 적용되어 있습니다.

1. **문장 단위 분석**: Kiwi로 리뷰를 문장 단위로 분리한 뒤, 해당 키워드가 포함된 문장만 추론하여 키워드와 무관한 내용에 의한 감성 오염 방지
2. **배치 처리**: 전체 문장을 32개 단위로 묶어 한 번에 추론 (단건 N회 호출 제거)
3. **중복 문장 dedup**: 동일 문장이 여러 키워드에 매칭될 경우 1회만 추론 후 역매핑

모델과 Kiwi 인스턴스는 모듈 레벨 싱글톤으로 관리하여 중복 로드를 방지합니다.

---

### 유도어 결합 조건

`purpose=search` 키워드에 유도어("맛집", "추천")를 결합할 때 다음 조건 중 하나를 만족해야 합니다.

- `semantic_dictionary`에 직접 등록된 메뉴명인 경우
- 2명 이상의 리뷰어가 독립적으로 언급한 경우 (`mention_count >= 2`)

조건 미충족 시 원본 키워드만 반환합니다. 1회 언급 키워드에 유도어를 결합하면 신뢰도 낮은 조합이 생성되는 것을 방지합니다.

---

### 최종 점수 정렬

블렌딩 이후 최종 정렬 점수는 파이프라인 점수와 검색 수요를 함께 반영합니다.

```
최종 점수 = base_score × 0.6 + log(monthly_search_volume + 1) / log(200,001) × 0.4
```

---

## 연동 구조

```
Spring Backend
      ↓  {place_id, round} → analysis:queue 적재
    Redis
      ↓  brpop으로 작업 수신
placeup-analyzer (워커)
      ↓  파이프라인 실행 후 결과 → analysis:result:queue 적재
    Redis
      ↑  결과 수신
Spring Backend → 프론트 전달
```

### Round 구분

| Round | 실행 조건 | 전달 데이터 |
|-------|-----------|-------------|
| 1 | 최초 분석 요청 | 키워드 문자열 목록 (Spring이 순위 크롤링 후 round=2 재요청) |
| 2 | 순위 크롤링 완료 후 | 키워드 + score + 순위 + 검색량 + 경쟁도 + SEO 점수 + 피드백 |

---

## 플레이스 관리 점수

| 항목 | 배점 | 기준 |
|------|------|------|
| 매장 정보 완성도 | 40점 | 소개글, 메뉴, 사진 등록 여부 |
| 리뷰 품질 | 60점 | 리뷰 수, 일관성 점수, 키워드 다양성 |

| 점수 | 등급 |
|------|------|
| 80~100 | 🟢우수 |
| 60~79 | 🟡보통 |
| 40~59 | 🟠미흡 |
| 0~39 | 🔴취약 |

---

## 환경 변수

`.env.example`을 참고하여 `.env` 파일을 생성합니다.

```env
READ_DB_USER=
READ_DB_PASSWORD=
READ_DB_HOST=
READ_DB_PORT=
READ_DB_NAME=

WRITE_DB_USER=
WRITE_DB_PASSWORD=
WRITE_DB_HOST=
WRITE_DB_PORT=
WRITE_DB_NAME=
```

---

## 실행 방법

### 워커 실행 (Redis 큐 대기)

```bash
python main.py
```

### 단일 플레이스 직접 실행

```python
from main import run
run(place_id=128, round_no=1)
```

---

## 향후 발전 방향

- **ABSA(속성 기반 감성 분석) 도입**: 현재 문장 단위 이진 분류에서 맛/서비스/분위기 속성별 감성 분리로 고도화
- **검색 노출 피드백 루프**: 추천 키워드 적용 후 실제 네이버 플레이스 노출 순위 변화를 추적하여 파이프라인에 재반영
- **업종별 특화 설정**: semantic_dictionary, blocklist, scoring 가중치를 업종별로 분리 관리
- **실시간 파이프라인**: 리뷰 신규 등록 시 자동 갱신하는 이벤트 기반 구조 전환
