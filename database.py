# database.py - 개발/배포 환경 분리 버전
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv
from sqlalchemy import text

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# 현재 환경 확인 (기본값: 'development')
APP_ENV = os.getenv("APP_ENV", "development").lower()

if APP_ENV == "production":
    # --- 🚀 배포 환경 (Production) ---
    # 기존 PostgreSQL (Neon) 연결 설정 사용
    print("🚀 Running in PRODUCTION mode. Connecting to PostgreSQL...")

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
    except (ValueError, TypeError):
        print(f"❌ 포트 값이 올바르지 않습니다: {PORT}. 기본 포트 5432를 사용합니다.")
        port_int = 5432

    # Neon 호환성을 위한 연결 설정
    DATABASE_URL = f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{port_int}/{DBNAME}?sslmode=require"

    try:
        # Neon에 최적화된 엔진 설정
        engine = create_engine(
            DATABASE_URL,
            pool_size=2, max_overflow=3, pool_timeout=20, pool_recycle=1800, pool_pre_ping=True,
            connect_args={
                "application_name": "lol_team_matcher_prod",
                "connect_timeout": 10,
            },
            echo=False,  # 프로덕션 환경에서는 SQL 로깅 비활성화
            future=True
        )
        # 연결 테스트
        with engine.connect() as connection:
            result = connection.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✅ Neon PostgreSQL 연결 성공!")
            print(f"📊 PostgreSQL 버전: {version[:50]}...")

    except Exception as e:
        print(f"❌ CRITICAL: PostgreSQL 연결 실패 in PRODUCTION mode: {e}")
        # 배포 환경에서는 DB 연결 실패 시 더 이상 진행하지 않도록 예외 발생
        raise e

else:
    # --- 🔧 개발 환경 (Development) ---
    print("🔧 Running in DEVELOPMENT mode. Using SQLite database.")

    # SQLite 데이터베이스 설정
    DATABASE_URL = "sqlite:///./lol_team_matching_dev.db"
    engine = create_engine(
        DATABASE_URL,
        # 개발 시에는 SQL 쿼리를 로깅하는 것이 디버깅에 유용
        echo=True,
        connect_args={"check_same_thread": False},
        future=True
    )
    print(f"✅ SQLite 연결 성공: {DATABASE_URL}")


# --- 공통 설정 ---
# 세션 생성
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)

# 베이스 클래스 생성
Base = declarative_base()