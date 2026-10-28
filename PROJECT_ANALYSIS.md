# 프로젝트 분석 보고서

작성일: 2026-10-26 (KST)  
분석 원칙: 파일을 삭제·이동·수정하지 않고 읽기 전용으로 확인했습니다. 이 보고서만 새로 만들었습니다. `.env`의 실제 값은 열람·기록하지 않았으며, 예시 설정의 비밀값도 본문에 쓰지 않았습니다.

## 1. 한눈에 보는 현재 상태

이 저장소는 **과수 질병 이미지 서비스의 기반(Phase 1)** 과 **YOLO 학습용 데이터셋 준비 도구**가 함께 있는 프로젝트입니다.

- 실제 웹 서비스: React 프런트엔드, FastAPI 백엔드, PostgreSQL, S3 호환 파일 저장소(로컬에서는 SeaweedFS)를 Docker Compose로 띄우도록 구성되어 있습니다.
- 실제 구현 완료 범위: API 생존/DB 준비 상태 확인, 이미지 파일을 오브젝트 스토리지에 업로드·목록 조회·다운로드하는 API.
- 아직 없는 핵심 기능: 사용자/권한, DB 테이블과 마이그레이션, 분석 작업 관리, YOLO 가중치 로드 및 추론, 분석 결과 저장, PDF 리포트 생성, AWS 인프라 코드와 CI/CD.
- 루트의 `Farm Doctor Page.html`은 완성 화면처럼 보이지만, 코드상 `simulateYoloDetection()`, `downloadPDFReport()`, `alert()`를 쓰는 **독립 정적 데모**입니다. React 서비스와 연결되어 있지 않습니다.

용어: **API**는 화면과 서버가 데이터를 주고받는 URL 규칙이고, **오브젝트 스토리지**는 이미지처럼 큰 파일을 보관하는 저장소입니다. **가중치(weights)** 는 학습이 끝난 AI 모델 파일입니다.

## 2. 폴더 구조와 역할

```text
aws/
├─ backend/                    FastAPI 서버와 서버 테스트
│  ├─ app/                     health, 이미지 API, S3 저장소 코드
│  ├─ tests/                   health/이미지 API 단위 테스트
│  ├─ Dockerfile               Python 3.12 기반 개발 컨테이너
│  └─ requirements.txt         서버 Python 의존성 목록
├─ frontend/                   React + TypeScript + Vite 웹 화면
│  ├─ src/                     App.tsx, 진입점, CSS
│  ├─ Dockerfile               Node 22 기반 개발 컨테이너
│  ├─ package.json             npm 실행/빌드 명령과 의존성
│  ├─ node_modules/            설치된 npm 패키지 (배포 원본 불필요)
│  └─ dist/                    기존 빌드 산출물 (배포 시 재생성 가능)
├─ data/                       원본 이미지·JSON 라벨 및 생성된 데이터셋 ZIP
│  ├─ images/                  사과/배 정상·질병 이미지
│  ├─ labels/                  이미지에 대응하는 라벨 JSON
│  └─ processed/               YOLO 분류/탐지용 산출물과 ZIP
├─ datasets/                   분류/탐지 데이터셋 ZIP의 별도 사본
├─ scripts/dataset_converter/  원본을 검증하고 YOLO 형식으로 변환하는 CLI
├─ reports/dataset/            데이터셋 검증·분할·매핑 보고서
├─ config/                     9개 클래스 매핑과 코드북 설정
├─ tests/                      데이터셋 변환기 테스트
├─ notebooks/                  데이터셋/YOLO 학습 참고 노트북
├─ prd/ 및 *_PRD.md            요구사항·향후 설계 문서
├─ inference_api/models/       비어 있음; 추론용 모델 파일은 확인되지 않음
├─ .venv/, .venv-1/, backend/.venv/
│                              로컬 Python 가상환경 (배포 원본 불필요)
├─ .tmp_pytest/, .pytest_cache/ 테스트 임시/캐시 (배포 불필요)
├─ docker-compose.yml          로컬 개발용 컨테이너 묶음
├─ .env.example                환경 변수의 이름과 예시만 제공
└─ Farm Doctor Page.html       API 미연동 정적 UI 데모
```

