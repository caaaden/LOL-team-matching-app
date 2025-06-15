# main.py - 중복 로그인 방지 기능 제거 버전
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Body, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from contextlib import asynccontextmanager
import os
import uvicorn
import math
import traceback
import gc
import psutil
import asyncio

from database import SessionLocal, engine, Base
import models
import schemas
from utils import calculate_tier_score, balance_teams, update_team_match_scores, POSITIONS_ORDER, \
    distribute_players_to_groups

# --- 환경 설정 ---
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-is-still-secret-but-use-env-var")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Qv4RDGoEE8G41ru")

# --- Tailwind CSS 클래스 맵 (중앙 관리) ---
POSITION_COLOR_MAP = {
    "TOP": "bg-red-600 text-white",
    "JUNGLE": "bg-green-600 text-white",
    "MID": "bg-yellow-500 text-black",
    "ADC": "bg-orange-500 text-white",
    "SUPPORT": "bg-blue-500 text-white",
    "ALL": "bg-purple-600 text-white",
}

TIER_COLOR_MAP = {
    "IRON": "bg-gray-700 text-white",
    "BRONZE": "bg-amber-700 text-white",
    "SILVER": "bg-slate-400 text-black",
    "GOLD": "bg-yellow-400 text-black",
    "PLATINUM": "bg-teal-400 text-black",
    "EMERALD": "bg-emerald-500 text-white",
    "DIAMOND": "bg-sky-400 text-black",
    "MASTER": "bg-purple-500 text-white",
    "GRANDMASTER": "bg-red-500 text-white",
    "CHALLENGER": "bg-gradient-to-r from-yellow-400 to-sky-400 text-black font-bold",
}


# --- 템플릿 렌더링 헬퍼 ---
def render_template(template_name: str, context: Dict):
    """모든 템플릿에 공통 컨텍스트를 추가하는 헬퍼 함수"""
    common_context = {
        "POSITION_COLOR_MAP": POSITION_COLOR_MAP,
        "TIER_COLOR_MAP": TIER_COLOR_MAP
    }
    context.update(common_context)
    return templates.TemplateResponse(template_name, context)


# 메모리 누수 방지를 위한 개선된 데이터베이스 세션 관리
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_admin_user_on_startup(db: Session):
    admin_user = db.query(models.User).filter(models.User.user_id == ADMIN_USER_ID).first()
    if not admin_user:
        hashed_password = get_password_hash(ADMIN_PASSWORD)
        admin = models.User(user_id=ADMIN_USER_ID, hashed_password=hashed_password)
        db.add(admin)
        db.commit()
        print(f"Admin user '{ADMIN_USER_ID}' created.")
    elif not verify_password(ADMIN_PASSWORD, admin_user.hashed_password):
        # 비밀번호 변경 시, 해당 유저의 모든 활성 세션을 삭제하여 재로그인 유도
        db.query(models.ActiveSession).filter(models.ActiveSession.user_id == admin_user.id).delete()
        admin_user.hashed_password = get_password_hash(ADMIN_PASSWORD)
        db.commit()
        print(f"Admin user '{ADMIN_USER_ID}' password updated and all previous sessions invalidated.")
    else:
        print(f"Admin user '{ADMIN_USER_ID}' verified.")


