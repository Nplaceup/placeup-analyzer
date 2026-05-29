# Nplaceup 프로젝트 컨텍스트 핸드오프

> 새 대화에서 이 파일을 첨부하거나 전체 복사해서 시작하세요.

---

## 프로젝트 개요

**Nplaceup** — 네이버 플레이스 SEO 키워드 추천 파이프라인 (Python)

- 매장 리뷰 + 순위 데이터를 분석해 사장님에게 추천 키워드와 SEO 피드백 제공
- Backend(Spring) ↔ Python 파이프라인: **Redis 큐**로만 통신
- DB: 읽기용 RDS (크롤링 데이터) / 쓰기용 로컬 DB (분석 결과)

---

## 프로젝트 파일 구조

```
Nplaceup_Project/
├── main.py                          # 파이프라인 진입점 (Redis 수신 → 실행)
├── main_demo.py
├── app/
│   ├── core/config.py               # 환경변수, 상수 (CASE_B_SCORE_CAP=0.7, BLEND_TOP_N=30 등)
│   ├── data/
│   │   ├── semantic_dictionary.py   # keyword → SemanticTag(category, property) 사전
│   │   ├── inducement_dict.py       # 유도어 사전 (STAGE 4용)
│   │   ├── blocklist.py             # 불용어 목록
│   │   ├── category_dict.py
│   │   └── expression_dictionary.py
│   ├── db/
│   │   ├── database.py              # DB 연결
│   │   └── repository.py            # 전체 DB 접근 함수
│   ├── services/
│   │   ├── nlp/
│   │   │   ├── review_tfidf_analyze.py  # STAGE 1: 형태소분석 + TF-IDF
│   │   │   ├── keyword_normalizer.py    # STAGE 1a: 블랙리스트 + 표현 통일
│   │   │   ├── ngram.py                 # STAGE 2: N-gram PMI (현재 스킵)
│   │   │   ├── keyword_merger.py        # STAGE 2.5: rankings CASE A/B/C 병합
│   │   │   ├── category_mapper.py       # PURPOSE_RULES: (category,property) → search/marketing
│   │   │   ├── semantic_mapper.py       # SentenceTransformer 유사도 fallback
│   │   │   ├── nlp_preprocessing.py
│   │   │   └── sentiment.py
│   │   ├── analysis/
│   │   │   ├── base_keyword_generator.py  # 모듈1: place_info 기반 기본 키워드
│   │   │   ├── competitor_analyzer.py     # 모듈3: 경쟁업체 gap/역전 분석
│   │   │   ├── keyword_blender.py         # 모듈1+2+3 가중치 합산
│   │   │   └── user_type_classifier.py    # cold_start/early_growth/active 분류
│   │   └── scoring/
│   │       ├── keyword_scorer.py      # STAGE 3: 최종 점수 산출
│   │       ├── seo_scorer.py          # STAGE 6: SEO 점수
│   │       └── seo_feedback.py        # STAGE 7: SEO 피드백
│   └── output/
│       └── keyword_formatter.py       # STAGE 4: 의미 태깅 + 유도어 결합
```

---

## 전체 파이프라인 흐름

```
Redis 수신 (place_id)
  ↓
STAGE 0: DB 조회 (place_info, reviews, rankings)
  ↓
사용자 유형 분류 (cold_start ≤5 / early_growth ≤50 / active)
  ↓
┌─────────────┬────────────────────┬──────────────────┐
│   모듈1     │      모듈2         │     모듈3        │
│  base       │  NLP 파이프라인    │  competitor      │
│  키워드     │  리뷰 텍스트 분석  │  경쟁업체 분석   │
└─────────────┴────────────────────┴──────────────────┘
  ↓
keyword_blender: 가중치 합산 + 중복 제거
  ↓
STAGE 4: keyword_formatter (의미 태깅 + search/marketing 분류)
  ↓
STAGE 5: recommend_keywords DB upsert
  ↓
STAGE 6: seo_scorer (SEO 점수)
  ↓
STAGE 7: seo_feedback (모듈3 결과 참조, 재계산 없음)
  ↓
STAGE 8: seo_results DB upsert
  ↓
STAGE 9: Redis 완료 알림 적재
```

---

## 모듈별 역할 상세

### 모듈1 — base_keyword_generator (외부 검색 데이터)
cold_start 포함 전 유형 동작. 검증된 search 키워드 생성.

