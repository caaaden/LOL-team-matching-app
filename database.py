# database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# --- MODIFIED START ---

# 환경 변수에서 Supabase 데이터베이스 URL을 가져옵니다.
# .env 파일이나 호스팅 플랫폼의 환경 변수에 설정된 값을 사용합니다.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("DATABASE_URL 환경 변수가 설정되지 않았습니다.")

# PostgreSQL 엔진 생성
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# SQLite에서만 필요했던 connect_args={"check_same_thread": False} 옵션은 제거합니다.
# engine = create_engine(
#     SQLALCHEMY_DATABASE_URL
# )

# --- MODIFIED END ---

# 세션 생성
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 베이스 클래스 생성
Base = declarative_base()