# 만료된 세션 정리를 위한 백그라운드 태스크
async def cleanup_expired_sessions():
    while True:
        try:
            with SessionLocal() as db:
                expired_count = db.query(models.ActiveSession).filter(
                    models.ActiveSession.expires_at < datetime.now(timezone.utc)
                ).delete()
                if expired_count > 0:
                    db.commit()
                    print(f"🧹 만료된 세션 {expired_count}개 정리 완료")
        except Exception as e:
            print(f"❌ 세션 정리 태스크 오류: {e}")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 애플리케이션 시작 - 중복 로그인 방지 기능 비활성화")
    cleanup_task = asyncio.create_task(cleanup_expired_sessions())
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ 데이터베이스 테이블 생성 완료")
        with SessionLocal() as db:
            create_admin_user_on_startup(db)
    except Exception as e:
        print(f"❌ 시작 시 오류: {e}")
    yield
    print("🛑 애플리케이션 종료 - 정리 작업 중...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="LoL 팀 매칭 시스템", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def get_user_from_db(db, user_id: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.user_id == user_id).first()


def authenticate_user(db, user_id: str, password: str) -> Optional[models.User]:
    user = get_user_from_db(db, user_id)
    if not user or not verify_password(password, user.hashed_password) or user.user_id != ADMIN_USER_ID:
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# 활성 세션 확인 로직
async def get_current_user_from_cookie(request: Request, db: Session = Depends(get_db)) -> Optional[models.User]:
    token = request.cookies.get("access_token")
    if not token or not token.startswith("Bearer "):
        return None
    token = token.replace("Bearer ", "")

    # 토큰을 기반으로 활성 세션을 직접 조회
    active_session = db.query(models.ActiveSession).filter(models.ActiveSession.token == token).first()

    # 세션이 없거나 만료된 경우
    if not active_session or active_session.expires_at < datetime.now(timezone.utc):
        if active_session:  # 만료된 세션이면 DB에서 삭제
            db.delete(active_session)
            db.commit()
        return None

    # 세션이 유효하면 연결된 사용자 반환
    return active_session.user


async def login_required(user: Optional[models.User] = Depends(get_current_user_from_cookie)):
    if user is None or user.user_id != ADMIN_USER_ID:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            detail="로그인이 필요합니다.",
            headers={"Location": "/login?error=LoginRequired"},
        )
    return user


@app.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user_from_cookie(request, db)
    return render_template("index.html", {"request": request, "user": user})


