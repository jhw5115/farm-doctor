# 데이터셋 구조 및 YOLO 적용 사전 분석

## 범위 및 안전 경계

- `data/images`와 `data/labels`를 재귀 조사했습니다. 원본 이미지와 JSON은 읽기만 했으며 수정·삭제하지 않았습니다.
- 질병 코드북은 프로젝트 파일에서 확인되지 않았습니다. 폴더와 코드 빈도는 관측 사실로 기록했지만, 세부 질병명으로의 매핑은 확정하지 않았습니다.
- `class_mapping.csv`의 모든 행은 `training_label_approved=no`입니다. 검증 전 학습용 라벨을 생성하거나 YOLO 형식으로 변환하지 않습니다.

## 데이터 요약

- 이미지: 2000개; JSON: 2000개
- 파일명 기준 매칭: 2000개; unmatched image: 0개; unmatched label: 0개; ambiguous label: 0개
- 실제 이미지 크기와 JSON 선언 크기가 일치: 2000/2000개
- 좌표가 문법·범위 검사에서 유효한 JSON: 1998/2000개
- 실제 이미지 범위를 벗어난 개별 points: 2개
- 이미지/JSON 폴더 대응(배_0.정상→배_정상 등): 2000/2000개 일치
- 중복 SHA-256 그룹: 86개 (172개 파일 포함)

### 폴더별 코드 빈도

- `배_0.정상` (500 JSON)
  - `crop`: 1=500
  - `disease`: 0=500
  - `area`: 1=48, 3=100, 4=288, 5=64
  - `grow`: 25=386, 26=114
  - `risk`: 0=500
- `배_1.질병` (500 JSON)
  - `crop`: 1=500
  - `disease`: 1=250, 2=250
  - `area`: 1=68, 10=6, 11=7, 3=310, 4=3, 5=5, 8=3, 9=98
  - `grow`: 22=134, 23=366
  - `risk`: 1=229, 2=41, 3=230
- `사과_0.정상` (500 JSON)
  - `crop`: 2=500
  - `disease`: 0=500
  - `area`: 1=246, 3=134, 4=120
  - `grow`: 25=500
  - `risk`: 0=500
- `사과_1.질병` (500 JSON)
  - `crop`: 2=500
  - `disease`: 3=100, 4=100, 5=100, 6=100, 7=100
  - `area`: 1=110, 10=1, 2=4, 3=265, 4=40, 5=63, 8=7, 9=10
  - `grow`: 21=100, 22=254, 23=146
  - `risk`: 1=19, 2=396, 3=85

전체 필드·코드별 건수는 JSON 라벨 폴더명과 매칭 이미지 폴더명을 나란히 기록한 `dataset_statistics.csv`에 있습니다.

## 목표 9개 클래스와 원본 코드 매핑

`class_mapping.csv`는 목표 클래스별 후보 원본 폴더 및 그 폴더에서 관측된 crop/disease/risk 코드를 표시합니다. disease 코드는 배에서 1·2, 사과에서 3–7로 구분되어 관측되지만, 이를 목표 질병명에 대응시키는 원본 코드북은 없습니다. 따라서 숫자 코드들은 후보 신호일 뿐이고 특정 병명에 연결하지 않았습니다. 정상/질병 상위 폴더는 확인되지만, 질병 코드와 목표 병명 간의 의미 대응은 검증되지 않았습니다.

| ID | 목표 클래스 | 현 단계 매핑 |
|---:|---|---|
| 0 | `pear_healthy` | unverified_folder_candidate_only |
| 1 | `pear_scab` | unresolved_no_subtype_codebook |
| 2 | `pear_fire_blight` | unresolved_no_subtype_codebook |
| 3 | `apple_healthy` | unverified_folder_candidate_only |
| 4 | `apple_brown_spot` | unresolved_no_subtype_codebook |
| 5 | `apple_fire_blight` | unresolved_no_subtype_codebook |
| 6 | `apple_valsa_canker` | unresolved_no_subtype_codebook |
| 7 | `apple_alternaria_leaf_spot` | unresolved_no_subtype_codebook |
| 8 | `apple_anthracnose` | unresolved_no_subtype_codebook |

배/사과의 crop 코드 의미도 원본 코드북으로 대조해야 합니다. 코드북과 질병별 검수 라벨이 확보되기 전에는 어떤 세부 병해 클래스도 학습 대상으로 승인할 수 없습니다.

## 이미지-JSON 매칭 및 좌표 검증

