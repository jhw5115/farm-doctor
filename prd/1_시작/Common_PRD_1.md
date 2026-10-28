# Common PRD — 과수화상병 AI 의심증상 탐지 및 대응지원 플랫폼

- 문서 버전: 1.0
- 목표: VS Code Codex를 사용해 로컬 개발부터 AWS 운영 배포까지 실행 가능한 웹서비스 구축
- 연계 문서: `Function_PRD.md`

## 1. 제품 목표 및 경계
사과·배 등 과수의 촬영 이미지를 업로드하면 YOLO 모델이 학습된 증상 클래스의 위치와 신뢰도를 추론하고, 사용자에게 **과수화상병 의심 증상 탐지 결과**와 공적 지침 기반 대응 안내를 제공한다. 이미지 기반 결과는 확진이나 법적 방제 명령을 대체하지 않는다. 병징이 다른 병해·생리장해와 유사할 수 있음을 표시한다.

### 성공 기준
- 사용자 가입/로그인 → 이미지 업로드 → 분석 요청 → 결과 조회 → 이력 재조회 흐름이 실제 API/DB/S3/모델로 동작한다.
- 샘플 이미지와 실제 가중치가 준비되면 mock 없이 추론 가능하다.
- AWS에서 HTTPS 서비스가 운영되고 GitHub Actions로 재현 가능한 배포가 가능하다.
- 개인정보/위치정보 접근 제어, 감사 로그, 운영 모니터링 및 백업이 구성된다.

### 범위 외
- 사진만으로 확진, 농약 처방전 발행, 자동 신고 대행, 모델이 검증되지 않은 상태의 정확도 보장.
- 병징 클래스, 병원균 존재 여부, 약제 및 법적 조치의 임의 생성.

## 2. 사용자 및 역할
- 비회원: 소개, 사용법, 공지, 로그인/가입.
- 일반 사용자(농가/현장 담당자): 사진 분석, 본인 이력 및 대응 안내.
- 전문가/검토자: 권한이 부여된 분석 건 검토, 판단 의견 및 검토 상태 기록.
- 관리자: 사용자/권한, 공지, 안내 콘텐츠, 모델 활성 버전, 시스템 상태, 감사 기록.
- 서버의 모든 API에 역할별 권한 검사 적용. 프런트 메뉴 숨김만으로 보안 구현 금지.

## 3. 기술 스택
- Frontend: React, TypeScript, Vite, React Router, TanStack Query, 접근성 있는 UI 컴포넌트.
- Backend: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic.
- AI: PyTorch + 실제 가중치와 호환되는 YOLO 구현체(예: Ultralytics). 라이선스 확인 후 확정.
- DB: PostgreSQL 16+; 개발은 Docker Compose, 운영은 Amazon RDS for PostgreSQL.
- 이미지/결과 객체: 로컬 개발용 S3 호환 저장소 또는 로컬 어댑터, 운영 Amazon S3.
- 비동기 작업: MVP는 DB 작업 큐 + 별도 worker(단일 worker 기준 원자적 선점); 운영 확장 시 SQS 기반 큐로 전환. API 요청에서 장시간 추론 금지.
- 배포: Docker, Amazon ECR, Amazon ECS Fargate (CPU 추론이 성능 기준 충족할 때); GPU가 필요하면 ECS on EC2 GPU 인스턴스 등 별도 설계 및 비용 승인.
- 네트워크: Route 53(선택), ACM 인증서, ALB HTTPS, VPC, 퍼블릭/프라이빗 서브넷, 보안 그룹.
- 비밀정보: AWS Secrets Manager 또는 SSM Parameter Store; 환경별 최소 권한 IAM.
- 로그/모니터링: CloudWatch, ALB 헬스체크, 구조화 로그, 에러 및 지연 알람.
- GitHub: main/develop/feature 브랜치, PR 리뷰, GitHub Actions CI/CD, OIDC를 통한 AWS 권한 위임(장기 액세스 키 금지).

## 4. 논리 아키텍처
Browser → HTTPS ALB → Frontend(정적 빌드 배포: S3+CloudFront 권장) / FastAPI(ECS) → PostgreSQL(RDS), S3, Queue → YOLO Worker(ECS) → DB 및 S3 결과 기록.