@app.get("/login", response_class=HTMLResponse, name="login_page")
async def login_page(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user_from_cookie(request, db)
    if user and user.user_id == ADMIN_USER_ID:
        return RedirectResponse(url=app.url_path_for("home"), status_code=status.HTTP_303_SEE_OTHER)
    error_message = request.query_params.get("error")
    return render_template("login.html", {"request": request, "error": error_message})


# 로그인 로직 (중복 로그인 확인 제거)
@app.post("/login", name="login_form_submit")
async def login_form_post(request: Request, user_id: str = Form(...), password: str = Form(...),
                          db: Session = Depends(get_db)):
    if user_id != ADMIN_USER_ID:
        return render_template("login.html", {"request": request, "error": "관리자 아이디가 아닙니다."})

    user = authenticate_user(db, user_id, password)
    if not user:
        return render_template("login.html", {"request": request, "error": "아이디 또는 비밀번호가 잘못되었습니다."})

    # 중복 로그인 확인 로직 제거됨.
    # 성공적으로 인증되면 항상 새로운 세션과 토큰을 생성.

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire_datetime = datetime.now(timezone.utc) + access_token_expires
    access_token = create_access_token(data={"sub": user.user_id}, expires_delta=access_token_expires)

    new_session = models.ActiveSession(user_id=user.id, token=access_token, expires_at=expire_datetime)
    db.add(new_session)
    db.commit()

    response = RedirectResponse(url=app.url_path_for("home"), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=int(access_token_expires.total_seconds()),
        samesite="Lax",
        secure=request.url.scheme == "https"
    )
    return response


# 로그아웃 (현재 세션만 정리)
@app.get("/logout", name="logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    token_from_cookie = request.cookies.get("access_token")
    if token_from_cookie:
        token = token_from_cookie.replace("Bearer ", "")
        session_to_delete = db.query(models.ActiveSession).filter(models.ActiveSession.token == token).first()
        if session_to_delete:
            db.delete(session_to_delete)
            db.commit()

    response = RedirectResponse(url=app.url_path_for("login_page"), status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token", samesite="Lax", secure=request.url.scheme == "https")
    return response


@app.get("/player-management", response_class=HTMLResponse, name="player_management_page")
async def player_management_page(request: Request, admin: models.User = Depends(login_required),
                                 db: Session = Depends(get_db)):
    players = db.query(models.Player).order_by(models.Player.nickname).all()
    return render_template("player_management.html", {
        "request": request,
        "user": admin,
        "players": players,
        "Position": models.Position
    })


@app.post("/players/", response_model=schemas.Player, name="create_player_api", status_code=status.HTTP_201_CREATED,
          tags=["api_player"])
def create_player_api(player: schemas.PlayerCreate, db: Session = Depends(get_db),
                      admin: models.User = Depends(login_required)):
    existing_player = db.query(models.Player).filter(models.Player.nickname == player.nickname).first()
    if existing_player:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 사용 중인 닉네임입니다.")
    tier_score = calculate_tier_score(player.tier, player.division, player.lp)

    db_player = models.Player(
        nickname=player.nickname, tier=player.tier, division=player.division,
        player_position=player.position, sub_position=player.sub_position, lp=player.lp,
        tier_score=tier_score, match_score=tier_score
    )
    try:
        db.add(db_player)
        db.commit()
        db.refresh(db_player)
        return schemas.Player.from_orm(db_player)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"플레이어 저장 중 오류: {e}")


@app.put("/players/{player_id}", response_model=schemas.Player, name="update_player_api", tags=["api_player"])
def update_player_api(player_id: int, player_data: schemas.PlayerCreate, db: Session = Depends(get_db),
                      admin: models.User = Depends(login_required)):
    player_in_db = db.query(models.Player).filter(models.Player.id == player_id).first()
    if not player_in_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="플레이어를 찾을 수 없습니다")
    if player_data.nickname != player_in_db.nickname and \
            db.query(models.Player).filter(models.Player.nickname == player_data.nickname).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 사용 중인 닉네임입니다.")

    tier_score = calculate_tier_score(player_data.tier, player_data.division, player_data.lp)
    player_in_db.nickname = player_data.nickname
    player_in_db.tier = player_data.tier
    player_in_db.division = player_data.division
    player_in_db.player_position = player_data.position
    player_in_db.sub_position = player_data.sub_position
    player_in_db.lp = player_data.lp
    player_in_db.tier_score = tier_score
    try:
        db.commit()
        db.refresh(player_in_db)
        return schemas.Player.from_orm(player_in_db)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"플레이어 업데이트 중 오류: {e}")


@app.delete("/players/{player_id}", name="delete_player_api", status_code=status.HTTP_200_OK, tags=["api_player"])
def delete_player_api(player_id: int, db: Session = Depends(get_db), admin: models.User = Depends(login_required)):
    player = db.query(models.Player).filter(models.Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="플레이어를 찾을 수 없습니다")
    try:
        db.delete(player)
        db.commit()
        return {"message": f"플레이어 '{player.nickname}' 삭제 완료."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"플레이어 삭제 오류: {e}")


@app.get("/match-maker", response_class=HTMLResponse, name="match_maker_page")
async def match_maker_page(request: Request, admin: models.User = Depends(login_required),
                           db: Session = Depends(get_db)):
    players = db.query(models.Player).order_by(models.Player.nickname).all()
    recent_matches = db.query(models.Match).order_by(models.Match.match_date.desc()).limit(10).all()
    return render_template("match_maker.html", {
        "request": request,
        "user": admin,
        "players": players,
        "recent_matches": recent_matches
    })


@app.get("/matches/", response_model=List[schemas.Match], name="get_matches_api", tags=["api_match"])
def get_matches_api(db: Session = Depends(get_db), admin: models.User = Depends(login_required)):
    matches_orm = db.query(models.Match).order_by(models.Match.match_date.desc()).limit(20).all()
    return [schemas.Match.from_orm(match) for match in matches_orm]


