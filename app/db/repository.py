from sqlalchemy import text
from app.db.database import ReadSession, WriteSession
import pandas as pd
from typing import Optional
from datetime import datetime


# ───────────────────────────────────────────────
# READ (RDS - 크롤링 원본)
# ───────────────────────────────────────────────
def get_reviews(place_id : int) -> list[dict]:
    """
    특정 매장의 리뷰 목록 조회
    반환 : [{"id": int, "content": str, "created_at": datetime}]
    """
    with ReadSession() as session:
        result = session.execute(
            text("""
                SELECT id, body, created_at
                FROM place_reviews
                WHERE places_id = :place_id
                 AND body IS NOT NULL
                 AND body != ''
                ORDER BY created_at DESC
            """),
            {"place_id": place_id}
        )
        return [
            {
                "id":           row.id,
                "content":      row.body,
                "created_at":   row.created_at
            }
            for row in result
        ]


def get_review_dates(place_id: int) -> dict[int, datetime]:
    """
    리뷰 ID → 작성일자 매핑 반환 (keywordScorer 최신성 점수 계산용)
    반환: {review_id: datetime, ...}
    """
    with ReadSession() as session:
        result = session.execute(
            text("""
                SELECT id, created_at
                FROM place_reviews
                WHERE places_id = :place_id
                 AND created_at IS NOT NULL
            """),
            {"place_id": place_id}
        )
        return {row.id: row.created_at for row in result}


def get_all_place_ids() -> list[int]:
    """
    분석 대상 매장 ID 전체 조회
    """
    with ReadSession() as session:
        result = session.execute(
            text("SELECT DISTINCT places_id FROM place_reviews ORDER BY places_id")
        )
        return [row.places_id for row in result]


def get_review_analysis_labels() -> dict[str, list[str]]:
    """
    review_analysis 테이블에서 type별 label 목록 조회
    반환: {"THEMES": ["맛", "서비스", ...], "MENUS": ["스테이크", "파스타", ...]}
    """
    with ReadSession() as session:
        result = session.execute(
            text("""
                SELECT type, label
                FROM review_analysis
                ORDER BY type, id
            """)
        )
        labels: dict[str, list[str]] = {}
        for row in result:
            labels.setdefault(row.type, []).append(row.label)
        return labels


def get_place_rankings(place_id: int) -> list[dict]:
    """
    매장의 현재 키워드 순위 데이터 조회 (STAGE 2.5 rankings-only / NLP∩rankings 판별용)
    Spring rankings 테이블 기준으로 조회

    반환: [
        {
            "keyword":          str,   # 순위 추적 키워드
            "rank_no":          int,   # 현재 순위 (1 = 1위)
            "rank_no_change":   int,   # 순위 변동 (+: 상승, -: 하락, 0: 변동 없음)
        },
        ...
    ]
    순위 데이터 없으면 빈 리스트 반환.
    """
    with ReadSession() as session:
        result = session.execute(
            text("""
                SELECT DISTINCT ON (r.keyword_id)
                       k.keyword_name  AS keyword,
                       r.rank_no,
                       r.rank_no_change
                FROM   rankings r
                JOIN   keywords k ON k.id = r.keyword_id
                WHERE  r.place_id = :place_id
                ORDER  BY r.keyword_id, r.crawl_date DESC
            """),
            {"place_id": place_id}
        )
        return [
            {
                "keyword":        row.keyword,
                "rank_no":        row.rank_no,
                "rank_no_change": row.rank_no_change or 0,
            }
            for row in result
        ]


