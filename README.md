# 롤이터 - LoL 팀 매칭 시스템

리그 오브 레전드 클랜 내전을 위한 자동 팀 밸런싱 및 결과 관리 시스템입니다.

## 🎮 주요 기능

- **플레이어 관리**: 클랜원의 티어, 포지션, 실력 정보 등록 및 관리
- **자동 팀 매칭**: 10명의 플레이어를 실력과 포지션을 고려하여 균형있는 두 팀으로 자동 분배
- **매치 결과 관리**: 경기 결과 기록 및 승패에 따른 개인 점수 업데이트
- **통계 시스템**: 플레이어별 전적, 승률, 매칭 점수 통계 제공
- **멀티 매치**: 20명, 30명 등 다수 인원에 대한 여러 매치 동시 생성

## 🛠️ 기술 스택

- **Backend**: FastAPI, SQLAlchemy
- **Database**: PostgreSQL (배포) / SQLite (개발)
- **Frontend**: Jinja2 Templates, Tailwind CSS
- **Authentication**: JWT, Passlib
- **Deployment**: uvicorn, 환경변수 기반 설정

## 🔧 팀 밸런싱 알고리즘

시스템은 다음 요소들을 종합적으로 고려하여 최적의 팀을 구성합니다:

1. **티어 점수**: 각 플레이어의 랭크 티어를 점수화
2. **포지션 적합도**: 주/부 포지션 선호도 반영
3. **매칭 점수**: 실제 경기 결과를 반영한 동적 점수
4. **밸런스 최적화**: 두 팀 간 실력 차이 최소화

### 점수 시스템

- **승리 시**: +25~35점 (포지션 선호도에 따라 차등)
- **패배 시**: -20~30점 (포지션 선호도에 따라 차등)
- **포지션별 가중치**: 주 포지션 > 부 포지션 > 비선호 포지션

## 📦 설치 및 실행

### 1. 프로젝트 클론

```bash
git clone <repository-url>
cd lol-team-matcher
```

### 2. 가상환경 생성 및 활성화

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. 의존성 설치

```bash
pip install fastapi uvicorn sqlalchemy psycopg2-binary python-dotenv
pip install python-multipart jinja2 python-jose[cryptography] passlib[bcrypt]
pip install psutil  # 메모리 모니터링용
```

### 4. 환경변수 설정

`.env` 파일 생성:

```env
# 개발 환경
APP_ENV=development

# 배포 환경용 (필요시)
APP_ENV=production
user=your_db_user
password=your_db_password
host=your_db_host
port=5432
dbname=your_db_name

# JWT 설정
SECRET_KEY=your-super-secret-key-here
ADMIN_USER_ID=admin
ADMIN_PASSWORD=your-admin-password
```

### 5. 애플리케이션 실행

```bash
# 개발 환경 (SQLite 사용)
python main.py

# 또는 uvicorn 직접 실행
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

애플리케이션이 `http://localhost:8000`에서 실행됩니다.

## 🗃️ 데이터베이스 구조

### 주요 테이블

- **users**: 관리자 사용자 정보
- **active_sessions**: 활성 세션 관리 (동시 로그인 방지)
- **players**: 플레이어 정보 (닉네임, 티어, 포지션, 점수 등)
- **matches**: 매치 정보 (일시, 팀 평균 점수, 밸런스 점수 등)
- **team_assignments**: 매치별 팀 배정 정보

### 데이터베이스 초기화

애플리케이션 첫 실행 시 자동으로:
- 테이블 생성
- 관리자 계정 생성 (`admin` / 환경변수의 비밀번호)

## 🎯 사용 방법

### 1. 관리자 로그인
- 메인 페이지에서 "관리자 로그인" 클릭
- ID: `admin`, 비밀번호: 환경변수에 설정한 값

### 2. 플레이어 등록
- "플레이어 관리" 메뉴에서 새 플레이어 등록
- 닉네임, 티어, 주/부 포지션 입력

### 3. 팀 매칭
- "팀 매칭 및 결과 기록" 메뉴에서 참여자 10명 선택
- "팀 매칭 시작" 버튼으로 자동 팀 생성

### 4. 결과 입력
- 매치 상세 페이지에서 승리 팀 선택
- 자동으로 개인 점수 업데이트

### 5. 통계 확인
- "플레이어 통계" 메뉴에서 전체 플레이어 성과 확인
- 매칭 점수, 승률 등으로 정렬 가능

## 🚀 배포

### 환경변수 설정

배포 환경에서는 `APP_ENV=production`으로 설정하고 PostgreSQL 연결 정보를 제공해야 합니다.

```env
APP_ENV=production
user=production_db_user
password=production_db_password
host=production_db_host
port=5432
dbname=production_db_name
SECRET_KEY=production-secret-key
ADMIN_PASSWORD=secure-admin-password
```

### 성능 최적화

- 메모리 사용량 모니터링 및 자동 정리
- 만료된 세션 자동 삭제
- 데이터베이스 연결 풀링
- GZip 압축 지원

## 📊 API 엔드포인트

### 인증
- `POST /token`: API 토큰 발급
- `POST /login`: 웹 로그인
- `GET /logout`: 로그아웃

### 플레이어 관리
- `POST /players/`: 플레이어 등록
- `PUT /players/{player_id}`: 플레이어 정보 수정
- `DELETE /players/{player_id}`: 플레이어 삭제

### 매치 관리
- `POST /match/`: 단일 매치 생성 (10명)
- `POST /matches/multi-group/`: 다중 매치 생성 (10의 배수)
- `POST /match/{match_id}/result`: 매치 결과 등록
- `DELETE /match/{match_id}`: 미완료 매치 삭제

## 🔒 보안 기능

- JWT 기반 인증
- 관리자 전용 액세스
- 동시 로그인 방지
- 세션 만료 관리
- CSRF 보호 (SameSite 쿠키)

## 📱 반응형 디자인

모든 페이지는 Tailwind CSS를 사용하여 모바일, 태블릿, 데스크톱에서 최적화된 화면을 제공합니다.

## 🐛 문제 해결

### 일반적인 문제

1. **데이터베이스 연결 오류**
   - 환경변수 설정 확인
   - 데이터베이스 서버 상태 확인

2. **포트 충돌**
   - `PORT` 환경변수로 다른 포트 지정

3. **메모리 부족**
   - 시스템이 자동으로 메모리를 모니터링하고 정리
   - 로그에서 메모리 사용량 확인 가능

### 로그 확인

애플리케이션은 상세한 로그를 제공합니다:
- 데이터베이스 연결 상태
- 메모리 사용량
- 세션 관리 상태
- API 호출 결과

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## ❓ 지원

문제가 발생하거나 기능 요청이 있으시면 이슈를 등록해 주세요.