@app.post("/match/", response_model=schemas.MatchWithTeams, name="create_match_api",
          status_code=status.HTTP_201_CREATED, tags=["api_match"])
def create_match_api(payload: schemas.MatchCreate, db: Session = Depends(get_db),
                     admin: models.User = Depends(login_required)):
    player_ids = payload.player_ids
    if len(player_ids) != 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="정확히 10명의 플레이어가 필요합니다.")

    players_in_db = db.query(models.Player).filter(models.Player.id.in_(player_ids)).all()
    if len(players_in_db) != 10:
        missing_ids = set(player_ids) - {p.id for p in players_in_db}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"일부 플레이어 ID를 찾을 수 없습니다: {list(missing_ids)}")

    try:
        blue_team_ordered, red_team_ordered = balance_teams(players_in_db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    blue_avg_tier = sum(p.tier_score for p in blue_team_ordered) / 5 if blue_team_ordered else 0
    red_avg_tier = sum(p.tier_score for p in red_team_ordered) / 5 if red_team_ordered else 0
    blue_avg_match = sum(p.match_score for p in blue_team_ordered) / 5 if blue_team_ordered else 0
    red_avg_match = sum(p.match_score for p in red_team_ordered) / 5 if red_team_ordered else 0
    balance_val = abs(blue_avg_tier - red_avg_tier)

    KST = timezone(timedelta(hours=9))
    db_match = models.Match(
        blue_team_avg_score=blue_avg_tier,
        red_team_avg_score=red_avg_tier,
        blue_team_match_score=blue_avg_match,
        red_team_match_score=red_avg_match,
        balance_score=balance_val,
        match_date=datetime.now(KST)
    )

    try:
        db.add(db_match)
        db.flush()

        # 팀 배정 시 새 컬럼명 사용
        for i, p in enumerate(blue_team_ordered):
            db.add(models.TeamAssignment(
                team="BLUE",
                match_id=db_match.id,
                player_id=p.id,
                assigned_player_position=POSITIONS_ORDER[i]  # assigned_position → assigned_player_position
            ))
        for i, p in enumerate(red_team_ordered):
            db.add(models.TeamAssignment(
                team="RED",
                match_id=db_match.id,
                player_id=p.id,
                assigned_player_position=POSITIONS_ORDER[i]  # assigned_position → assigned_player_position
            ))

        db.commit()
        db.refresh(db_match)

        return schemas.MatchWithTeams(
            id=db_match.id,
            match_date=db_match.match_date,
            blue_team_avg_score=db_match.blue_team_avg_score,
            red_team_avg_score=db_match.red_team_avg_score,
            blue_team_match_score=db_match.blue_team_match_score,
            red_team_match_score=db_match.red_team_match_score,
            balance_score=db_match.balance_score,
            winner=db_match.winner,
            is_completed=db_match.is_completed,
            blue_team=[schemas.Player.from_orm(p) for p in blue_team_ordered],
            red_team=[schemas.Player.from_orm(p) for p in red_team_ordered]
        )
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"매치 저장 오류: {str(e)}")


@app.post("/matches/multi-group/", response_model=List[schemas.MatchWithTeams], name="create_multiple_matches_api",
          status_code=status.HTTP_201_CREATED, tags=["api_match"])
