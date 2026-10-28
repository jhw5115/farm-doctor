# Function_PRD — Farm Doctor 실제 기능 구현

## 1. 화면 구성 (원본 HTML 기준)
- **메인:** 총 검사 수, 정상 판별 수, 과수화상병 의심 수, 분석 실패 수를 실제 DB 통계로 표시한다. 결과가 없으면 모두 0. 사과 이미지 여러 장 선택/드래그앤드롭, 미리보기, 삭제, 분석 시작, 파일별 진행·오류 표시를 제공한다.
- **결과 갤러리:** 전체/정상 사과/과수화상병 의심/판별 실패 필터, 이미지 썸네일, 검사 시각, 클래스, 신뢰도, 상세 모달, 기간 검색 및 페이지네이션. Bounding Box는 실제 Detection 결과가 있을 때만 후속 UI에 표시한다.
- **보고서:** 선택한 검사 묶음 또는 기간의 실제 결과를 서버에서 PDF로 생성·다운로드한다. 파일명, 판별 결과, 신뢰도, 검사 시각, 모델 버전, 'AI 참고용·확진 아님' 문구를 포함한다. 실패 시 다운로드 성공 메시지를 띄우지 않는다.
- **안내 도우미:** 사과 과수화상병의 일반 증상·예방·의심 시 연락 안내를 제공한다. 실제 LLM 연동이 없다면 '안내형 FAQ'로 명시하고 가짜 AI 응답을 제거한다. 신고 버튼은 관할 농업기술센터 연락 안내만 표시하며 외부 신고 전송을 가장하지 않는다.

## 2. 검사 처리 흐름
1. 사용자가 사과나무의 열매·잎·줄기·가지 사진을 1~10장 업로드한다. 파일당 최대 크기는 환경설정(초깃값 10MB)으로 제한한다.
2. 프런트엔드는 업로드 목록을 검증하고 `POST /api/v1/inspections`로 multipart 요청한다.
3. FastAPI가 파일을 검증하고 저장소(S3 또는 로컬)에 업로드하며 MySQL에 검사 묶음/이미지 기록을 생성한다.
4. 로드된 YOLO Detection `best.pt`로 이미지별 추론을 수행하고, 최고 신뢰도 객체의 `apple_healthy` 또는 `apple_fire_blight`, 신뢰도, 실제 Bounding Box 목록을 저장한다. 클래스 매핑은 `model.names`로 확인하며 클래스 ID 순서는 하드코딩하지 않는다.
5. 프런트엔드는 결과를 표시하고 갤러리·통계를 갱신한다. 일부 파일 실패 시 해당 파일만 실패로 기록한다.
6. 대용량 처리·응답 지연이 발생하면 작업 큐/비동기 처리로 확장하되, MVP에서는 제한된 이미지 수의 동기 추론으로 시작한다.

## 3. API 최소 명세
| Method | Path | 기능 |
|---|---|---|
| GET | `/api/v1/health` | 서버 및 모델 준비 상태(민감정보 제외) |
| POST | `/api/v1/inspections` | 다중 이미지 업로드 및 검사 실행 |
| GET | `/api/v1/inspections` | 검사 이력 목록·필터·페이지네이션 |
| GET | `/api/v1/inspections/{id}` | 검사 묶음과 이미지별 결과 |
| GET | `/api/v1/statistics` | 실제 DB 기반 정상/의심/실패 통계 |
| GET | `/api/v1/reports/{id}.pdf` | 검사 결과 PDF 생성 |

검사 결과 예시(실제 추론 값으로 치환):
```json
{
  "inspection_id": 101,
  "status": "completed",
  "results": [
    {
      "image_id": 501,
      "class_code": "apple_fire_blight",
      "class_name_ko": "사과 과수화상병 의심",
      "confidence": 0.94,
      "model_version": "apple_binary_v1",
      "status": "completed"
    }
  ]
}
```

## 4. DB 및 저장 규칙
- `inspection_batches`: ID, 생성일, 전체 건수, 완료/실패 수, 상태.
- `inspection_images`: ID, batch ID, 원본 파일명, MIME, 파일 크기, S3 객체 키, 처리 상태, 오류 메시지.
- `predictions`: ID, image ID, 클래스 코드, 신뢰도, 모델 버전, 검출 객체 수, 실제 Bounding Box JSON, 추론 시각.
- `model_versions`: 버전명, 파일 경로/식별자, 클래스 정보, 활성 여부, 등록 시각.
- FK, 인덱스(검사일/상태/클래스), 삭제 시 파일 정리 정책, 마이그레이션을 구현한다. 이미지 접근은 공개 S3 URL이 아닌 인증된 API 또는 짧은 만료의 presigned URL을 사용한다.

## 5. 구현 순서
- Phase 1: 기존 HTML UI를 React로 이식, 배 관련 흔적 제거, 예시 데이터와 실제 데이터 구분.
- Phase 2: FastAPI·MySQL·Alembic·Docker Compose 구성 및 연결 검증.
- Phase 3: 이미지 업로드/저장/검사 이력 API와 프런트엔드 연동.
- Phase 4: **재학습된 2클래스 YOLO Detection** `best.pt` 연동, 클래스 매핑·모델 유형 검증, 이미지별 Detection 결과 저장.
- Phase 5: 통계/갤러리/상세 모달/PDF 보고서/안내 기능 완성.
- Phase 6: 테스트·보안 점검, AWS RDS/S3/ECR/ECS/CloudFront 배포 구성 및 운영 문서 작성.

## 6. 인수 테스트
- 사과 이미지 1~10장을 업로드하면 각 이미지에 결과 또는 명확한 오류가 표시된다.
- 배 클래스·배 필터·배 통계가 UI/API/모델 매핑에 존재하지 않는다.
- 정상/의심 분류 결과가 DB에 저장되고 새로고침 후에도 이력과 통계가 유지된다.
- PDF에 실제 검사 기록이 들어가며, 실패/미연동 기능은 성공으로 표시되지 않는다.
- 모델이 없거나 9클래스 모델이면 서버가 이를 감지하고 추론 준비 안 됨을 알린다.
- 로컬 Docker 실행과 AWS 배포 준비 문서가 제공된다.