`.git`은 Git 변경 이력을 저장하는 내부 폴더입니다. 현재 `git ls-files` 결과는 0개이고, `git status`에는 거의 모든 프로젝트 파일이 추적되지 않은 파일로 표시됩니다. 즉, 현재 상태만으로는 소스가 Git 이력에 안전하게 커밋되었다고 확인할 수 없습니다.

## 3. 큰 폴더와 파일

아래 수치는 실제 파일 크기를 합산한 값입니다. 권한이 거부된 `.pytest_cache` 및 `data/processed` 내부 폴더는 합산에서 빠질 수 있어, 해당 항목은 ZIP 크기로도 함께 판단했습니다.

### 큰 폴더

| 순위 | 폴더 | 크기(약) | 용도 |
|---:|---|---:|---|
| 1 | `data/` | 5,796 MiB | 원본 이미지·라벨과 처리된 데이터셋 ZIP |
| 2 | `.git/` | 4,134 MiB | Git 객체/이력. 대형 데이터가 이력에 들어간 흔적 |
| 3 | `datasets/` | 3,861 MiB | 분류·탐지 데이터셋 ZIP 사본 |
| 4 | `.venv/` | 121 MiB | 루트 Python 가상환경 |
| 5 | `.venv-1/` | 105 MiB | 두 번째 Python 가상환경 |
| 6 | `backend/` | 81 MiB | 서버 코드와 별도 가상환경 |
| 7 | `frontend/` | 66 MiB | 화면 코드, npm 패키지, 빌드 산출물 |
| 8 | `.tmp_pytest/` | 2.96 MiB | 테스트 임시 파일 |
| 9 | `reports/` | 0.79 MiB | 데이터셋 분석 결과 |
| 10 | `scripts/` | 0.26 MiB | 변환/검증 도구 |

### 큰 파일 TOP 20

| 순위 | 파일 | 크기(약) | 용도/판단 |
|---:|---|---:|---|
| 1 | `.git/objects/11/e833...` | 1,930.93 MiB | Git 내부 객체; 대형 데이터 이력 추정 |
| 2 | `.git/objects/c2/9c0c...` | 1,930.78 MiB | Git 내부 객체; 대형 데이터 이력 추정 |
| 3 | `data/processed/detection.zip` | 1,930.69 MiB | YOLO Detection 산출물 압축본 |
| 4 | `datasets/detection.zip` | 1,930.69 MiB | 위 탐지 ZIP의 별도 사본 |
| 5 | `datasets/classification.zip` | 1,930.30 MiB | YOLO Classification 산출물 압축본 |
| 6 | `data/processed/classification.zip` | 1,930.30 MiB | 위 분류 ZIP의 별도 사본 |
| 7 | `.git/objects/pack/pack-be51...pack` | 267.51 MiB | Git 압축 이력 |
| 8 | `frontend/node_modules/@esbuild/.../esbuild.exe` | 10.13 MiB | 프런트엔드 빌드 도구 바이너리 |
| 9 | `data/images/...0093w..._1.jpg` | 9.91 MiB | 원본 학습 이미지 |
| 10 | `data/images/...0093w..._5.jpg` | 9.79 MiB | 원본 학습 이미지 |
| 11 | `data/images/...0093w..._3.jpg` | 8.67 MiB | 원본 학습 이미지 |
| 12 | `frontend/node_modules/typescript/lib/typescript.js` | 8.63 MiB | TypeScript 컴파일러 |
| 13 | `data/images/...0093w..._2.jpg` | 8.36 MiB | 원본 학습 이미지 |
| 14 | `data/images/...0093w..._4.jpg` | 8.29 MiB | 원본 학습 이미지 |
| 15 | `.venv/Lib/site-packages/PIL/_avif...pyd` | 7.47 MiB | 이미지 처리 라이브러리 바이너리 |
| 16 | `frontend/node_modules/typescript/lib/_tsc.js` | 5.87 MiB | TypeScript 컴파일러 내부 파일 |
| 17 | `.venv/.../pydantic_core...pyd` | 5.29 MiB | FastAPI 데이터 검증용 바이너리 |
| 18 | `.venv-1/.../pydantic_core...pyd` | 5.29 MiB | 위 라이브러리의 중복 가상환경 사본 |
| 19 | `backend/.venv/.../pydantic_core...pyd` | 5.29 MiB | 위 라이브러리의 백엔드 가상환경 사본 |
| 20 | `.venv/.../psycopg_binary/_psycopg.c` | 5.24 MiB | PostgreSQL 연결 드라이버 구성 파일 |