def create_multiple_matches_api(payload: schemas.MatchCreate, db: Session = Depends(get_db),
                                admin: models.User = Depends(login_required)):
    player_ids = payload.player_ids
    num_players = len(player_ids)
    print(f"DEBUG: Multi-match API 호출됨, 플레이어 ID 수: {num_players}")

    if num_players == 0 or num_players % 10 != 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"플레이어 수는 10의 배수여야 합니다. 현재 {num_players}명.")

    all_players_in_db = db.query(models.Player).filter(models.Player.id.in_(player_ids)).all()
    if len(all_players_in_db) != num_players:
        missing_ids = set(player_ids) - {p.id for p in all_players_in_db}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"일부 플레이어 ID({len(missing_ids)}명)를 찾을 수 없습니다: {list(missing_ids)[:5]}")

    print(f"DEBUG: DB에서 찾은 플레이어 수: {len(all_players_in_db)}")

    try:
        player_groups = distribute_players_to_groups(all_players_in_db, group_size=10)
        print(f"DEBUG: 플레이어 그룹 분배 결과 (그룹 수: {len(player_groups)})")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"그룹 분배 오류: {str(e)}")

    if not player_groups and num_players > 0:
        print(f"DEBUG: distribute_players_to_groups가 빈 리스트 반환 (플레이어 수: {num_players})")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="플레이어 그룹 분배에 실패했습니다 (결과 없음).")

    created_matches_with_teams: List[schemas.MatchWithTeams] = []
    KST = timezone(timedelta(hours=9))

    for group_idx, player_group_for_match in enumerate(player_groups):
        print(f"DEBUG: 그룹 {group_idx} 매치 생성 시작, 플레이어 수: {len(player_group_for_match)}")
        if len(player_group_for_match) != 10:
            print(f"CRITICAL: 그룹 {group_idx}의 플레이어 수가 10명이 아님 ({len(player_group_for_match)}명). 건너뜀.")
            continue

        try:
            blue_team_ordered, red_team_ordered = balance_teams(player_group_for_match)
            print(
                f"DEBUG: 그룹 {group_idx} 팀 밸런싱 완료. 블루: {[p.nickname for p in blue_team_ordered]}, 레드: {[p.nickname for p in red_team_ordered]}")
        except ValueError as e:
            print(f"ERROR: 그룹 {group_idx} 팀 밸런싱 중 오류: {str(e)}. 이 그룹 건너뜀.")
            traceback.print_exc()
            continue
        except Exception as e_balance:
            print(f"CRITICAL ERROR: 그룹 {group_idx} 팀 밸런싱 중 예상치 못한 오류: {str(e_balance)}. 이 그룹 건너뜀.")
            traceback.print_exc()
            continue

        if not blue_team_ordered or not red_team_ordered:
            print(f"WARNING: 그룹 {group_idx}의 balance_teams 결과가 유효하지 않음 (팀이 비어있음). 건너뜀.")
            continue

        blue_avg_tier = sum(p.tier_score for p in blue_team_ordered) / 5 if blue_team_ordered else 0
        red_avg_tier = sum(p.tier_score for p in red_team_ordered) / 5 if red_team_ordered else 0
        blue_avg_match = sum(p.match_score for p in blue_team_ordered) / 5 if blue_team_ordered else 0
        red_avg_match = sum(p.match_score for p in red_team_ordered) / 5 if red_team_ordered else 0
        balance_val = abs(blue_avg_tier - red_avg_tier)

        db_match_multi = models.Match(
            match_date=datetime.now(KST) + timedelta(seconds=group_idx),
            blue_team_avg_score=blue_avg_tier,
            red_team_avg_score=red_avg_tier,
            blue_team_match_score=blue_avg_match,
            red_team_match_score=red_avg_match,
            balance_score=balance_val
        )

        try:
            db.add(db_match_multi)
            db.flush()
            for i, p in enumerate(blue_team_ordered):
                db.add(models.TeamAssignment(
                    team="BLUE",
                    match_id=db_match_multi.id,
                    player_id=p.id,
                    assigned_player_position=POSITIONS_ORDER[i]
                ))
            for i, p in enumerate(red_team_ordered):
                db.add(models.TeamAssignment(
                    team="RED",
                    match_id=db_match_multi.id,
                    player_id=p.id,
                    assigned_player_position=POSITIONS_ORDER[i]
                ))
            db.commit()
            db.refresh(db_match_multi)

            match_schema = schemas.MatchWithTeams(
                id=db_match_multi.id,
                match_date=db_match_multi.match_date,
                blue_team_avg_score=db_match_multi.blue_team_avg_score,
                red_team_avg_score=db_match_multi.red_team_avg_score,
                blue_team_match_score=db_match_multi.blue_team_match_score,
                red_team_match_score=db_match_multi.red_team_match_score,
                balance_score=db_match_multi.balance_score,
                winner=db_match_multi.winner,
                is_completed=db_match_multi.is_completed,
                blue_team=[schemas.Player.from_orm(p) for p in blue_team_ordered],
                red_team=[schemas.Player.from_orm(p) for p in red_team_ordered]
            )
            created_matches_with_teams.append(match_schema)
            print(f"DEBUG: 그룹 {group_idx} 매치 ID {db_match_multi.id} 생성 및 저장 완료.")
        except Exception as e_save:
            db.rollback()
            print(f"ERROR: 그룹 {group_idx} 매치 저장 중 오류: {str(e_save)}. 이 그룹 건너뜀.")
            traceback.print_exc()

    if not created_matches_with_teams and num_players > 0:
        print(f"DEBUG: 최종 생성된 매치 없음 (입력 플레이어 수: {num_players})")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="모든 그룹에 대한 매치 생성에 실패했습니다. 서버 로그를 확인하세요.")

    print(f"DEBUG: 최종 생성된 매치 수: {len(created_matches_with_teams)}")
    return created_matches_with_teams