def get_place_info(place_id: int) -> dict | None:
    """
    매장의 지역·업종 정보 조회 (STAGE 4 지역/업종 기반 키워드 결합용)

    반환: {
        "name":          str,   # 매장명
        "category":      str,   # 업종 (예: "이탈리안", "브런치카페")
        "neighborhood":  str,   # 동 단위 — 접미사 제거 (예: "역삼동" → "역삼")
        "city":          str,   # 구/군 단위 — 접미사 제거 (예: "강남구" → "강남")
        "description":        str,   # 소개글 (없으면 빈 문자열)
        "menu_list":          str,   # 메뉴 목록 (없으면 빈 문자열)
        "image_review_count": int,   # 사진 포함 리뷰 수 (없으면 0)
    }
    매장 없으면 None 반환.

    address 형식: '{시도} {구군} {동}' — 예: '서울 강남구 역삼동', '인천 중구 운서동'
    """
    with ReadSession() as session:
        result = session.execute(
            text("""
                SELECT place_name, category, address, 
                    description, menu_list, image_review_count
                FROM places
                WHERE id = :place_id
                LIMIT 1
            """),
            {"place_id": place_id}
        ).fetchone()

    if not result:
        return None

    address = (result.address or "").strip()
    parts   = address.split()

    # parts[0] = 시/도 (서울, 인천 ...) — 검색어로는 너무 광역
    # parts[1] = 구/군 (강남구, 중구 ...) — "강남구" → "강남" 접미사 제거
    # parts[2] = 동/읍/면 (역삼동, 운서동 ...) — "역삼동" → "역삼" 접미사 제거
    city         = _strip_suffix(parts[1], ("구", "군", "시")) if len(parts) >= 2 else ""
    neighborhood = _strip_suffix(parts[2], ("구", "군", "동", "읍", "면", "리")) if len(parts) >= 3 else ""

    return {
        "name":         result.place_name     or "",
        "category":     result.category or "",
        "neighborhood": neighborhood,   # 예: "역삼", "운서"
        "city":         city,           # 예: "강남"(강남구→강남) / "중구"(중구→유지, 2자 이하 제거 안 함)
        "description":        result.description       or "",
        "menu_list":          result.menu_list         or "",
        "image_review_count": result.image_review_count or 0,
    }


def _strip_suffix(word: str, suffixes: tuple[str, ...]) -> str:
    """
    단어 끝에 붙은 행정구역 접미사를 제거해 검색 친화적 형태로 변환.

    예: "강남구" → "강남" / "역삼동" → "역삼" / "중구" → "중구" (2자 이하 제거 안 함)

    2자 이하 단어는 접미사 제거 시 의미 없어지므로 원형 유지.
    예: "중구" → 제거하면 "중" (의미 모호) → "중구" 그대로 반환
    """
    for suffix in suffixes:
        if word.endswith(suffix) and len(word) > len(suffix) + 1:
            return word[: -len(suffix)]
    return word


def get_competitor_place_ids(
    category:         str,
    city:             str,
    exclude_place_id: int,
    limit:            int = 10,
) -> list[int]:
    """
    동일 카테고리+도시 내 매장 ID 조회 (경쟁업체 분석용).
    category/address는 LIKE 매칭 — 정규화 불일치 대응. 리뷰수 내림차순.
    """
    with ReadSession() as session:
        result = session.execute(
            text("""
                SELECT   p.id
                FROM     places p
                JOIN (
                    SELECT   places_id,
                             COUNT(*) AS review_count
                    FROM     place_reviews
                    GROUP BY places_id
                ) r ON r.places_id = p.id
                WHERE  p.category LIKE :category
                  AND  p.address  LIKE :city_pattern
                  AND  p.id != :exclude_id
                ORDER  BY r.review_count DESC
                LIMIT  :limit
            """),
            {
                "category":     f"%{category}%",
                "city_pattern": f"%{city}%",
                "exclude_id":   exclude_place_id,
                "limit":        limit,
            }
        )
        return [row.id for row in result]