생성 패턴:
- `{동} {term}`, `{구} {term}` — category split("육류,고기요리" → ["육류","고기요리"])
- `{동/구} 맛집`, `{term} 맛집`
- `{동/구} 데이트`, `{동} 혼밥`, `{동} 회식` ← 신규
- 랜드마크 사전(`{구/동: [랜드마크]}`) → `{랜드마크} {term}`, `{랜드마크} 맛집` ← 신규
- **keyword_related 통합** ← 신규 (rankings 키워드의 네이버 연관검색어, 위치 필터 + top15, CAP=0.9)

점수: 검색량 있으면 정규화(vol/max_vol), 없으면 fallback(0.2~0.6)

### 모듈2 — NLP 파이프라인 (리뷰 텍스트 분석)
- STAGE 1: Okt 형태소분석 → 명사/형용사 추출
- STAGE 1a: blocklist 필터 + keyword_normalizer 표현 통일
- STAGE 1b: TF-IDF 계산
- STAGE 2: N-gram PMI — **USE_BIGRAM=False로 현재 스킵**
- STAGE 2.5: rankings CASE A/B/C 병합
  - CASE A: NLP ∩ rankings → NLP 점수 유지 + 순위 메타
  - CASE B: rankings only → 검색량 기반 합성 점수
  - CASE C: NLP only → NLP 점수 그대로
- STAGE 3: keyword_scorer (tfidf + 최신성 + 일관성, 감성은 구현 예정)

### 모듈3 — competitor_analyzer
- 동일 category + city 경쟁업체 top10 조회
- gap 키워드 (경쟁업체 리뷰 자주 등장, 우리 리뷰엔 없음)
- rankings 역전 키워드 (경쟁업체보다 순위 낮음)
- 카테고리 분포 비교 데이터 → **결과 객체로 보존 → STAGE 7에서 참조**

### STAGE 4 — keyword_formatter (재설계 완료, 미구현)
기존 유도어 결합 방식 폐기. 새 로직:
1. semantic 태깅 (_tag_semantic)
2. category="음식" + property="메뉴명/*" → `{동} {메뉴}`, `{구} {메뉴}` 생성 → **search**
   - 메뉴명/음료, 메뉴명/디저트는 place category="카페"일 때만 포함
3. 나머지 (맛/서비스/분위기 등) → **marketing** 그대로

---

## 핵심 상수 (config.py)

```python
USER_TYPE_THRESHOLDS = {"cold_start": 5, "early_growth": 50}

MODULE_WEIGHTS = {
    "cold_start":   {"base": 0.30, "nlp": 0.00, "competitor": 0.70},
    "early_growth": {"base": 0.30, "nlp": 0.40, "competitor": 0.30},
    "active":       {"base": 0.10, "nlp": 0.70, "competitor": 0.20},
}

CASE_B_SCORE_CAP  = 0.7   # rankings only 키워드 점수 상한
RELATED_SCORE_CAP = 0.9   # keyword_related 키워드 점수 상한 (신규, 미반영)
BLEND_TOP_N       = 30
COMPETITOR_LIMIT  = 10
USE_BIGRAM        = False
```

---

## 주요 DB 테이블

| 테이블 | 역할 |
|---|---|
| places | 매장 정보 (name, category, address) |
| reviews | 리뷰 원문 + 날짜 |
| rankings | 키워드별 순위 (crawl_date 기준 최신) |
| keywords | 키워드 마스터 (keyword_name: "강남맛집" 형태 붙여쓰기) |
| keyword_related | 특정 키워드의 네이버 연관검색어 + 검색량 + 경쟁도 |
| keyword_search_volumes | 키워드별 월간 검색량 |
| recommend_keywords | 분석 결과 추천 키워드 (쓰기용) |
| seo_results | SEO 점수 + 피드백 (쓰기용) |

---

## semantic_dictionary 구조

```python
SemanticTag(category, property)

category: 음식 / 맛 / 서비스 / 분위기 / 장소 / 미분류
property 예시:
  음식: 메뉴명/육류, 메뉴명/해산물, 메뉴명/면류, 메뉴명/밥류,
        메뉴명/국찌개, 메뉴명/음료, 메뉴명/디저트
  맛:   일반맛, 식감/풍미, 온도, 양
  서비스: 친절도, 속도, 전문성, 편의, 혼잡도, 가성비
  분위기: 감성, 뷰, 소음
  장소: 청결, 편의/주차, 편의/시설, 공간, 위치
```

