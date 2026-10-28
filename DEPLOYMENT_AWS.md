# AWS 배포 준비 절차

이 저장소는 로컬에서는 MySQL과 로컬 파일 저장소를 사용하고, 운영에서는 RDS MySQL·S3·ECS Fargate로 전환합니다. 실제 AWS 리소스 생성은 포함하지 않습니다.

## 구성

- 정적 React 산출물: S3 비공개 버킷 + CloudFront(OAC). `VITE_API_BASE_URL`은 ALB의 HTTPS 주소로 빌드 시 설정합니다.
- API: `backend/Dockerfile`을 ECR에 push하고 ECS Fargate 서비스로 실행합니다. ALB `/api/*` 라우팅을 연결합니다.
- DB: RDS for MySQL 8.x, UTF8MB4. RDS는 비공개 서브넷에 두고 ECS 보안 그룹에서만 3306 접근을 허용합니다.
- 이미지: 전용 S3 버킷. ECS task role에 해당 버킷의 필요한 prefix에 대한 Get/Put 권한만 부여합니다. 공개 URL을 사용하지 않습니다.
- 모델: 검증된 2클래스 `best.pt`를 EFS, 사설 S3에서 시작 시 내려받는 방식, 또는 이미지에 포함하는 방식 중 운영 정책에 맞게 선택합니다. `MODEL_PATH`는 그 위치로 지정합니다.

## 운영 환경 변수

`DATABASE_URL`, `STORAGE_BACKEND=s3`, `S3_BUCKET`, `AWS_REGION`, `MODEL_PATH`, `MODEL_VERSION`, `CORS_ORIGINS`, `MAX_UPLOAD_SIZE_MB`, `MAX_UPLOAD_FILES`를 ECS task definition 또는 Secrets Manager/SSM에 등록합니다. DB 암호는 Secrets Manager로 주입하며 소스 및 이미지에 포함하지 않습니다.

## 배포 전 점검

1. `best.pt`의 `model.names`가 정확히 `apple_healthy`, `apple_fire_blight` 두 클래스인지 확인합니다.
2. ECS task에서 `alembic upgrade head`를 단일 배포 작업으로 실행합니다. 다중 task가 동시에 마이그레이션하지 않도록 CI 단계 또는 one-off task로 분리합니다.
3. HTTPS(ACM), ALB health check(`/api/v1/health`), CloudWatch 로그와 알람, RDS 백업/삭제 보호, S3 암호화·수명 주기를 설정합니다.
4. CloudFront만 프런트 버킷을 읽을 수 있게 하고, CORS에는 실제 CloudFront 도메인만 지정합니다.