def get_keywords_by_place_ids(place_ids: list[int]) -> dict[int, list[dict]]:
    """
    여러 매장의 최신 키워드+순위 조회 (경쟁업체 분석용).
    반환: {place_id: [{"keyword": str, "rank_no": int}, ...]}
    """
    if not place_ids:
        return {}

    with ReadSession() as session:
        result = session.execute(
            text("""
                SELECT DISTINCT ON (r.place_id, r.keyword_id)
                       r.place_id,
                       k.keyword_name  AS keyword,
                       r.rank_no
                FROM   rankings r
                JOIN   keywords k ON k.id = r.keyword_id
                WHERE  r.place_id = ANY(:place_ids)
                ORDER  BY r.place_id, r.keyword_id, r.crawl_date DESC
            """),
            {"place_ids": place_ids}
        )
        mapping: dict[int, list[dict]] = {}
        for row in result:
            mapping.setdefault(row.place_id, []).append({
                "keyword": row.keyword,
                "rank_no": row.rank_no,
            })
        return mapping


def get_related_keywords_for_place(
    place_id:     int,
    city:         str,
    neighborhood: str,
    top_n:        int = 10,
) -> list[dict]:
    """
    매장 rankings 키워드에 매핑된 연관검색어 조회.
    위치(city/neighborhood LIKE 매칭) + 검색량>0 필터, 검색량 내림차순 top_n.
    """
    if not place_id or (not city and not neighborhood):
        return []

    with ReadSession() as session:
        result = session.execute(
            text("""
                SELECT DISTINCT ON (kr.name)
                       kr.name                  AS keyword,
                       kr.monthly_search_volume,
                       kr.competition_level
                FROM   keyword_related kr
                JOIN   rankings r ON r.keyword_id = kr.keywords_id
                WHERE  r.place_id = :place_id
                  AND  kr.monthly_search_volume > 0
                  AND  (
                       kr.name LIKE :city_pattern
                    OR kr.name LIKE :neighborhood_pattern
                  )
                ORDER  BY kr.name, kr.monthly_search_volume DESC
            """),
            {
                "place_id":             place_id,
                "city_pattern":         f"%{city}%",
                "neighborhood_pattern": f"%{neighborhood}%",
            }
        )
        rows = [
            {
                "keyword":               row.keyword,
                "monthly_search_volume": row.monthly_search_volume,
                "competitive_level": row.competition_level or "낮음",
            }
            for row in result
        ]

    return sorted(rows, key=lambda x: -x["monthly_search_volume"])[:top_n]


def get_keyword_monthly_search(keyword_names: list[str]) -> dict[str, int]:
    """
    키워드 월간 검색량 조회 (keyword_search_volumes 테이블)
    - 동일 키워드의 가장 최신 데이터만 사용
    - Spring이 keyword_name을 공백 제거(replaceAll("\\s+", ""))하여 저장하므로
      Python도 동일하게 정규화하여 조회 후 원본 키워드로 역매핑
    반환: {keyword_name(원본): monthly_search_volume, ...}
    """
    if not keyword_names:
        return {}

    normalized = ["".join(kw.split()) for kw in keyword_names]
    reverse_map = {normalized[i]: keyword_names[i] for i in range(len(keyword_names))}

    with ReadSession() as session:
        result = session.execute(
            text("""
                SELECT DISTINCT ON (k.keyword_name)
                       k.keyword_name,
                       ksv.monthly_search_volume
                FROM   keyword_search_volumes ksv
                JOIN   keywords k ON k.id = ksv.keywords_id
                WHERE  k.keyword_name = ANY(:names)
                ORDER  BY k.keyword_name, ksv.created_at DESC
            """),
            {"names": normalized}
        )
        return {
            reverse_map.get(row.keyword_name, row.keyword_name): row.monthly_search_volume
            for row in result
        }

# ───────────────────────────────────────────────
# WRITE (Local DB - 분석 결과 적재)
# ───────────────────────────────────────────────