특히 데이터셋 ZIP이 각각 두 위치에 중복되어 있고, Git 객체도 약 4GB입니다. AWS 소스 배포용 Docker 빌드 컨텍스트에는 절대 포함시키면 안 됩니다. 현재 `.dockerignore`는 `data`, `.git`, 가상환경, `node_modules`를 제외하므로 Docker 빌드에는 보호 장치가 있습니다.

## 4. 프런트엔드

- 기술: React 19, TypeScript 5.7, Vite 6, Node 22 Alpine 컨테이너.
- 주요 소스: `frontend/src/main.tsx`가 React를 시작하고, `frontend/src/App.tsx`가 화면을 렌더링합니다.
- 실행 명령: `npm run dev` (Vite 개발 서버), `npm run build` (TypeScript 검사 후 정적 산출물 생성), `npm run test` (실제로는 TypeScript 검사 명령).
- 현재 화면 기능: 시작 시 `GET /api/health/live`를 요청하여 API 연결 상태만 표시합니다. 이미지 선택, 업로드, 결과 표시, 리포트 UI는 React 앱에 구현되어 있지 않습니다.
- 프록시: `vite.config.ts`는 개발 중 `/api/*`를 백엔드로 보낼 때 `/api` 접두어를 제거합니다. 따라서 현재 React의 `/api/health/live` 요청은 `/health/live`로 변환되어 맞습니다. 반면 백엔드 이미지 API의 실제 경로는 `/api/images`라서, 프런트가 같은 규칙으로 `/api/images`를 호출하면 `/images`로 바뀌어 404가 됩니다. 이미지 화면을 연결하기 전에 프록시 규칙 또는 API 경로를 통일해야 합니다.
- `Farm Doctor Page.html`: Tailwind CDN, Font Awesome CDN, Google Fonts를 외부에서 불러오는 별도 HTML입니다. `fetch`/API 호출은 없고 업로드·YOLO·PDF·신고가 모의 처리입니다. 운영 프런트로 사용하려면 React에 통합하거나 별도의 실제 API 연동을 구현해야 합니다.

## 5. 백엔드와 API 구조

- 기술: Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2, psycopg(PostgreSQL 드라이버), boto3(S3), python-multipart(파일 업로드).
- 진입점: `backend/app/main.py`; 컨테이너는 `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`로 실행합니다.
- 저장소 코드: `backend/app/storage.py`가 S3 또는 S3 호환 서비스로 버킷 생성 확인, 업로드, 목록, 다운로드를 수행합니다.

| 메서드 | 경로 | 구현 상태 | 설명 |
|---|---|---|---|
| GET | `/health/live` | 구현 | DB 없이 서버 프로세스 생존 여부 반환 |
| GET | `/health/ready` | 구현 | PostgreSQL에 `SELECT 1`을 실행; 실패 시 503 반환 |
| POST | `/api/images` | 구현 | `image/*` Content-Type만 허용해 S3에 업로드하고 키 반환 |
| GET | `/api/images` | 구현 | 버킷의 객체 목록 반환 |
| GET | `/api/images/{object_key}` | 구현 | 저장된 파일을 스트리밍 다운로드 |

이미지 업로드 API는 파일의 **Content-Type 헤더**만 확인합니다. 실제 이미지 바이트 검증, 파일 크기 제한, 확장자/악성 파일 정책, 사용자 소유권, DB 메타데이터 기록은 코드에 없습니다. `POST /api/v1/uploads/presign`, 분석 작업, 모델 조회, 리포트 API 등은 PRD에는 있으나 서버 코드에는 없습니다.

## 6. 데이터베이스와 MySQL 여부

