# 사과 과수화상병 AI 판별 서비스

## 현재 구현 상태

- React + TypeScript 화면: 사진 업로드, 실제 통계, 검사 이력 갤러리, 안내형 FAQ
- FastAPI + MySQL 8 + Alembic: 검사 묶음, 이미지, 예측, 모델 버전 스키마
- 저장소: 로컬 개발 파일 저장소(`STORAGE_BACKEND=local`)와 AWS S3 전환형 어댑터
- YOLO Detection: `best.pt`가 사과 정상/과수화상병 의심 두 클래스의 **Detection** 모델일 때만 추론합니다. 최고 신뢰도 객체와 실제 Bounding Box 결과를 저장합니다. 표준 클래스명(`apple_healthy`, `apple_fire_blight`)과 학습 모델의 별칭(`normal`, `fire_blight`)은 서비스 표준 코드로 정규화합니다.
- 모델이 없거나 유효하지 않으면 임의 판별값을 만들지 않고 파일별 실패 사유를 저장합니다.

## 로컬 실행

```powershell
Copy-Item .env.example .env
docker compose up --build
```

- 화면: <http://localhost:5173>
- API 문서: <http://localhost:8000/docs>
- 상태: <http://localhost:8000/api/v1/health>

모델을 준비했다면 `inference_api/models/best.pt`에 두고 컨테이너를 다시 시작합니다. 2클래스 모델이 아닌 경우 서버는 준비되지 않은 상태로 표시합니다.

AWS 배포 설계와 점검 사항은 [DEPLOYMENT_AWS.md](DEPLOYMENT_AWS.md)를 참고하세요.

> 아래 내용은 기존 Phase 1 기반 환경의 보존 문서입니다. PostgreSQL/SeaweedFS, `/api/images`, `/health/*` 관련 설명은 현재 구현에 적용되지 않으며, 이 문서 상단의 MySQL 및 `/api/v1` 안내를 우선합니다.

Common PRD와 Function PRD를 기준으로 구성하는 React + TypeScript + Vite / FastAPI 서비스입니다. 현재 **Phase 1 (Foundation)** 만 구현되어 있습니다. 화면에서 실제 분석 결과나 가짜 통계를 제공하지 않습니다.

## 프로젝트 구조

```text
.
├── backend/
│   ├── app/                 # FastAPI 애플리케이션 및 도메인/API
│   ├── tests/               # 백엔드 단위/통합 테스트
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/                 # React + TypeScript 화면
│   ├── Dockerfile
│   └── package.json
├── data/                    # 제공된 원천/라벨 데이터 (현재 변경하지 않음)
├── docker-compose.yml        # PostgreSQL, SeaweedFS S3, API, 프런트 로컬 환경
├── .env.example
└── README.md
```

후속 구조는 `backend/alembic/` (DB 마이그레이션), `worker/` (비동기 YOLO 추론), `infra/terraform/` (AWS 인프라), `.github/workflows/` (검증 및 배포), `docs/` (운영·모델·API 문서)로 확장합니다.

## 개발 단계

1. **Foundation** — 저장소 기반, Docker Compose, PostgreSQL/S3 호환 저장소, FastAPI/React, health endpoint 및 기본 테스트.
2. **Database** — SQLAlchemy 모델, Alembic 마이그레이션, 데이터 접근 계층.
3. **Authentication** — 가입/로그인, 안전한 세션, 역할 기반 API 권한.
4. **Image Upload** — 업로드 검증, S3 저장, 이미지 및 과원 데이터 흐름.
5. **YOLO Integration** — 작업 큐/worker, 모델 인터페이스와 실제 가중치 연결.
6. **Analysis UI** — 업로드·분석 상태·결과·이력·공식 대응 안내 화면.
7. **Admin** — 사용자, 모델, 가이드, 감사 및 시스템 관리.
8. **Testing** — 통합/E2E, 권한·접근성·성능·모델 검증.
9. **AWS Deployment** — 승인 후 IaC, ECR/ECS, RDS, S3, ALB/HTTPS, 모니터링 및 CI/CD.

## 로컬 실행

Docker Desktop/Engine이 설치 및 실행되어야 합니다.

