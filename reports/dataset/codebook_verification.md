# AI Hub 코드북 검증 보고서

- 검증일: 2026-10-16
- 대상: AI Hub `과수화상병 촬영 이미지` (데이터셋 ID `146`, 공개 버전 `1.0`, 2021-06-25)
- 출처: <https://www.aihub.or.kr/aihubdata/data/view.do?aihubDataSe=data&currMenu=115&dataSetSn=146&topMenu=100>
- 확인 근거: 사용자가 AI Hub 공식 페이지의 구축 수량 표를 직접 확인하여 9개 `(crop,disease)` 조합을 승인했습니다.
- 근거 표: 사용자 확인을 반영한 공식 코드 대응표. `config/official_disease_codebook.csv`에 출처 URL, ID, 버전, 공개일, 확인일 및 확인 상태를 행별 메타데이터로 기록했습니다.

## 판정

`OFFICIAL_CODEBOOK_VERIFIED: VERIFIED`

사용자가 확인한 AI Hub 공식 구축 수량 표와 현재 JSON/YOLO 매핑은 9개 모두 일치합니다. 이 상태는 기존의 로컬 매핑 CSV를 공식 코드북으로 오인한 상태와는 다릅니다. 변환기는 이제 `official_disease_codebook.csv`만 코드북으로 사용하며, `local_disease_mapping.csv`는 로컬 관측/승인 기록일 뿐 공식 출처로 사용할 수 없습니다.

| YOLO ID | (crop, disease) | 클래스 | 공식 명칭 | 제공 표 대조 |
|---:|---|---|---|---|
| 0 | (1, 0) | pear_healthy | 배 정상 | 일치 |
| 1 | (1, 1) | pear_scab | 배검은별무늬병 | 일치 |
| 2 | (1, 2) | pear_fire_blight | 배과수화상병 | 일치 |
| 3 | (2, 0) | apple_healthy | 사과 정상 | 일치 |
| 4 | (2, 3) | apple_brown_spot | 사과갈색무늬병 | 일치 |
| 5 | (2, 4) | apple_fire_blight | 사과과수화상병 | 일치 |
| 6 | (2, 5) | apple_valsa_canker | 사과부란병 | 일치 |
| 7 | (2, 6) | apple_alternaria_leaf_spot | 사과점무늬낙엽병 | 일치 |
| 8 | (2, 7) | apple_anthracnose | 사과탄저병 | 일치 |

## 변경 및 재현성

- 이전 코드북은 `config/official_disease_codebook.pre_aihub_2026-10-16.csv`로 백업했습니다.
- `config/dataset_mapping.yaml`의 클래스 ID 0~8 및 `(crop, disease)` 쌍은 변경하지 않았습니다.
- 검증 로직은 공식 코드북 역할 선언과 행별 출처 메타데이터를 요구합니다. 로컬 CSV를 `codebook_path`로 지정하거나 공식 역할/메타데이터가 누락되면 검증 오류가 됩니다.
- 사용자 확인을 재현 가능하게 하려면 해당 AI Hub 페이지의 구축 수량 표 캡처 또는 원본 다운로드 표를 실험 기록과 함께 보관하세요.
