# database.py - Neon PostgreSQL 호환성 수정 버전
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
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

# Neon 호환성을 위한 연결 설정 (문제 파라미터 제거)
DATABASE_URL = f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{port_int}/{DBNAME}?sslmode=require"

try:
    # Neon에 최적화된 엔진 설정 (호환성 문제 해결)
    engine = create_engine(
        DATABASE_URL,
        # 연결 풀 크기 최적화 (메모리 사용량 줄이기)
        pool_size=2,  # 기본 연결 수
        max_overflow=3,  # 추가 연결 수
        pool_timeout=20,  # 연결 대기 시간
        pool_recycle=1800,  # 30분마다 연결 재생성 (메모리 정리)
        pool_pre_ping=True,  # 연결 상태 확인

        # Neon 호환성을 위한 연결 설정 (문제 파라미터 제거)
        connect_args={
            "application_name": "lol_team_matcher",
            "connect_timeout": 10,
            # ❌ 제거: "options": "-c default_transaction_isolation=read_committed"
            # Neon의 connection pooling 모드에서는 이 옵션이 지원되지 않음
        },

        # 로깅 최소화 (메모리 절약)
        echo=False,

        # 엔진 최적화
        future=True  # SQLAlchemy 2.0 스타일 사용
    )

    # 연결 테스트
    from sqlalchemy import text

    with engine.connect() as connection:
        result = connection.execute(text("SELECT version()"))
        version = result.fetchone()[0]
        print(f"✅ Neon PostgreSQL 연결 성공!")
        print(f"📊 연결 풀 설정: pool_size=2, max_overflow=3")
        print(f"🔧 PostgreSQL 버전: {version[:50]}...")

except Exception as e:
    print(f"❌ PostgreSQL 연결 실패: {e}")
    print("🔄 SQLite로 폴백합니다...")

    # SQLite로 폴백 (메모리 효율적 설정)
    DATABASE_URL = "sqlite:///./lol_team_matching.db"
    engine = create_engine(
        DATABASE_URL,
        connect_args={
            "check_same_thread": False,
            "timeout": 20  # SQLite 타임아웃 설정
        },
        echo=False,
        # SQLite 최적화
        pool_timeout=20,
        pool_recycle=-1  # SQLite는 연결 재활용하지 않음
    )
    print("✅ SQLite 데이터베이스 연결 완료")

# 세션 생성 (메모리 효율적 설정)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    # 메모리 최적화
    expire_on_commit=False  # 커밋 후 객체 만료 방지 (메모리 사용량 줄임)
)

# 베이스 클래스 생성
Base = declarative_base()