```powershell
Copy-Item .env.example .env
# .env의 S3_ACCESS_KEY와 S3_SECRET_KEY를 영문·숫자 조합의 임의 값으로 변경합니다.
docker compose up --build
```

- 프런트엔드: <http://localhost:5173>
- FastAPI 문서: <http://localhost:8000/docs>
- API 생존 확인: <http://localhost:8000/health/live>
- API 및 DB 준비 확인: <http://localhost:8000/health/ready>
- S3 API: <http://localhost:8333> (SeaweedFS; 인증정보는 `.env`의 `S3_ACCESS_KEY`, `S3_SECRET_KEY`)
- PostgreSQL: `localhost:5432`

`.env.example`의 저장소 인증정보는 교체용 예시 문자열이며 실제 운영 인증정보가 아닙니다. Compose에는 저장소 인증정보 기본값이 없으므로 두 값을 설정해야 시작됩니다. S3 호환 API는 SeaweedFS에 자동으로 버킷을 만들며, 이미지 업로드·목록·다운로드는 FastAPI의 `/api/images`에서 제공합니다.

종료 시 `docker compose down`을 실행합니다. PostgreSQL 데이터는 `postgres_data`, 새 SeaweedFS 데이터는 `seaweedfs_data` named volume에 보존됩니다. 기존 MinIO `minio_data` 볼륨은 `seaweedfs_data`와 분리되어 재사용하거나 자동 이전하지 않습니다. 데이터 볼륨까지 지우는 `docker compose down -v`는 로컬 DB, SeaweedFS 및 보존된 기존 MinIO 볼륨을 삭제하므로 주의하세요.

### 이미지 API

- `POST /api/images`: `file` multipart 필드로 이미지 업로드. `image/*` 콘텐츠 유형만 허용하며 고유한 S3 객체 키를 반환합니다.
- `GET /api/images`: 버킷 객체 키, 크기, 수정 시각 조회.
- `GET /api/images/{key}`: 저장된 이미지 다운로드.

```powershell
curl.exe -F "file=@leaf.jpg;type=image/jpeg" http://localhost:8000/api/images
curl.exe http://localhost:8000/api/images
curl.exe -o downloaded.jpg http://localhost:8000/api/images/<반환된-key>
```

AWS 배포에서는 `S3_ENDPOINT_URL`을 설정하지 않고, AWS 자격 증명은 IAM 역할 등 AWS 표준 자격 증명 체계로 제공하며, `S3_CREATE_BUCKET=false`로 설정합니다. Compose의 `S3_ACCESS_KEY`/`S3_SECRET_KEY`는 로컬 SeaweedFS 전용 계정이므로 AWS 자격 증명으로 사용하지 않습니다.

### 프런트엔드 단독 검증

```powershell
Set-Location frontend
npm install
npm run build
```

단독 개발 서버에서 API를 `localhost:8000`으로 실행하면 Vite가 `/api` 요청을 자동으로 프록시합니다. 다른 주소를 사용할 때는 `VITE_API_PROXY_TARGET`을 설정하세요. Docker Compose는 컨테이너 네트워크의 backend 서비스로 프록시합니다.

