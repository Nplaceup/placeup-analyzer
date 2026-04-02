from app.db.database import test_connection, show_table
from app.db.repository import get_reviews, get_review_dates

def test_crawling_data(place_id: int):
    print("=== DB 연결 테스트 ===")
    test_connection()

    print("\n=== 테이블 목록 ===")
    show_table()

    print(f"\n=== place_id={place_id} 리뷰 샘플 ===")
    reviews = get_reviews(place_id)
    print(f"총 리뷰 수: {len(reviews)}")
    for r in reviews[:3]:
        print(f"  id={r['id']} | created_at={r['created_at']} | content={r['content'][:30]}...")

    print("\n=== 날짜 데이터 확인 ===")
    dates = get_review_dates(place_id)
    print(f"  날짜 매핑 수: {len(dates)}")
    for review_id, dt in list(dates.items())[:3]:
        print(f"  review_id={review_id} → {dt}")

if __name__ == "__main__":
    test_crawling_data(place_id=167)  # 실제 place_id로 변경