def create_recommend_keywords_table() -> None:
    """
    recommend_keywords 테이블이 없으면 생성하고,
    기존 테이블에 신규 컬럼이 없으면 추가 (멱등 실행 가능).
    애플리케이션 초기 구동 시 한 번 호출.

    컬럼 설명
    ─────────────────────────────────────────────
    place_id               : 매장 ID (FK: place_reviews.places_id)
    keyword                : 키워드 (1-gram 또는 bigram)
    score                  : 최종 종합 점수
    tfidf_score            : TF-IDF 지표 점수 (정규화 0~1)
    sentiment_score        : 감성 지표 점수 (정규화 0~1, Phase 2 연동 전 기본 1.0)
    recency_score          : 최신성 지표 점수 (0~1)
    consistency_score      : 일관성 지표 점수 (0~1)
    is_induced             : 유도어 결합 여부
    keyword_purpose        : 'search' | 'marketing'
    category               : '음식' | '장소' | '서비스' | '분위기' | '미분류'
    case_type              : 'A' (NLP∩순위) | 'B' (순위only) | 'C' (NLP only)
    rank_no                : 현재 네이버 플레이스 순위 (NULL = 순위 없음)
    rank_no_change         : 순위 변동 (+상승 / -하락 / 0 유지)
    monthly_search_volume  : 월간 검색량
    mention_count          : 리뷰 언급 건수 (CASE B는 0)
    competition_level      : '높음' (≥10,000) | '중간' (≥1,000) | '낮음'
    is_opportunity         : 검색량 높은데 10위권 밖인 키워드 여부
    analyzed_at            : 분석 실행 시각
    ─────────────────────────────────────────────
    UNIQUE(place_id, keyword) → upsert 기준 키
    """
    with WriteSession() as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS recommend_keywords (
                id                     SERIAL PRIMARY KEY,
                place_id               INT           NOT NULL,
                keyword                VARCHAR(100)  NOT NULL,
                score                  FLOAT         NOT NULL,
                tfidf_score            FLOAT         NOT NULL DEFAULT 0.0,
                sentiment_score        FLOAT         NOT NULL DEFAULT 1.0,
                recency_score          FLOAT         NOT NULL DEFAULT 0.0,
                consistency_score      FLOAT         NOT NULL DEFAULT 0.0,
                is_induced             BOOLEAN       NOT NULL DEFAULT FALSE,
                keyword_purpose        VARCHAR(20)   NOT NULL DEFAULT 'marketing',
                category               VARCHAR(20)   NOT NULL DEFAULT '미분류',
                case_type              CHAR(1)       NOT NULL DEFAULT 'C',
                rank_no                INT,
                rank_no_change         INT           NOT NULL DEFAULT 0,
                monthly_search_volume  INT           NOT NULL DEFAULT 0,
                mention_count          INT           NOT NULL DEFAULT 0,
                competition_level      VARCHAR(10)   NOT NULL DEFAULT '낮음',
                is_opportunity         BOOLEAN       NOT NULL DEFAULT FALSE,
                analyzed_at            TIMESTAMP     NOT NULL DEFAULT NOW(),
                UNIQUE (place_id, keyword)
            )
        """))
        # ── 신규 컬럼 추가 (이미 있으면 무시) ────────────────────────────────────
        new_columns = [
            ("case_type",             "CHAR(1)     NOT NULL DEFAULT 'C'"),
            ("rank_no",               "INT"),
            ("rank_no_change",        "INT         NOT NULL DEFAULT 0"),
            ("monthly_search_volume", "INT         NOT NULL DEFAULT 0"),
            ("mention_count",         "INT         NOT NULL DEFAULT 0"),
            ("competition_level",     "VARCHAR(10) NOT NULL DEFAULT '낮음'"),
            ("is_opportunity",        "BOOLEAN     NOT NULL DEFAULT FALSE"),
        ]
        for col_name, col_def in new_columns:
            session.execute(text(
                f"ALTER TABLE recommend_keywords "
                f"ADD COLUMN IF NOT EXISTS {col_name} {col_def}"
            ))

        session.commit()
        print("[DB] recommend_keywords 테이블 확인/생성 완료")


def upsert_recommend_keywords(place_id: int, formatted: list[dict], scored_map: dict) -> int:
    """
    attach_inducement() + keyword_meta 결합 결과를 로컬 DB에 upsert.
    (place_id, keyword) 충돌 시 전체 수치 컬럼 덮어쓰기.
    """
    if not formatted:
        return 0

    rows = []
    for item in formatted:
        kw = item["keyword"]
        # 유도어 결합형은 마지막 토큰 제거해 기반 키워드의 breakdown 조회
        base_kw   = " ".join(kw.split()[:-1]) if item["is_induced"] else kw
        breakdown = scored_map.get(base_kw, {})

        rows.append({
            "place_id":               place_id,
            "keyword":                kw,
            "score":                  item["base_score"],
            "tfidf_score":            breakdown.get("tfidf",       0.0),
            "sentiment_score":        breakdown.get("sentiment",   1.0),
            "recency_score":          breakdown.get("recency",     0.0),
            "consistency_score":      breakdown.get("consistency", 0.0),
            "is_induced":             item["is_induced"],
            "keyword_purpose":        item["keyword_purpose"],
            "category":               item["category"],
            "case_type":              item.get("case_type",             "C"),
            "rank_no":                item.get("rank_no"),
            "rank_no_change":         item.get("rank_no_change",        0),
            "monthly_search_volume":  item.get("monthly_search_volume", 0),
            "mention_count":          item.get("mention_count",         0),
            "competition_level":      item.get("competition_level",     "낮음"),
            "is_opportunity":         item.get("is_opportunity",        False),
        })

    with WriteSession() as session:
        session.execute(
            text("""
                INSERT INTO recommend_keywords
                    (place_id, keyword, score,
                     tfidf_score, sentiment_score, recency_score, consistency_score,
                     is_induced, keyword_purpose, category,
                     case_type, rank_no, rank_no_change,
                     monthly_search_volume, mention_count,
                     competition_level, is_opportunity,
                     analyzed_at)
                VALUES
                    (:place_id, :keyword, :score,
                     :tfidf_score, :sentiment_score, :recency_score, :consistency_score,
                     :is_induced, :keyword_purpose, :category,
                     :case_type, :rank_no, :rank_no_change,
                     :monthly_search_volume, :mention_count,
                     :competition_level, :is_opportunity,
                     NOW())
                ON CONFLICT (place_id, keyword)
                DO UPDATE SET
                    score                  = EXCLUDED.score,
                    tfidf_score            = EXCLUDED.tfidf_score,
                    sentiment_score        = EXCLUDED.sentiment_score,
                    recency_score          = EXCLUDED.recency_score,
                    consistency_score      = EXCLUDED.consistency_score,
                    is_induced             = EXCLUDED.is_induced,
                    keyword_purpose        = EXCLUDED.keyword_purpose,
                    category               = EXCLUDED.category,
                    case_type              = EXCLUDED.case_type,
                    rank_no                = EXCLUDED.rank_no,
                    rank_no_change         = EXCLUDED.rank_no_change,
                    monthly_search_volume  = EXCLUDED.monthly_search_volume,
                    mention_count          = EXCLUDED.mention_count,
                    competition_level      = EXCLUDED.competition_level,
                    is_opportunity         = EXCLUDED.is_opportunity,
                    analyzed_at            = NOW()
            """),
            rows
        )
        session.commit()

    print(f"[DB] place_id={place_id} → {len(rows)}개 키워드 upsert 완료")
    return len(rows)


# ───────────────────────────────────────────────
# READ (Local DB - 저장 결과 조회)
# ───────────────────────────────────────────────

def get_recommend_keywords(place_id: int) -> list[dict]:
    """
    저장된 추천 키워드 조회 (score 내림차순)
    반환: [{"keyword", "score", "keyword_purpose", "category",
            "is_induced",
            "case_type", "rank_no", "rank_no_change",
            "monthly_search_volume", "mention_count",
            "competition_level", "is_opportunity",
            "analyzed_at"}, ...]
    """
    with ReadSession() as session:   # 읽기 전용 세션 사용
        result = session.execute(
            text("""
                SELECT keyword, score, tfidf_score, sentiment_score,
                       recency_score, consistency_score,
                       is_induced, keyword_purpose, category,
                       case_type, rank_no, rank_no_change,
                       monthly_search_volume, mention_count,
                       competition_level, is_opportunity,
                       analyzed_at
                FROM recommend_keywords
                WHERE place_id = :place_id
                ORDER BY score DESC
            """),
            {"place_id": place_id}
        )
        return [dict(row._mapping) for row in result]

def create_seo_results_table() -> None:
    with WriteSession() as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS seo_results (
                id                   SERIAL PRIMARY KEY,
                place_id             INT           NOT NULL,
                score                INT           NOT NULL,
                grade                VARCHAR(20)   NOT NULL,
                place_completeness   FLOAT         NOT NULL DEFAULT 0.0,
                review_quality       FLOAT         NOT NULL DEFAULT 0.0,
                place_summary        TEXT          NOT NULL DEFAULT '{}',
                summary              TEXT          NOT NULL,
                seo_feedback         TEXT          NOT NULL DEFAULT '[]',
                review_feedback      TEXT          NOT NULL DEFAULT '[]',
                competitor_feedback  TEXT          NOT NULL DEFAULT '[]',
                created_at           TIMESTAMP     NOT NULL DEFAULT NOW(),
                UNIQUE (place_id)
            )
        """))
        session.commit()
        print("[DB] seo_results 테이블 확인/생성 완료")