### 백엔드 테스트

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
```

## Phase 1 구현 및 경계

- React 페이지는 FastAPI의 `/health/live`에 직접 요청해 연결 상태를 표시합니다.
- `/health/ready`는 PostgreSQL `SELECT 1` 연결을 검사하고 DB 연결 실패를 HTTP 503으로 명시합니다.
- Docker Compose 개발 환경에 PostgreSQL 16과 단일 노드 SeaweedFS S3를 포함합니다. FastAPI는 이미지 업로드 시 버킷을 확인/생성하고 객체 목록 및 다운로드를 지원합니다. 데이터베이스 스키마는 아직 구현하지 않았습니다.
- Python 개발 컨테이너는 3.12를 사용합니다 (PRD의 Python 3.11+ 범위 내). 운영 기본값 확정은 별도 검토합니다.
- YOLO 가중치가 제공되지 않았으므로 모델 추론은 구현하거나 모의 결과로 대체하지 않았습니다.
- AWS 리소스 생성 및 비용 발생 작업은 수행하지 않았습니다.

## 확인이 필요한 제품/운영 결정

다음 항목은 PRD에 확정값이 없어 관련 단계 착수 전에 결정이 필요합니다.

- 공개 서비스인지 기관 내부 서비스인지, 계정 승인/검토자 부여 절차.
- 실제 지원 작물·부위 및 라벨 클래스 정의, 데이터셋/가중치 형식·라이선스.
- 공식 대응 가이드 담당 기관, 적용 지역 및 검토·승인 책임자.
- 개인정보/이미지 보존 기간과 사용자 삭제 요청 처리 정책.
- 동시 분석량, 분석 지연 목표, 운영 예산 및 CPU/GPU 선택.

브랜드 `FireBlight AI`는 PRD의 임시 이름이며, 현재 UI에서는 한국어 서비스 설명명을 사용합니다.

## AWS 배포용 GitHub 파일 관리

GitHub에는 AWS가 애플리케이션을 다시 빌드하고 배포하는 데 필요한 **소스 코드와 설정**을 올립니다. 개인 PC에서 생성되거나, 비밀 정보 또는 대용량 산출물인 파일은 올리지 않습니다.

### GitHub에 포함하는 파일

- 백엔드: `backend/app/`, `backend/requirements*.txt`, `backend/Dockerfile*`, Alembic migration 파일
- 프런트엔드: `frontend/src/`, `package.json`, `package-lock.json`, `Dockerfile.prod`, `nginx.conf`
- 배포 및 개발 설정: `docker-compose.yml`, `.dockerignore`, `.gitignore`, `.env.example`
- 운영 문서·검증 자료: `DEPLOYMENT_AWS.md`, `docs/`, 테스트와 재현 가능한 스크립트

### GitHub에서 제외하는 파일

| 대상 | 예시 | 제외 이유 |
| --- | --- | --- |
| 비밀값 | `.env`, AWS 접근 키, DB 비밀번호, OpenAI API 키 | 공개 저장소 또는 권한 있는 저장소에서도 유출 위험이 있습니다. AWS에서는 Secrets Manager 또는 SSM Parameter Store를 사용합니다. |
| 설치 결과물 | `.venv/`, `node_modules/` | 운영체제마다 달라지고 용량이 큽니다. `requirements.txt`와 `package-lock.json`으로 다시 설치합니다. |
| 실행 중 생성물 | `uploads/`, 로그, 캐시, `__pycache__/` | 컨테이너·PC마다 달라지며 다시 생성됩니다. 운영 업로드 파일은 S3에 보관합니다. |
| AI 모델·학습 데이터 | `best.pt`, `*.pth`, 데이터셋, 대용량 ZIP | 대용량 산출물이며 접근 권한과 버전을 별도로 관리해야 합니다. |
| 개인 설정·임시 파일 | `.aws/`, `.vscode/`, `.idea/`, `~$*.xlsx` | 개인 환경 설정 또는 자격 증명이 포함될 수 있습니다. |

`.gitignore`에 등록된 파일은 `git add -A`를 실행해도 GitHub에 추가되지 않습니다. 현재 프로젝트에서는 `.env`, `.venv`, `node_modules`, `*.pt`, `*.pth`, `*.zip` 등이 이에 해당합니다. `.env.example`은 실제 비밀값이 없는 예시 파일이므로 포함합니다.

### `best.pt` 모델 배포

`best.pt`는 설치 과정에서 자동으로 만들어지는 파일이 아니라 학습이 끝난 AI 모델 파일입니다. 로컬 개발에서는 `inference_api/models/best.pt`에 별도로 두고 Docker Compose가 `/app/models/best.pt`로 읽기 전용 마운트합니다.

AWS 운영 환경에서는 실제 모델 파일을 GitHub에 넣지 않습니다. Private S3 또는 EFS에 모델을 보관하고 ECS task가 읽도록 구성한 뒤, `MODEL_PATH`를 모델 파일 위치로 지정합니다. S3 방식을 사용할 경우 ECS Task Role에 모델 객체의 `s3:GetObject` 권한과 컨테이너 시작 시 모델을 내려받는 절차가 필요합니다. 배포 후 `/api/v1/health`에서 `model_ready: true`인지 확인합니다.
