# 세션 인수인계 — Nplaceup NLP 파이프라인
> 새 세션 시작 시 이 파일을 첨부하거나 내용을 붙여넣으세요.

---

## 프로젝트 위치
- **작업 폴더**: `Nplaceup_Project/`
- **진입점**: `main.py` → `run(place_id=167)`

---

## 현재까지 완료한 작업

### 코드 정리 (교수님 확인용)
| 파일 | 변경 내용 |
|------|-----------|
| `app/db/database.py` | `read_engine`이 `WRITE_DB_URL` 사용하던 버그 수정 → `READ_DB_URL`로 교체. 오타 "falied" × 2 수정 |
| `app/services/scoring/keyword_scorer.py` | 메서드 간 빈 줄, 정렬, 클래스 docstring 추가, `_calc_consistency` 단순화 |
| `app/services/nlp/ngram.py` | 오타 "extract_biagrams" 수정, trailing whitespace 제거, 클래스 docstring 추가 |
| `app/services/nlp/review_tfidf_analyze.py` | trailing whitespace 제거 |
| `app/db/repository.py` | 함수 간 trailing whitespace · 빈 줄 정리 |
| `app/services/nlp/keyword_merger.py` | 위치 확정: `app/services/nlp/` (main.py import 경로와 일치) |

### 생성된 문서
- `README.md` — 교수님 확인용 GitHub 리드미 (재작성 요청 중단된 상태, 아래 참고)
- `code_structure.html` — 인터랙티브 코드 구조 시각화 (5탭: 파이프라인/모듈/파일트리/DB/의존성)

---

## 마지막으로 하던 작업 (미완료)

**README.md 재작성** — "교수님 확인용 데이터 분석 파트 깃허브 레포지토리 리드미" 목적에 맞게 다시 써달라고 요청한 상태에서 세션 종료됨.

현재 `README.md`는 기술 문서 스타일. 아래 방향으로 재작성 필요:
- GitHub 레포 첫 화면에 걸맞는 구성 (뱃지, 간결한 도입, 시각적 구조)
- **데이터 분석** 관점 강조 (왜 이 방법론을 선택했는지, 설계 결정 근거)
- 교수님 대상 → 구현보다 **분석 설계·알고리즘 근거** 중심
- 한국어, 학술적이되 읽기 쉬운 톤

---

## 파이프라인 전체 구조

```
STAGE 0   DB 조회          place_reviews · keyword_place_ranks · keyword_search_volumes
STAGE 1   형태소 분석       Okt POS 태깅 → Noun/Adj Counter
STAGE 1a  정제             blocklist 56개 제거 · KeywordNormalizer 동의어 통일
STAGE 1b  TF-IDF           TF(t,d) = count/total, IDF = log(N/df+1)
STAGE 2   N-gram PMI        Bigram 슬라이딩 윈도우 → min_count/df_min/pmi_threshold 3단계 필터
           PMI 정규화       (pmi/max_pmi) × max_tfidf — bigram이 unigram 잠식 방지
STAGE 2.5 외부 키워드 결합  CASE A(NLP∩순위) / B(순위only, 70%캡) / C(NLP only)
           is_opportunity   검색량 ≥ 1,000 AND 순위 > 10
STAGE 3   스코어링          tfidf×0.4 + sentiment×0.25 + recency×0.2 + consistency×0.15
STAGE 3.5 유사도 매핑       (Sprint 3 예정) semantic_dedup
STAGE 4   포맷터            semantic_dict → SemanticMapper(SBERT, threshold=0.55) → CategoryMapper
           유도어 결합       purpose="search" 키워드에 inducement_dict 결합
STAGE 5   DB upsert         recommend_keywords 18컬럼 ON CONFLICT DO UPDATE
```

---

## 파일 구조 (현재 확정)

```
app/
├── core/config.py
├── db/
│   ├── database.py          ReadSession(READ_DB_URL) / WriteSession(WRITE_DB_URL)
│   └── repository.py        get_reviews, get_place_rankings, upsert_recommend_keywords 등
├── data/
│   ├── blocklist.py         범용어 56개
│   ├── synonym_dict.txt     동의어 사전
│   ├── inducement_dict.py   유도어 사전
│   ├── semantic_dictionary.py
│   ├── category_dict.py
│   └── SentiWord_info.json  감성 사전 (Phase 2)
├── services/
│   ├── nlp/
│   │   ├── nlp_preprocessing.py
│   │   ├── review_tfidf_analyze.py
│   │   ├── keyword_normalizer.py
│   │   ├── ngram.py
│   │   ├── keyword_merger.py   ← STAGE 2.5
│   │   ├── semantic_mapper.py
│   │   ├── category_mapper.py
│   │   └── sentiment.py
│   └── scoring/
│       └── keyword_scorer.py
└── output/
    └── keyword_formatter.py
```

---

## recommend_keywords 테이블 (18컬럼)

기존 11컬럼 + Sprint 2 신규 7컬럼 (ALTER TABLE ADD COLUMN IF NOT EXISTS로 멱등 추가)

신규: `case_type` / `rank_no` / `rank_no_change` / `monthly_search_volume` / `mention_count` / `competition_level` / `is_opportunity`

---

## Sprint 3 예정

- STAGE 3.5 `semantic_dedup()` 의미 중복 병합
- FastAPI 엔드포인트 (`/dashboard`, `/analysis`, `/trend`, `/competitors`)
- `get_keyword_trend()` · `get_competitor_ranks()` · `get_gap_keywords()`
- `sentiment.py` 감성 사전 실연결

---

## 알려진 이슈 / 설계 결정 메모

- **Bigram 도미네이션** (보류): df_min=2→3 조정해도 bigram 과도함. Sprint 3에서 score multiplier 감소 등 다른 접근 검토
- **CASE B sentiment 기본값** 1.0 (중립 처리). Phase 2에서 0.5로 변경 예정
- **database.py**: 현재 read/write 모두 `WRITE_DB_URL` 사용 중 (환경 설정상 동일 RDS 엔드포인트). `READ_DB_URL` 분리는 인프라 설정 후 적용 예정
- **ngram.py df_min=3**: 허들 2는 노이즈 과도, 허들 3은 너무 엄격 — 적정값 탐색 중
