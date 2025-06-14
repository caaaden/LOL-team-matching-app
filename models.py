# models.py - PostgreSQL 호환성 개선 버전
from sqlalchemy import Column, Integer, String, Boolean, Text, ForeignKey, DateTime, Enum, Float, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, timezone, timedelta
import enum


class Position(str, enum.Enum):
    TOP = "TOP"
    JUNGLE = "JUNGLE"
    MID = "MID"
    ADC = "ADC"
    SUPPORT = "SUPPORT"
    ALL = "ALL"


class Tier(str, enum.Enum):
    IRON = "IRON"
    BRONZE = "BRONZE"
    SILVER = "SILVER"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"
    EMERALD = "EMERALD"
    DIAMOND = "DIAMOND"
    MASTER = "MASTER"
    GRANDMASTER = "GRANDMASTER"
    CHALLENGER = "CHALLENGER"


# 사용자 모델
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), unique=True, index=True, nullable=False)  # 길이 명시
    hashed_password = Column(String(255), nullable=False)  # 길이 명시

    # 사용자와 활성 세션 간의 관계 설정
    active_session = relationship("ActiveSession", back_populates="user", uselist=False, cascade="all, delete-orphan")


# 활성 세션 모델 (동시 로그인 방지용)
class ActiveSession(Base):
    __tablename__ = "active_sessions"

    id = Column(Integer, primary_key=True, index=True)
    # 한 명의 유저는 하나의 세션만 가질 수 있도록 unique=True 설정
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    token = Column(Text, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)  # timezone 명시

    user = relationship("User", back_populates="active_session")


# 플레이어 모델 - PostgreSQL 최적화
class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    nickname = Column(String(100), index=True, unique=True, nullable=False)  # 길이 및 제약 조건 명시
    tier = Column(Enum(Tier, name="player_tier"), default=Tier.SILVER, nullable=False)
    division = Column(Integer, default=4, nullable=False)
    # PostgreSQL 호환성을 위한 Enum 타입명 명시
    player_position = Column(Enum(Position, name="player_position_enum"), nullable=False)  # 주 포지션
    sub_position = Column(Enum(Position, name="sub_position_enum"), nullable=True)  # 부 포지션
    lp = Column(Integer, default=0, nullable=False)
    tier_score = Column(Float, default=0.0, nullable=False)
    match_score = Column(Float, default=1000.0, nullable=False)
    win_count = Column(Integer, default=0, nullable=False)
    lose_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    team_assignments = relationship("TeamAssignment", back_populates="player", cascade="all, delete-orphan")

    # 기존 코드와의 호환성을 위한 프로퍼티
    @property
    def position(self):
        """기존 코드 호환성을 위한 프로퍼티"""
        return self.player_position

    @position.setter
    def position(self, value):
        """기존 코드 호환성을 위한 setter"""
        self.player_position = value


# 매치 모델
class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    match_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone(timedelta(hours=9))), nullable=False)
    blue_team_avg_score = Column(Float, nullable=False)
    red_team_avg_score = Column(Float, nullable=False)
    blue_team_match_score = Column(Float, nullable=False)
    red_team_match_score = Column(Float, nullable=False)
    balance_score = Column(Float, nullable=False)
    winner = Column(String(10), nullable=True)  # "BLUE" or "RED"
    is_completed = Column(Boolean, default=False, nullable=False)

    team_assignments = relationship("TeamAssignment", back_populates="match", cascade="all, delete-orphan")


# 팀 배정 모델 - PostgreSQL 최적화
class TeamAssignment(Base):
    __tablename__ = "team_assignments"

    id = Column(Integer, primary_key=True, index=True)
    team = Column(String(10), nullable=False)  # "BLUE" or "RED"
    # PostgreSQL 호환성을 위한 Enum 타입명 명시
    assigned_player_position = Column(Enum(Position, name="assigned_position_enum"), nullable=False)

    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)

    match = relationship("Match", back_populates="team_assignments")
    player = relationship("Player", back_populates="team_assignments")

    # 복합 인덱스 추가 (성능 최적화)
    __table_args__ = (
        UniqueConstraint('match_id', 'player_id', name='unique_match_player'),
    )

    # 기존 코드와의 호환성을 위한 프로퍼티
    @property
    def assigned_position(self):
        """기존 코드 호환성을 위한 프로퍼티"""
        return self.assigned_player_position

    @assigned_position.setter
    def assigned_position(self, value):
        """기존 코드 호환성을 위한 setter"""
        self.assigned_player_position = value