- 현재 선택된 DB는 **PostgreSQL 16**입니다. `docker-compose.yml`의 `postgres:16-alpine`, `DATABASE_URL` 기본 형식, `psycopg` 의존성이 근거입니다.
- MySQL 드라이버, MySQL 컨테이너, MySQL 연결 문자열은 확인되지 않았습니다. 따라서 **MySQL은 적용되어 있지 않습니다.**
- SQLAlchemy 엔진은 만들고 readiness에서 연결만 검사합니다. ORM 모델, 테이블 생성, Alembic 마이그레이션, CRUD(생성·조회·수정·삭제) 코드는 확인되지 않았습니다. 즉 PostgreSQL은 실행 환경에 포함되지만, 현재 업무 데이터는 DB에 저장되지 않습니다.
- 로컬 이미지 본문은 PostgreSQL이 아니라 SeaweedFS(S3 호환 서비스)에 저장됩니다.

## 7. YOLO 모델과 데이터셋

- 모델 파일 조사: `*.pt`, `*.pth`, `*.onnx`, `*.engine`, `*.ckpt`, `*.torchscript` 파일은 발견되지 않았습니다. `inference_api/models/`도 파일 없이 비어 있습니다.
- 실제 추론 연동: `backend/requirements.txt`에 `ultralytics`, `torch`가 없고, 백엔드 코드에 모델 로드/추론 호출도 없습니다. **실제 YOLO 추론은 연동되지 않았습니다.**
- 정적 HTML의 `best.pt (Active)` 문구와 `YOLOv8 모델 분석 완료` 알림은 실제 모델 상태가 아니라 하드코딩된 데모 표현입니다.
- 데이터 준비: 변환기는 Ultralytics용 YOLO Classification 및 Detection ZIP을 만들 수 있습니다. 노트북/변환기 예시는 `yolo11n-cls.pt`, `yolo11n.pt`로 학습하는 예시를 포함하지만, 이는 학습 실행 코드가 아니라 주석/문서 예시이며 가중치 파일은 저장소에 없습니다.
- 검증 보고서 기준: 1,200개 서브셋은 분류 학습에 `READY`, 탐지는 주목 객체 위치 bbox라는 조건부 `CONDITIONAL`, 병변(lesion) 위치 탐지는 `NOT_READY`입니다. 따라서 탐지 결과를 병변 위치라고 설명하면 안 됩니다.

## 8. Docker와 컨테이너 구성

`docker-compose.yml`에는 다음 4개 서비스가 있습니다.

| 서비스 | 이미지/빌드 | 역할 | 영속 데이터 |
|---|---|---|---|
| `db` | `postgres:16-alpine` | PostgreSQL DB | `postgres_data` 볼륨 |
| `minio` | `chrislusf/seaweedfs:3.80` | 이름은 minio이나 실제로는 SeaweedFS S3 호환 서버 | `seaweedfs_data` 볼륨 |
| `backend` | `backend/Dockerfile` | FastAPI API | 소스 bind mount(개발용) |
| `frontend` | `frontend/Dockerfile` | Vite 개발 서버 | 소스 bind mount, `frontend_node_modules` |

모든 컨테이너는 로컬 개발 편의 중심입니다.

- backend Dockerfile은 `--reload`를 사용합니다. 운영용에는 부적합합니다.
- frontend Dockerfile은 `npm run dev`로 Vite 개발 서버를 실행합니다. 운영용 정적 빌드/S3+CloudFront 또는 Nginx 구성이 아닙니다.
- `minio_data` 볼륨은 선언되어 있으나 어떤 서비스도 사용하지 않습니다.
- 운영에서 SeaweedFS를 쓸지 AWS S3로 바꿀지는 결정이 필요합니다. README는 AWS에서 S3 endpoint를 비우고 IAM 권한을 쓰라고 설명하지만, 실제 AWS 배포 파일은 없습니다.

## 9. 기능별 구현 상태

| 흐름 단계 | 상태 | 코드 근거 및 빈 부분 |
|---|---|---|
| 이미지 선택/미리보기 | 미구현(React) / 모의(HTML) | React 앱에는 없음. 정적 HTML은 브라우저 미리보기만 처리 |
| 서버 업로드 | 구현 | `POST /api/images` → S3 호환 저장소 |
| 업로드 메타데이터 DB 저장 | 미구현 | DB 테이블/INSERT 코드 없음 |
| 이미지 목록/다운로드 | 구현 | S3 객체 목록 및 스트리밍 다운로드 API |
| YOLO 모델 선택·로딩 | 미구현 | 모델 파일 및 관련 Python 의존성 없음 |
| YOLO 추론 작업 | 미구현 | worker/큐/분석 API 없음 |
| 추론 결과 DB 저장 | 미구현 | analysis/result 테이블과 코드 없음 |
| 결과 화면 표시 | 미구현(React) / 모의(HTML) | 정적 HTML의 표시는 샘플 배열 기반 |
| PDF 리포트 생성/다운로드 | 미구현 | HTML은 alert만 실행; 서버 PDF 라이브러리/API 없음 |
| 1399 신고 전송 | 미구현 | HTML은 alert만 실행; 외부 연동 코드 없음 |
| 데이터셋 검증/YOLO 형식 변환 | 구현 | `scripts/dataset_converter`와 검증 보고서 존재 |