JSON `description.image`의 basename을 이미지 basename과 정확히 비교했습니다. 이미지 헤더에서 JPEG/PNG 실제 가로·세로를 읽어 JSON의 `description.width/height` 및 각 points의 `xtl,ytl,xbr,ybr`를 검사했습니다. 자세한 파일별 결과와 실패 사유는 `annotation_validation.csv`, 미매칭·중복 참조는 `unmatched_files.csv`에 있습니다.

좌표가 이미지 안에 있고 순서가 올바르다는 검사는 주석의 의미를 입증하지 않습니다. 정상 이미지에도 points가 존재하므로 points를 병변 박스라 가정하지 않았습니다. Detection 변환은 주석 대상이 병변인지, 과실/잎 등 촬영 대상인지, 점 좌표 의미가 무엇인지 데이터 제공자 확인 후에만 가능합니다.

## YOLO Classification 데이터셋 생성 가능성

- JSON에는 배 질병 코드 1·2(각 250건), 사과 질병 코드 3–7(각 100건)이 관측됩니다. 숫자값이 나뉘어 있어 세부 클래스 후보가 될 수 있지만, 코드-병명 코드북이 없으므로 목표 9개 클래스의 정답 라벨로 확정할 수 없습니다.
- 원본 코드북과 질병별 검수 라벨을 확보해 각 숫자 코드가 목표 병명과 맞는지 확인하고, 작물 코드 정의와 클래스별 표본 수/오류 사례를 재검토해야 합니다. 불명확 사례는 임의 배정 대신 제외/보류해야 합니다.
- 허가된 분류 라벨을 얻은 후에만 `train/<class>`, `val/<class>`, `test/<class>` 구조로 내보낼 수 있습니다. 이번 작업에서는 이 디렉터리나 학습 라벨을 만들지 않았습니다.
- 정확한 중복 이미지를 제거하거나 동일 그룹에 묶고, 같은 개체와 연속 촬영 시리즈가 서로 다른 split에 들어가지 않도록 해야 합니다.

## YOLO Detection 적용 가능성

- 원본 points는 박스 형태이고 좌표 범위 검증은 가능하지만, `annotation_semantics`가 확인되지 않았습니다. 정상 이미지의 박스 존재는 병변 박스 해석과 양립하지 않으므로 자동 변환은 부적절합니다.
- 제공자/주석 지침에서 대상 객체, 경계 규칙, 클래스 의미, 정상 이미지의 박스 의미를 확인하고 샘플을 육안 검수해야 합니다.
- 의미 검증 후 image size와 좌표를 사용해 중심점/너비/높이 정규화 및 클래스 ID 변환을 설계할 수 있습니다. 현재는 YOLO Detection 라벨을 생성하지 않았습니다.

## 개체·연속 촬영 누수 방지

- 파일명의 마지막 숫자 프레임(배의 `_Sxx_1` 접미부 포함)을 제외한 후보 그룹이 482개 발견됐고, 그룹당 평균 4.15개 이미지입니다. 이 규칙은 파일명 기반 후보일 뿐, 동일 개체를 완전히 식별한다는 보장은 없습니다.
- 후보 그룹 중 여러 라벨 폴더를 포함하는 그룹은 0개입니다. 이 파일명 규칙으로 교차 폴더 그룹은 나오지 않았지만, 동일 개체가 다른 파일명/촬영 세션으로 기록됐는지는 별도 확인이 필요합니다.
- 최종 split 전 촬영 세션/개체 ID를 메타데이터에서 검증하고, 검증된 group ID 단위로 train/val/test에 할당해야 합니다. 시간·연속 촬영이 같거나 동일 개체로 판단되는 사진은 전부 한 split에 둡니다. 가능한 경우 별도 촬영일/과원 기준 외부 테스트도 고려합니다.
- 이번 분석은 split 디렉터리나 학습 데이터를 만들지 않았습니다.

## 산출물

- `class_mapping.csv`: 목표 9개 클래스와 미확정 원본 코드 매핑
- `dataset_statistics.csv`: crop/disease/area/grow/risk 코드별 폴더 빈도
- `unmatched_files.csv`: 미매칭, 모호한 매칭, 중복 참조 및 읽기 오류
- `annotation_validation.csv`: 파일별 매칭·이미지 크기·좌표 결과
- `scripts/analyze_dataset.py`: 원본 데이터를 읽기만 하며 위 보고서와 CSV를 재생성하는 분석 스크립트 (`python scripts/analyze_dataset.py`)