- 프런트는 API를 통해 업로드용 presigned URL을 받고 S3에 직접 업로드; 서버에서 MIME, 파일 시그니처, 크기, 해상도, 업로드 완료 검증.
- DB에는 객체 키와 메타데이터만 저장하고 원본 이미지 바이너리는 저장하지 않는다.
- S3 버킷은 비공개, 암호화, 만료형 URL 사용; 사용자별 접근 권한 확인.
- 분석 작업은 `queued → processing → completed/failed` 상태 전이를 갖고 재시도 횟수 및 실패 원인을 저장한다.
- 업로드, 작업 생성, 추론 및 결과 조회는 추적 가능한 request_id/job_id를 사용한다.

## 5. 데이터 모델 (최소 필수)
- users: id(UUID PK), email(unique), password_hash, display_name, role, status, created_at, updated_at.
- orchards: id, owner_id(FK), name, crop_type, approximate_region(nullable), created_at.
- images: id, owner_id, orchard_id(nullable), s3_key(unique), original_filename, mime_type, size_bytes, width, height, sha256, uploaded_at.
- model_versions: id, name, architecture, weights_uri, weights_sha256, class_map_json, confidence_threshold, iou_threshold, training_metadata_json, validation_metrics_json, status, activated_at.
- analysis_jobs: id, user_id, image_id, model_version_id, status, progress, error_code, retry_count, created_at, started_at, completed_at.
- detections: id, job_id, class_id, class_name, confidence, bbox_x1, bbox_y1, bbox_x2, bbox_y2 (픽셀 좌표), optional_mask_key.
- analysis_results: id, job_id(unique), annotated_image_key, summary_json, risk_label, disclaimer_version, created_at.
- guidance_articles: id, crop_type, title, body, official_source_name, official_source_url, source_checked_at, effective_from, effective_to, version, approved_by, published.
- expert_reviews: id, job_id, reviewer_id, review_status, note, created_at.
- audit_logs: id, actor_id, action, target_type, target_id, metadata_json, created_at.
- notification_events (선택): id, user_id, type, payload_json, read_at, created_at.

모든 외래키·고유 제약·인덱스·삭제 정책 정의. Alembic 마이그레이션 포함. 민감한 위치정보는 선택 입력으로 최소 수집.

## 6. API 공통 규약
- Prefix `/api/v1`, JSON, OpenAPI 자동 문서화(운영에서 접근 제한).
- 인증: 안전한 세션 또는 짧은 수명 access token + 회전형 refresh token(가능하면 HttpOnly/Secure/SameSite 쿠키). 비밀번호 Argon2id 해시.
- 표준 오류: `{ "error": { "code": "...", "message": "...", "request_id": "..." } }`.
- 페이지네이션, 입력 유효성, 파일 크기 제한(기본 15MB/장, 설정 가능), 허용 포맷 JPEG/PNG/WebP, 요청 rate limit.
- Swagger 예제, HTTP 상태 코드, 권한별 접근 테스트 포함.

## 7. AI 모델 통합 계약
- 학습된 YOLO 가중치는 제공되지 않은 것으로 간주한다. 기본 동작은 `MODEL_NOT_CONFIGURED`로 명확하게 안내하며 **실제 분석인 척하는 mock 결과를 사용자에게 표시하지 않는다**.
- 개발 전용 demo mode는 명시적 `DEMO` 배지와 분리된 테스트 데이터로만 허용한다.
- 가중치 경로, 클래스 맵, 입력 크기, conf/IoU 임계값, 전처리 및 후처리는 설정/버전으로 관리한다.
- YOLO 탐지 클래스는 실제 데이터셋 정의를 기준으로만 등록한다. 예: `suspected_fire_blight_symptom`은 샘플일 뿐 확정 클래스가 아니다.
- 클래스별 탐지 점수는 병 감염 확률 또는 임상적 확진 신뢰도로 표시하지 않는다.
- 음성 탐지 결과는 '과수화상병 없음'이 아니라 '모델이 탐지한 의심 영역 없음'으로 표기한다.
- 모델 검증: 데이터 분리(과원/촬영시점 기준 누수 방지), mAP50, mAP50-95, Precision, Recall, 클래스별 혼동행렬, 미탐/오탐, 실제 현장 이미지 성능, 처리 시간.
- 모델/데이터 라이선스, 개인정보 및 촬영 권리 확인.

