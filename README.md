# placeup-analyzer

네이버 플레이스 리뷰 및 순위 데이터를 분석하여 SEO 키워드를 추천하고, SEO 점수와 피드백을 제공하는 데이터 파이프라인 서비스입니다.

---

## 주요 기능

- **키워드 추천**: 리뷰 텍스트, 지역/업종, 경쟁업체 데이터를 분석하여 검색 최적화 키워드 추천
- **SEO 점수 산출**: 플레이스 리뷰 품질, 매장 정보 완성도, 검색 노출 현황, 순위 관리 상태를 기반으로 사장님의 플레이스 관리 수준을 0~100점으로 점수화 (크롤링 데이터 확장 후 고도화 예정)
- **SEO 피드백 제공**: 점수 기반 + 리뷰 내용 기반의 구체적인 개선 방향 제시
- **경쟁업체 분석**: 동일 업종/지역 경쟁 매장과의 플레이스 관리 상태 비교 및 분석

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| 언어 | Python 3.11+ |
| NLP | KoNLPy (Okt), scikit-learn (TF-IDF) |
| 유사도 | SentenceTransformers (snunlp/KR-SBERT-V40K-klueNLI-augSTS) |
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
│   │   └── config.py                # 환경변수, 파라미터 설정
│   ├── data/
│   │   ├── blocklist.py             # 불용어 목록
│   │   ├── expression_dictionary.py # 표현 통일 사전 (존맛 → 맛있다)
│   │   ├── semantic_dictionary.py   # 의미 태그 사전 (육즙 → 맛/식감)
│   │   ├── category_dict.py         # 카테고리 사전 (하위 호환용)
│   │   ├── inducement_dict.py       # 유도어 사전 (맛집, 추천, 데이트 등)
│   │   └── demo_data.py             # 데모용 샘플 데이터
│   ├── db/
│   │   ├── database.py              # DB 엔진 및 세션 설정
│   │   └── repository.py            # DB 조회/저장 함수 모음
│   ├── services/
│   │   ├── analysis/
│   │   │   ├── base_keyword_generator.py  # 모듈1: 지역+업종 기반 키워드 생성
│   │   │   ├── competitor_analyzer.py     # 모듈3: 경쟁업체 키워드 분석
│   │   │   ├── keyword_blender.py         # 모듈1/2/3 가중치 합산 블렌딩
│   │   │   └── user_type_classifier.py    # 리뷰 수 기반 사용자 유형 분류
│   │   ├── nlp/
│   │   │   ├── nlp_preprocessing.py       # 텍스트 전처리 (특수문자, 이모지 제거)
│   │   │   ├── review_tfidf_analyze.py    # 형태소 분석 + TF-IDF 계산
│   │   │   ├── keyword_normalizer.py      # 표현 통일 (expression_dictionary 기반)
│   │   │   ├── keyword_merger.py          # STAGE 2.5: NLP + 순위 데이터 결합
│   │   │   ├── ngram.py                   # N-gram PMI 필터링
│   │   │   ├── semantic_mapper.py         # 유사도 기반 의미 태그 매핑
│   │   │   ├── category_mapper.py         # keyword_purpose 결정 (search/marketing)
│   │   │   └── sentiment.py               # 감성 분석 (Phase 2 연동 예정)
│   │   └── scoring/
│   │       ├── keyword_scorer.py          # 키워드 복합 점수 계산 (TF-IDF/감성/최신성/일관성)
│   │       ├── seo_scorer.py              # SEO 점수 산출 (0~100점)
│   │       ├── seo_feedback.py            # SEO 피드백 생성
│   │       └── test_seo_scorer.py         # SEO 점수 Mock 테스트
│   └── output/
│       └── keyword_formatter.py           # STAGE 4: 의미 태깅 + 유도어 결합
```

---

## 파이프라인 흐름

```
STAGE 0   DB 조회 (리뷰, 매장 정보)
            ↓
          사용자 유형 분류 (cold_start / early_growth / active)
            ↓
모듈1     지역+업종 기반 기본 키워드 생성
            ↓
모듈2     NLP 파이프라인 (cold_start 스킵)
          STAGE 1  형태소 분석 (Okt POS)
          STAGE 1a 불용어 제거 + 표현 통일
          STAGE 1b TF-IDF 계산
          STAGE 2  N-gram PMI (현재 비활성화)
          STAGE 2.5 외부 순위 데이터 결합 (CASE A/B/C)
          STAGE 3  키워드 복합 점수 산출
            ↓
모듈3     경쟁업체 키워드 분석
            ↓
          블렌딩 (모듈1/2/3 가중치 합산)
            ↓
STAGE 4   의미 태깅 + 유도어 결합
            ↓
STAGE 5   DB upsert (recommend_keywords)
            ↓
STAGE 6   SEO 점수 산출
            ↓
STAGE 7   SEO 피드백 생성
            ↓
STAGE 9   Redis 큐 적재 → 백엔드 전달
```

---

## 연동 구조

```
Spring Backend
      ↓ analysis:queue에 {place_id, round} 적재
    Redis
      ↓ brpop으로 작업 수신
placeup-analyzer (워커)
      ↓ 파이프라인 실행
      ↓ round 1: 키워드 문자열 목록 → analysis:result:queue 적재
      ↓ round 2: 키워드 + 순위/검색량 전체 데이터 → analysis:result:queue 적재
    Redis
      ↑ 결과 수신
Spring Backend → 프론트 전달
```

### Round 구분

| Round | 설명 | 전달 데이터 |
|-------|------|-------------|
| 1 | 1차 분석 (키워드 추출) | `place_id`, `round`, `keywords[]` (키워드 문자열 목록) |
| 2 | 2차 분석 (순위/검색량 포함) | `place_id`, `round`, `keywords[]` (키워드 + score + 순위 + 검색량 + 경쟁도) |

---

## 환경 변수 설명

| 변수 | 설명 |
|------|------|
| `READ_DB_*` | 크롤링 원본 데이터 읽기용 DB (PostgreSQL) |
| `WRITE_DB_*` | 분석 결과 저장용 로컬 DB (PostgreSQL) |
| `JAVA_HOME` | KoNLPy 형태소 분석기 실행을 위한 JDK 경로 |

`.env.example`을 참고하여 `.env` 파일 생성

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

JAVA_HOME=
```

---

## SEO 점수 구성

| 항목 | 계산 방식 | 사용 데이터 |
|------|-----------|-------------|
| 매장 정보 완성도 | 소개글, 사진, 메뉴 여부 | 크롤링 데이터 |
| 리뷰 품질 | 리뷰 일관성, 개수 등 | `score`, `consistency_score` |
| 노출 점수 | 같은 지역/업종 검색 시 매장 노출 등수 | 순위 데이터 |
| 순위 관리 상태 | 순위 변동 여부 | `rank_no_change` |

---

### 점수 등급

| 점수 | 등급 |
|------|------|
| 80~100 | 🟢 우수 |
| 60~79 | 🟡 보통 |
| 40~59 | 🟠 미흡 |
| 0~39 | 🔴 취약 |

---

## 향후 개발 예정

- **감성 분석 연동** (Phase 2): `sentiment.py` 기반 부정 리뷰 필터링으로 리뷰 기반 피드백 정확도 향상
- **경쟁업체 피드백 구현**: 경쟁 매장 대비 gap 기반 피드백 제공
- **사전 확장**: `expression_dictionary`, `semantic_dictionary` 지속 보완