def upsert_seo_result(place_id: int, seo_result: dict, feedback_result: dict) -> None:
    import json
    b = seo_result["breakdown"]

    with WriteSession() as session:
        session.execute(
            text("""
                INSERT INTO seo_results
                    (place_id, score, grade,
                     place_completeness, review_quality,
                     place_summary,
                     summary, seo_feedback, review_feedback,
                     competitor_feedback,
                     created_at)
                VALUES
                    (:place_id, :score, :grade,
                     :place_completeness, :review_quality,
                     :place_summary,
                     :summary, :seo_feedback, :review_feedback,
                     :competitor_feedback,
                     NOW())
                ON CONFLICT (place_id)
                DO UPDATE SET
                    score               = EXCLUDED.score,
                    grade               = EXCLUDED.grade,
                    place_completeness  = EXCLUDED.place_completeness,
                    review_quality      = EXCLUDED.review_quality,
                    place_summary       = EXCLUDED.place_summary,
                    summary             = EXCLUDED.summary,
                    seo_feedback        = EXCLUDED.seo_feedback,
                    review_feedback     = EXCLUDED.review_feedback,
                    competitor_feedback = EXCLUDED.competitor_feedback,
                    created_at          = NOW()
            """),
            {
                "place_id":            place_id,
                "score":               seo_result["total"],
                "grade":               seo_result["grade"],
                "place_completeness":  b["place_completeness"],
                "review_quality":      b["review_quality"],
                "place_summary":       json.dumps(feedback_result.get("place_summary", {}), ensure_ascii=False),
                "summary":             feedback_result["summary"],
                "seo_feedback":        json.dumps(feedback_result["seo_feedback"],        ensure_ascii=False),
                "review_feedback":     json.dumps(feedback_result["review_feedback"],     ensure_ascii=False),
                "competitor_feedback": json.dumps(feedback_result["competitor_feedback"], ensure_ascii=False),
            }
        )
        session.commit()
    print(f"[DB] place_id={place_id} 플레이스 관리 점수 upsert 완료")
    

def get_seo_result(place_id: int) -> dict | None:
    with ReadSession() as session:
        result = session.execute(
            text("""
                SELECT place_id, score, grade,
                       place_completeness, review_quality,
                       place_summary,
                       summary, seo_feedback, review_feedback,
                       competitor_feedback,
                       created_at
                FROM seo_results
                WHERE place_id = :place_id
                LIMIT 1
            """),
            {"place_id": place_id}
        ).fetchone()

        if not result:
            return None

        return dict(result._mapping)