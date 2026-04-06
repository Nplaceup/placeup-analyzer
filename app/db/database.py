from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import READ_DB_URL, WRITE_DB_URL

# 읽기용 DB 연결 엔진 생성 - RDS (연결이 끊겼을때 자동으로 재연결 시도함)
read_engine = create_engine(WRITE_DB_URL, pool_pre_ping=True)
ReadSession = sessionmaker(bind=read_engine)

# 쓰기용 DB 연결 엔진 생성 - Local (연결이 끊겼을때 자동으로 재연결 시도함)
write_engine = create_engine(WRITE_DB_URL, pool_pre_ping=True)
WriteSession = sessionmaker(bind=write_engine)


def test_connection():
    """ DB 연결 테스트 """
    try:
        with read_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("RDS successfully connected")
    except Exception as e:
        print(f"RDS connection falied : {e}")

    try:
        with write_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("local DB successfully connected")
    except Exception as e:
        print(f"local DB connection falied : {e}")


def show_table():
    """ 현재 DB 테이블 목록 확인"""
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