@app.get("/match/{match_id}", response_class=HTMLResponse, name="match_detail_page")
async def match_detail_page(match_id: int, request: Request, admin: models.User = Depends(login_required),
                            db: Session = Depends(get_db)):
    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="매치를 찾을 수 없습니다")

    blue_assignments = db.query(models.TeamAssignment).filter_by(match_id=match_id, team="BLUE").order_by(
        models.TeamAssignment.id).all()
    red_assignments = db.query(models.TeamAssignment).filter_by(match_id=match_id, team="RED").order_by(
        models.TeamAssignment.id).all()

    # 새 컬럼명 사용
    blue_team_info = [
        {"player": db.query(models.Player).get(ta.player_id),
         "assigned_pos_value": ta.assigned_player_position.value} for ta
        in blue_assignments if db.query(models.Player).get(ta.player_id)]
    red_team_info = [
        {"player": db.query(models.Player).get(ta.player_id),
         "assigned_pos_value": ta.assigned_player_position.value} for ta
        in red_assignments if db.query(models.Player).get(ta.player_id)]

    return render_template("match_detail.html", {
        "request": request,
        "user": admin,
        "match": match,
        "blue_team_info": blue_team_info,
        "red_team_info": red_team_info,
        "positions_order": [p.value for p in POSITIONS_ORDER]
    })


@app.post("/match/{match_id}/result", name="record_match_result_api", status_code=status.HTTP_200_OK,
          tags=["api_match"])
def record_match_result_api(match_id: int, result_data: schemas.MatchResult, db: Session = Depends(get_db),
                            admin: models.User = Depends(login_required)):
    if result_data.match_id != match_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="경로와 본문의 매치 ID 불일치.")
    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="매치를 찾을 수 없습니다")
    if match.is_completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 결과가 등록된 매치입니다")
    if result_data.winner not in ["BLUE", "RED"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="승리 팀은 'BLUE' 또는 'RED'여야 합니다.")
    if not update_team_match_scores(result_data.winner, match_id, db):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="매치 결과 처리 중 오류 발생.")
    db.refresh(match)
    return {"message": f"{result_data.winner} 팀 승리! 결과 등록 완료.", "match_id": match_id, "winner": result_data.winner}

