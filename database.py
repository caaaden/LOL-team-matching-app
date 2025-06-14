# database.py - Neon PostgreSQL 연결 최적화 버전
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# 환경 변수를 안전하게 가져오기
USER = os.getenv("user", "neondb_owner")
PASSWORD = os.getenv("password", "npg_74kbTqrNtCwu")
HOST = os.getenv("host", "ep-fancy-wildflower-a8iqjc97-pooler.eastus2.azure.neon.tech")
PORT = os.getenv("port", "5432")
DBNAME = os.getenv("dbname", "neondb")

print(f"🔄 데이터베이스 연결 시도: {HOST}/{DBNAME}")

# 포트 검증
try:
    port_int = int(PORT)
except ValueError:
    print(f"❌ 포트 값이 올바르지 않습니다: {PORT}")
    print("🔄 기본 포트 5432를 사용합니다...")
    port_int = 5432

# Neon에 최적화된 SQLAlchemy 연결 문자열
DATABASE_URL = f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{port_int}/{DBNAME}?sslmode=require"

try:
    # Neon에 최적화된 엔진 설정
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # 연결 상태 확인
        pool_recycle=300,  # 5분마다 연결 재생성 (Neon 권장사항)
        pool_size=5,  # 연결 풀 크기
        max_overflow=10,  # 최대 추가 연결
        echo=False  # SQL 로그 (개발 시에만 True)
    )

    # 연결 테스트
    from sqlalchemy import text

    with engine.connect() as connection:
        result = connection.execute(text("SELECT version()"))
        version = result.fetchone()[0]
        print(f"✅ Neon PostgreSQL 연결 성공!")
        print(f"📊 PostgreSQL 버전: {version[:50]}...")

except Exception as e:
    print(f"❌ PostgreSQL 연결 실패: {e}")
    print("🔄 SQLite로 폴백합니다...")

    # SQLite로 폴백
    DATABASE_URL = "sqlite:///./lol_team_matching.db"
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False
    )
    print("✅ SQLite 데이터베이스 연결 완료")

# 세션 생성
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 베이스 클래스 생성
Base = declarative_base()