from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import READ_DB_URL, WRITE_DB_URL

# 읽기용 엔진 — RDS (연결 끊김 시 자동 재연결)
read_engine = create_engine(READ_DB_URL, pool_pre_ping=True)
ReadSession  = sessionmaker(bind=read_engine)

# 쓰기용 엔진 — RDS (연결 끊김 시 자동 재연결)
write_engine = create_engine(WRITE_DB_URL, pool_pre_ping=True)
WriteSession = sessionmaker(bind=write_engine)


def test_connection():
    """읽기/쓰기 DB 연결 상태 확인."""
    try:
        with read_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Read DB connected successfully")
    except Exception as e:
        print(f"Read DB connection failed: {e}")

    try:
        with write_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Write DB connected successfully")
    except Exception as e:
        print(f"Write DB connection failed: {e}")


def show_table():
    """현재 DB의 public 스키마 테이블 목록 출력."""
    with read_engine.connect() as conn:
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