@app.delete("/match/{match_id}", name="delete_match_api", status_code=status.HTTP_200_OK, tags=["api_match"])
def delete_match_api(match_id: int, db: Session = Depends(get_db), admin: models.User = Depends(login_required)):
    """미완료된 매치를 삭제하는 API 엔드포인트"""
    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="매치를 찾을 수 없습니다.")

    if match.is_completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 결과가 등록된 매치는 삭제할 수 없습니다.")

    try:
        # TeamAssignment는 Match 모델의 cascade 설정으로 자동 삭제됩니다.
        db.delete(match)
        db.commit()
        return JSONResponse(status_code=status.HTTP_200_OK, content={"message": f"매치(ID: {match_id})가 성공적으로 삭제되었습니다."})
    except Exception as e:
        db.rollback()
        print(f"매치 삭제 중 오류 발생: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="매치 삭제 중 서버 오류가 발생했습니다.")

@app.get("/player-stats", response_class=HTMLResponse, name="player_stats_page")
async def player_stats_page(request: Request, admin: models.User = Depends(login_required),
                            db: Session = Depends(get_db), sort_by: str = Query("match_score",
                                                                                enum=["nickname", "match_score",
                                                                                      "total_games", "win_rate",
                                                                                      "tier_score"]),
                            order: str = Query("desc", enum=["asc", "desc"])):
    players = db.query(models.Player).all()
    player_stats_data = []
    for p in players:
        total_games = p.win_count + p.lose_count
        win_rate = (p.win_count / total_games * 100) if total_games > 0 else 0
        player_stats_data.append({
            "player": p,
            "total_games": total_games,
            "win_rate": win_rate,
            "clean_position": p.position.value if p.position else "N/A",
            "clean_sub_position": p.sub_position.value if p.sub_position else "없음",
            "clean_tier": p.tier.value if p.tier else "N/A"
        })

    key_map = {
        "match_score": lambda x: x["player"].match_score,
        "total_games": lambda x: x["total_games"],
        "win_rate": lambda x: x["win_rate"],
        "nickname": lambda x: x["player"].nickname.lower(),
        "tier_score": lambda x: x["player"].tier_score
    }
    if sort_by in key_map:
        player_stats_data.sort(key=key_map[sort_by], reverse=(order == "desc"))

    return render_template("player_stats.html", {
        "request": request,
        "user": admin,
        "player_stats": player_stats_data,
        "sort_by": sort_by,
        "order": order
    })


@app.get("/help", response_class=HTMLResponse, name="help_page")
async def help_page(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user_from_cookie(request, db)
    return render_template("help.html", {"request": request, "user": user})


@app.post("/token", response_model=schemas.Token, tags=["api_auth"], name="api_login_for_token")
async def login_for_access_token_api(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="아이디 또는 비밀번호가 잘못되었습니다.",
                            headers={"WWW-Authenticate": "Bearer"})

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire_datetime = datetime.now(timezone.utc) + access_token_expires
    access_token = create_access_token(data={"sub": user.user_id}, expires_delta=access_token_expires)

    new_session = models.ActiveSession(user_id=user.id, token=access_token, expires_at=expire_datetime)
    db.add(new_session)
    db.commit()

    return {"access_token": access_token, "token_type": "bearer"}


# API Auth check (토큰 기반으로 세션 확인)
async def get_current_api_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증 정보를 확인할 수 없습니다.",
                                          headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_from_token: Optional[str] = payload.get("sub")
        if user_id_from_token is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    active_session = db.query(models.ActiveSession).filter(models.ActiveSession.token == token).first()
    if not active_session or active_session.expires_at < datetime.now(timezone.utc):
        raise credentials_exception

    user = active_session.user
    if user is None or user.user_id != ADMIN_USER_ID:
        raise credentials_exception

    return user


@app.get("/api/users/me", response_model=schemas.User, tags=["api_auth"], name="api_read_current_user")
async def read_users_me_api(current_user: models.User = Depends(get_current_api_user)):
    return schemas.User.from_orm(current_user)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)