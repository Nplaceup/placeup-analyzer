from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import DB_URL

# DB 연결 엔진 생성 (연결이 끊겼을때 자동으로 재연결 시도함)
engine = create_engine(DB_URL, pool_pre_ping=True)

#세션 팩토리 생성
# autocommit=False -> 직접 commit() 호출해야 저장
# autoflush=False  -> 명시적으로 flush 할 때만 DB에 반영
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """ DB 세션 반환 - 사용 후 자동으로 닫힘 """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_connection():
    """ DB 연결 테스트 """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("DB successfully connected")
    except:
        print("DB connection falied : {e}")

def show_table():
    """ 현재 DB 테이블 목록 확인"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result]
        print("=== 테이블 목록 ===")
        for table in tables:
            print(f"  - {table}")
        return tables

if __name__ == "__main__":
    test_connection()
    show_table()