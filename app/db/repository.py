from sqlalchemy import text
from app.db.database import ReadSession
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


def get_keyword_monthly_search(keyword_names: list[str]) -> dict[str, int]:
    """
    키워드 월간 검색량 조회 (keyword_search_volumes 테이블)
    - 동일 키워드의 가장 최신 데이터만 사용
    반환: {keyword_name: monthly_search_volume, ...}
    """
    if not keyword_names:
        return {}

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
            {"names": keyword_names}
        )
        return {row.keyword_name: row.monthly_search_volume for row in result}

# ───────────────────────────────────────────────
# WRITE (Local DB - 분석 결과 적재)
# ───────────────────────────────────────────────

# ───────────────────────────────────────────────
# READ (Local DB - 저장 결과 조회)
# ───────────────────────────────────────────────
