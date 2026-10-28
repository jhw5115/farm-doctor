# AWS 전환 전 점검

## 이미지 빌드

- 백엔드: `docker build -f backend/Dockerfile.prod -t farm-doctor-backend:local backend`
- 프런트엔드: `docker build -f frontend/Dockerfile.prod -t farm-doctor-frontend:local frontend`
- `best.pt`는 이미지에 포함하지 않고 S3 또는 EFS에서 ECS 태스크에 제공한다.

## 데이터베이스

- 배포 전 `alembic current`와 `alembic heads`가 같은 revision인지 확인한다.
- ECS 서비스 배포 전에 1회성 migration task 또는 CI 작업으로 `alembic upgrade head`를 실행한다.
- 운영 RDS에는 롤백 계획과 스냅샷을 준비한 뒤 마이그레이션한다.

## 회귀 테스트

```powershell
cd backend
python -m pytest tests -q
cd ../frontend
npm.cmd run build
```

통합 환경에서는 `/api/v1/health`, 검사 업로드·조회, 리포트 요약/PDF, 챗봇 상태 API를 확인한다.

## 환경변수

- `.env`는 Git에 넣지 않는다.
- ECS에서는 DB 비밀번호·향후 OpenAI 키를 Secrets Manager에서 주입한다.
- S3 접근은 액세스 키가 아니라 ECS Task Role을 사용한다.