---

## 현재 작업 중 — STAGE 4 튜닝 설계 (미구현)

### 확정된 설계 사항

| # | 항목 | 결정 내용 |
|---|---|---|
| 1 | 유도어 대폭 축소 | 음식→["맛집"] 1개만, 장소→["추천","핫플"] |
| 2 | NO_INDUCEMENT_PROPERTY 추가 | 메뉴명/음료, 메뉴명/디저트, 일반맛, 전문성, 편의, 혼잡도 |
| 3 | STAGE 4 재설계 | 유도어 결합 폐기 → marketing/search 소스 분리 |
| 4 | NLP 메뉴 키워드 | 지역+메뉴 조합으로 search 변환 |
| 5 | base: category split | "육류,고기요리" → 콤마 분리해서 각 term 조합 |
| 6 | base: 지역+상황 추가 | {동} 데이트/혼밥/회식 |
| 7 | base: 랜드마크 사전 | {구/동: [랜드마크 리스트]} 형태 |
| 8 | keyword_related | 모듈1에 흡수, 위치 필터+top15, CAP=0.9 |
| 9 | 블렌딩 중복 제거 | 동일 키워드 최고점 유지 + source 병합 |
| 10 | 모듈3 결과 재사용 | 한 번 계산 → STAGE 7에서 참조만 |

### 미결/보류 사항

| 항목 | 상태 |
|---|---|
| 문제5: 카테고리 정보 부족 | 팀원 semantic_dictionary 튜닝 확인 후 결정 |
| 감성 점수 (STAGE 3) | 구현 예정, 데이터 준비 필요 |
| 랜드마크 사전 실제 데이터 | 2차 확장으로 별도 작업 예정 |
| get_related_keywords_for_place() | repository.py에 추가 필요 (미구현) |

### 구현 대상 파일 목록

```
app/core/config.py             RELATED_SCORE_CAP = 0.9 추가
app/data/inducement_dict.py    유도어 축소 + NO_INDUCEMENT_PROPERTY 보강
app/data/landmark_dict.py      신규 생성 — {구/동: [랜드마크]}
app/db/repository.py           get_related_keywords_for_place() 추가
app/services/analysis/
  base_keyword_generator.py    category split + 상황어 + 랜드마크 + keyword_related
  keyword_blender.py           중복 제거 로직 추가
app/output/keyword_formatter.py  STAGE 4 재설계
```

---

## SEO 점수 설계 (논의 중)

rankings 실데이터 기반으로 "현재 얼마나 노출이 잘 되고 관리되는가" 측정.

### SEO 점수 항목 (가중치 미확정)

| 항목 | 가중치(안) | 설명 |
|---|---|---|
| 노출 규모 | 35% | Σ(검색량 × 순위가중치), 순위가중치: 1위=1.0 ~ 10위=0.1 |
| 상위 집중도 | 20% | 1~3위 키워드 수 / 전체 순위권 키워드 수 |
| 순위 관리 상태 | 15% | rank_no_change 기반 상승/하락 비율 |
| 기회 활용률 | 20% | is_opportunity 키워드 중 순위권 비율 |
| 경쟁 포지션 | 10% | 경쟁업체보다 순위 높은 키워드 비율 |

### 설계 결정 사항

- **제외**: 키워드 다양성 — 알고리즘 출력의 질을 측정하는 항목이지 SEO 성과가 아님
- **SEO 피드백으로 이동**: 마케팅 카테고리 균형, 키워드 패턴 커버리지
- **모듈3 결과 재사용**: competitor_analyzer 결과 객체를 STAGE 7에서 참조만 (재계산 없음)
- 가중치 확정 전 상태. 다음 대화에서 계속 논의 필요.

---

## 커밋 워크플로우

코드 수정 후 커밋 메시지 제안 → 수민이 직접 커밋.

## HTML 생성 규칙

HTML 파일은 별개 파일로 생성 (code 블록에 포함 금지).
현재 생성된 파일: `pipeline.html` (기존, STAGE 4 섹션 수정 완료), `pipeline_flow.html`, `pipeline_walkthrough.html`
