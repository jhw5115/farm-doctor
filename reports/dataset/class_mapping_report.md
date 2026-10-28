# 클래스 매핑 검증 보고서

- 설정 파일: `C:\Users\mbc\aws\config\dataset_mapping.yaml`
- 로컬 JSON의 `crop+disease` 조합을 기준으로 사용자가 승인한 매핑입니다. `class_id`는 9개 목표 클래스에 대해 0~8로 고유하며, JSON의 원본 disease 숫자만으로는 작물 간 코드를 구별하지 않습니다.
- 사용자가 제공한 기존 공식표 전사본은 `config/official_disease_codebook.csv`에 보존했습니다. 이 표는 사과 disease 코드가 로컬 JSON과 다르므로 변환 매핑에는 적용하지 않았습니다.
- 설정 승인 상태: `True`
- 승인 검토자: `user`
- 로컬 매핑 검증 결과: 오류 없음
- 로컬 관측 조합과 9개 설정 조합 일치: `True`.

| YOLO ID | 목표 클래스 | 로컬 (crop, disease) | 로컬 관측 수 | 상태 |
|---:|---|---|---:|---|
| 0 | pear_healthy | (1, 0) | 100 | locally_observed_mapped |
| 1 | pear_scab | (1, 1) | 250 | locally_observed_mapped |
| 2 | pear_fire_blight | (1, 2) | 250 | locally_observed_mapped |
| 3 | apple_healthy | (2, 0) | 100 | locally_observed_mapped |
| 4 | apple_brown_spot | (2, 3) | 100 | locally_observed_mapped |
| 5 | apple_fire_blight | (2, 4) | 100 | locally_observed_mapped |
| 6 | apple_valsa_canker | (2, 5) | 100 | locally_observed_mapped |
| 7 | apple_alternaria_leaf_spot | (2, 6) | 100 | locally_observed_mapped |
| 8 | apple_anthracnose | (2, 7) | 100 | locally_observed_mapped |

## 실제 관측 crop-disease 조합

| 조합 | 개수 |
|---|---:|
| (1, 0) | 100 |
| (1, 1) | 250 |
| (1, 2) | 250 |
| (2, 0) | 100 |
| (2, 3) | 100 |
| (2, 4) | 100 |
| (2, 5) | 100 |
| (2, 6) | 100 |
| (2, 7) | 100 |

- 설정에 없는 로컬 조합: 없음
- 로컬에 관측되지 않은 설정 조합: 없음

질병명은 사용자가 제공한 클래스 목록 순서에 따라 로컬 코드에 대응했습니다. 이는 AI Hub 원본 공식 코드북과의 일치가 검증되었다는 뜻은 아닙니다.