## 8. 보안 및 운영
- TLS, CORS 허용 목록, CSRF 방어(쿠키 인증 시), SQL 인젝션 방어, 업로드 파일 검사, 접근 제어, XSS 방지.
- 이미지 EXIF/GPS 제거 또는 명시적 동의 후 최소 보존. 이미지 및 계정 삭제 요청 지원.
- 로그에 비밀번호, 토큰, 원본 이미지, 정밀 GPS 기록 금지.
- RDS 자동 백업, S3 버저닝/수명주기 정책, 복구 리허설, DB migration rollback 계획.
- 비밀키는 GitHub에 커밋하지 않는다. `.env.example`만 제공한다.
- 운영비 예산과 사용량 알림 설정; CPU/GPU 인프라 비용을 별도 산정.
- 농업 관련 공식 대응 지침은 담당 기관의 최신 공표자료를 확인하여 관리자 승인 후 게시한다. 지역/시기별 차이가 있을 수 있다.

## 9. GitHub 저장소 구조
```text
fireblight-ai/
  frontend/                 # React UI
  backend/app/              # FastAPI, 도메인, 서비스, 저장소
  backend/alembic/          # DB migrations
  worker/                   # YOLO inference worker
  tests/                    # unit/integration/e2e
  infra/terraform/          # AWS IaC (선택하되 운영 전 필수)
  .github/workflows/        # CI/CD
  docs/                     # PRD, API, 운영 및 모델 문서
  docker-compose.yml
  .env.example
  README.md
```

## 10. 단계별 개발 및 수락 기준
1. Foundation: 저장소, Docker Compose, PostgreSQL, FastAPI, React, 환경 변수, health endpoint, 기본 테스트.
2. Auth/RBAC: 가입/로그인/로그아웃, 역할별 API 접근 제한, 감사 로그.
3. Data: 과원 정보, S3 업로드, 파일 검증, 목록/상세/삭제.
4. AI: 모델 레지스트리, 실제 가중치 로딩, 비동기 추론, bounding box 렌더링, 오류 처리.
5. Guidance: 검토된 공식 안내, 결과 연계, 전문가 검토 및 이력.
6. Admin: 사용자/모델/콘텐츠 관리, 운영 지표.
7. QA: unit/integration/e2e, 권한 침투 시나리오, 성능, 접근성, 실제 모델 검증.
8. AWS: IaC, RDS/S3/ECS/ALB/CloudFront, CI/CD, 도메인/HTTPS, 로그/알람/백업, 운영 검증.

완료 정의(DoD): 모든 핵심 사용자 흐름이 mock 없이 작동(모델 제공 시), DB 영속화 확인, 자동 테스트 통과, AWS에서 재배포 가능, 운영 문서와 실제 실행 명령 제공. 모델 미제공 시 해당 기능을 완료로 표시하지 않는다.

## 11. Codex 개발 지침
- Common_PRD와 Function_PRD를 모두 읽고 충돌 시 보안/의학적 표현 제한을 우선한다.
- 단계마다 파일 생성/변경 목록, 실행 명령, 테스트 결과, 미완료 항목을 보고한다.
- 임의의 가짜 분석 결과, 가짜 정확도 수치, 허위 외부 연동을 구현하지 않는다.
- 각 단계 완료 시 실제 앱을 실행해 API/DB/UI 연동을 검증한다.
- AWS 자원 생성, 비용 발생, 운영 DB 변경 및 배포는 사용자 승인 후 실행한다.

## 12. 착수 전 결정 사항
- 대상 작물(사과/배), 클래스 정의, 데이터셋 보유 여부, YOLO 가중치 형식과 라이선스.
- 일반 사용자용 공개 서비스인지 기관 내부용인지, 전문가 검토 절차.
- 공식 방제 안내의 담당 기관/지역, 운영 예산, 동시 분석량, 데이터 보존 기간.
