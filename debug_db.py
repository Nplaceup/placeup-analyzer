"""
DB 데이터 진단 스크립트
검색량·순위 점수가 0으로 나올 때 원인 파악용

"""
from app.db.repository import (
    get_reviews,
    get_place_rankings,
    get_place_info,
    get_keyword_monthly_search,
)
from app.db.database import ReadSession
from sqlalchemy import text

PLACE_ID = 863  # 테스트 대상 place_id


def sep(label: str):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('=' * 60)


# ── 1. 순위 데이터 확인 ──────────────────────────────────────────────────────
sep("1. keyword_place_ranks 조회")
rankings = get_place_rankings(PLACE_ID)
print(f"  반환 행 수: {len(rankings)}")
if rankings:
    print(f"  샘플 (5개):")
    for r in rankings[:5]:
        print(f"    keyword={r['keyword']!r:<25}  rank_no={r['rank_no']}  change={r['rank_no_change']}")
else:
    print("  ※ 결과 없음 — place_id가 keyword_place_ranks에 없거나 다름")

    # place_id 범위 확인
    with ReadSession() as session:
        result = session.execute(
            text("SELECT DISTINCT place_id FROM keyword_place_ranks LIMIT 10")
        )
        ids = [row.place_id for row in result]
        print(f"  keyword_place_ranks에 존재하는 place_id 샘플: {ids}")


# ── 2. 검색량 테이블 확인 ─────────────────────────────────────────────────────
sep("2. keyword_search_volumes 테이블 구조 확인")
with ReadSession() as session:
    # 테이블 존재 + 행 수
    try:
        cnt = session.execute(text("SELECT COUNT(*) FROM keyword_search_volumes")).scalar()
        print(f"  keyword_search_volumes 행 수: {cnt}")

        # keywords 테이블 샘플
        kw_sample = session.execute(
            text("SELECT id, keyword_name FROM keywords LIMIT 10")
        ).fetchall()
        print(f"\n  keywords 테이블 샘플:")
        for row in kw_sample:
            print(f"    id={row.id}  keyword_name={row.keyword_name!r}")

        # search_volumes 샘플
        vol_sample = session.execute(
            text("""
                SELECT k.keyword_name, ksv.monthly_search_volume
                FROM keyword_search_volumes ksv
                JOIN keywords k ON k.id = ksv.keywords_id
                ORDER BY ksv.monthly_search_volume DESC
                LIMIT 10
            """)
        ).fetchall()
        print(f"\n  검색량 상위 10개:")
        for row in vol_sample:
            print(f"    {row.keyword_name!r:<25}  검색량={row.monthly_search_volume:,}")

    except Exception as e:
        print(f"  ※ 오류: {e}")


# ── 3. 순위 키워드로 검색량 매칭 확인 ─────────────────────────────────────────
sep("3. 순위 키워드 → 검색량 매칭 확인")
if rankings:
    sample_kws = [r["keyword"] for r in rankings[:10]]
    print(f"  조회 키워드: {sample_kws}")
    volumes = get_keyword_monthly_search(sample_kws)
    print(f"  매칭 결과 ({len(volumes)}개 매칭):")
    if volumes:
        for kw, vol in list(volumes.items())[:10]:
            print(f"    {kw!r:<25}  검색량={vol:,}")
    else:
        print("  ※ 매칭 없음 — keyword_place_ranks.keyword_id와 keywords.keyword_name 형식 불일치 가능성")

        # keyword_place_ranks의 keyword_id 실제 형식 확인
        with ReadSession() as session:
            result = session.execute(
                text("SELECT DISTINCT keyword_id FROM keyword_place_ranks LIMIT 5")
            )
            kw_ids = [row.keyword_id for row in result]
            print(f"\n  keyword_place_ranks.keyword_id 실제 값: {kw_ids}")


# ── 4. place_info 확인 ────────────────────────────────────────────────────────
sep("4. place_info 확인")
place_info = get_place_info(PLACE_ID)
if place_info:
    print(f"  name        : {place_info['name']}")
    print(f"  category    : {place_info['category']!r}")
    print(f"  neighborhood: {place_info['neighborhood']!r}")
    print(f"  city        : {place_info['city']!r}")
else:
    print(f"  ※ place_id={PLACE_ID} 에 해당하는 places 행 없음")

    with ReadSession() as session:
        ids = session.execute(
            text("SELECT id FROM places LIMIT 5")
        ).fetchall()
        print(f"  places 테이블 id 샘플: {[r.id for r in ids]}")


# ── 5. 리뷰 수 확인 ──────────────────────────────────────────────────────────
sep("5. 리뷰 수 확인")
reviews = get_reviews(PLACE_ID)
print(f"  리뷰 수: {len(reviews)}개")