## 10. AWS 배포에 필요한 것과 배포 원본에서 제외할 것

### 필요한 파일/구성 요소

- `backend/`, `frontend/`, 각 Dockerfile, 의존성 잠금 파일(`package-lock.json`) 및 `.dockerignore`.
- 환경 변수의 **이름**을 제공하는 `.env.example` (실제 `.env`는 배포물/저장소에 포함 금지).
- AWS S3 버킷, PostgreSQL용 Amazon RDS, 컨테이너 이미지를 둘 ECR, API 실행용 ECS/Fargate 또는 동등 실행 환경, HTTPS용 ALB/ACM, 로그/모니터링(IAM·CloudWatch).
- 아직 없는 배포 정의: ECS task definition, ECR push 스크립트, IAM 역할 정책, 네트워크(VPC/subnet/security group), Terraform/CDK/CloudFormation, CI/CD 설정. 모두 **새로 작성 필요**입니다.

### Docker/AWS 배포 원본에서 제외할 것

- `.venv/`, `.venv-1/`, `backend/.venv/`, `frontend/node_modules/`, `frontend/dist/`, `.pytest_cache/`, `.tmp_pytest/` — 개발 컴퓨터의 산출물/캐시.
- `data/`, `datasets/`의 대형 원본·학습 ZIP — 서비스 실행 이미지에 불필요합니다. 학습용이라면 별도 S3 버킷/데이터 관리 경로를 사용해야 합니다.
- `.git/` — 소스 이력이며 이미지에 불필요합니다.
- `Farm Doctor Page.html` — 현재 React 앱과 분리된 데모이므로 운영 화면으로 채택하지 않으면 제외 대상입니다.
- `notebooks/`, `reports/`, `prd/`, 발표 문서·CSV — 런타임에는 불필요하나, 문서/학습 관리용 별도 저장소에는 보관 가치가 있습니다.

삭제 권고가 아닙니다. 이 절의 ‘제외’는 **AWS 실행 이미지 또는 배포 패키지에 넣지 말라**는 뜻입니다.

## 11. 현재 가능한 기능, 미완성 기능, 오류 가능성

### 현재 가능한 기능

- Docker 환경에서 PostgreSQL과 SeaweedFS를 함께 기동할 구성.
- FastAPI 서버의 liveness/readiness 점검.
- S3 호환 스토리지로 이미지 업로드·목록·다운로드 API.
- Vite 개발 서버에서 API 생존 상태를 보여주는 React 화면.
- 원본 데이터 검증, 클래스 매핑, YOLO 형식 데이터셋 변환 도구.

### 미완성 기능

- 실제 사용자용 업로드 화면부터 AI 분석·결과·이력·PDF까지의 전체 서비스 흐름.
- 실제 YOLO 학습 산출물(가중치), 추론 서버/worker, GPU 실행 설계.
- DB 스키마/마이그레이션/업무 데이터 저장.
- 인증·권한·관리 기능.
- AWS 인프라 자동화, 운영용 Docker 이미지, HTTPS/도메인, CI/CD.

### 배포 또는 실행 시 오류 가능성이 높은 지점

1. Compose는 S3 접근용 환경 변수가 없으면 기동을 중단하도록 되어 있습니다. 실제 `.env` 값이 유효한지는 이 분석에서 확인하지 않았으므로 **검증 필요**입니다.
2. Vite 프록시가 `/api`를 제거하지만 이미지 API는 `/api/images`를 요구합니다. React에서 이미지 API를 붙일 때 404가 날 가능성이 높습니다.
3. `S3_CREATE_BUCKET=true`일 때 `create_bucket` 호출에는 리전별 위치 제약이 있을 수 있습니다. 로컬 SeaweedFS와 실제 AWS S3 각각에서 검증 필요입니다.
4. 업로드에 크기 제한·이미지 내용 검증·인증이 없어, 공개 배포 시 저장소 남용과 보안 문제가 생길 수 있습니다.
5. CORS 기본값은 로컬 주소 하나이며, 운영 도메인은 환경 변수로 정확히 설정해야 합니다.
6. Docker의 소스 bind mount와 `--reload`/Vite 개발 서버는 운영 컨테이너에 맞지 않습니다.
7. 모델 파일·추론 코드가 없으므로 ‘AI 분석’ 버튼을 실제 기능으로 배포할 수 없습니다.
8. 현재 Git 추적 파일 수가 0이므로, 배포 전 소스를 안전한 원격 저장소에 커밋·백업했는지 검증해야 합니다.

## 12. AWS 배포 전 반드시 해결할 문제와 권장 순서

1. **소스 기준선 확보**: Git 추적/커밋 상태를 정리하고, `.env`와 대형 데이터/가중치가 커밋되지 않도록 확인합니다. 현재 4GB 이상 Git 객체의 원인도 별도 점검합니다.
2. **서비스 범위 확정**: 정적 HTML 데모를 버릴지 React로 재구현할지 결정하고, 실제 사용자 흐름(업로드 → 분석 → 결과 → 리포트)을 API 명세로 확정합니다.
3. **DB 구현**: PostgreSQL 테이블(이미지, 모델 버전, 분석 작업, 탐지 결과, 리포트)을 설계하고 SQLAlchemy 모델·Alembic 마이그레이션·저장 로직을 추가합니다.
4. **파일 업로드 보강**: presigned URL 또는 안전한 서버 업로드, 파일 크기/실제 이미지 검증, 사용자별 접근 제어, S3 수명 주기를 구현합니다. 프록시/API 경로도 하나로 통일합니다.
5. **AI 검증과 연동**: 데이터셋 의미를 재확인하고 모델을 학습·평가합니다. 확정된 가중치, 클래스 맵, 임계값, 라이선스를 버전 관리한 뒤 worker에서 실제 추론하도록 연결합니다. 병변 bbox 성능을 주장하려면 병변 라벨 데이터가 필요합니다.
6. **결과와 리포트 구현**: 비동기 분석 작업 상태, 결과 조회 UI, PDF 생성/다운로드를 실제 데이터 기반으로 구현합니다. 신고 외부 연동은 대상 기관의 공식 API·권한을 확인한 뒤 별도 구현합니다.
7. **테스트와 운영 보안**: 단위·통합·E2E 테스트, 업로드 보안 테스트, 환경별 CORS, 비밀값은 AWS Secrets Manager/SSM과 IAM 역할로 관리합니다.
8. **운영 배포물 제작**: backend는 reload 없는 production 이미지, frontend는 빌드 결과 정적 호스팅(S3+CloudFront) 또는 웹 서버 이미지로 분리합니다. ECR/ECS/RDS/S3/ALB/ACM/VPC/IAM을 IaC로 정의합니다.
9. **스테이징 검증 후 운영 전환**: 별도 AWS 스테이징에서 업로드→S3→DB→추론→결과→PDF 전 흐름, 장애 응답, 비용·로그·백업·복구를 검증한 뒤 운영에 배포합니다.

## 13. 분석 한계(검증 필요)

- `.pytest_cache`와 `data/processed`의 일부 하위 폴더는 권한 제한으로 내부 목록을 열람하지 못했습니다. 그러나 상위 ZIP 파일과 보고서는 확인했습니다.
- 컨테이너 기동, API 호출, 빌드, 테스트는 프로젝트 파일을 생성하거나 캐시를 바꿀 수 있으므로 요청 조건에 따라 실행하지 않았습니다. 따라서 ‘코드상 구현됨’은 확인했지만 ‘이 컴퓨터에서 지금 실제 기동됨’은 **검증 필요**입니다.
- 실제 `.env`, AWS 계정, S3 버킷/RDS/ECS 리소스, 외부 신고 API의 존재·권한은 조사하지 않았습니다. 모두 **검증 필요**입니다.
