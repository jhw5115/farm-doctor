$ErrorActionPreference = 'Stop'
$outputPath = Join-Path (Get-Location) 'Farm_Doctor_개발과정_AWS_전환_가이드.pptx'
$ppt = New-Object -ComObject PowerPoint.Application
$ppt.Visible = 1
$presentation = $ppt.Presentations.Add()

function Add-Text($slide, [string]$text, [double]$left, [double]$top, [double]$width, [double]$height, [int]$size, [int]$color, [bool]$bold=$false) {
  $shape = $slide.Shapes.AddTextbox(1, $left, $top, $width, $height)
  $range = $shape.TextFrame.TextRange
  $range.Text = $text
  $range.Font.NameFarEast = '맑은 고딕'
  $range.Font.Name = 'Aptos'
  $range.Font.Size = $size
  $range.Font.Color.RGB = $color
  $range.Font.Bold = [int]$bold
  $shape.TextFrame.WordWrap = -1
  return $shape
}
function Add-Card($slide, [string]$title, [string]$body, [double]$left, [double]$top, [double]$width, [double]$height, [int]$accent) {
  $card = $slide.Shapes.AddShape(5, $left, $top, $width, $height)
  $card.Fill.ForeColor.RGB = 16316661
  $card.Line.ForeColor.RGB = 15132390
  $bar = $slide.Shapes.AddShape(1, $left, $top, 7, $height)
  $bar.Fill.ForeColor.RGB = $accent
  $bar.Line.Visible = 0
  Add-Text $slide $title ($left+18) ($top+14) ($width-30) 26 17 4866907 $true | Out-Null
  Add-Text $slide $body ($left+18) ($top+48) ($width-30) ($height-58) 11 6710886 $false | Out-Null
}
function Add-Page([string]$title, [string]$subtitle, [string[]]$cards) {
  $slide = $presentation.Slides.Add($presentation.Slides.Count+1, 12)
  $slide.FollowMasterBackground = 0
  $slide.Background.Fill.ForeColor.RGB = 16382457
  Add-Text $slide $title 42 28 850 40 28 4866907 $true | Out-Null
  Add-Text $slide $subtitle 44 72 850 24 11 7895160 $false | Out-Null
  $count=$cards.Count; $columns=if($count -le 3){$count}else{2}; $cardWidth=if($columns -eq 1){830}elseif($columns -eq 2){400}else{260};
  for($i=0;$i -lt $count;$i++) { $col=$i%$columns; $row=[math]::Floor($i/$columns); $x=42+$col*($cardWidth+18); $y=118+$row*190; $parts=$cards[$i].Split('|',2); if($i%3 -eq 0){$accent=6456179}elseif($i%3 -eq 1){$accent=2919503}else{$accent=13395545}; Add-Card $slide $parts[0] $parts[1] $x $y $cardWidth 168 $accent }
  Add-Text $slide "Farm Doctor · 사과 과수화상병 AI 판별 웹서비스" 42 500 500 18 9 10066329 $false | Out-Null
}

$title=$presentation.Slides.Add(1,12); $title.FollowMasterBackground=0; $title.Background.Fill.ForeColor.RGB=16382457
$circle=$title.Shapes.AddShape(9,48,55,104,104); $circle.Fill.ForeColor.RGB=10737472; $circle.Line.Visible=0
Add-Text $title '🌱' 76 76 52 52 32 4866907 $false | Out-Null
Add-Text $title 'Farm Doctor 개발 과정과 AWS 전환 가이드' 48 190 800 55 31 4866907 $true | Out-Null
Add-Text $title '사과 과수화상병 AI 판별 웹서비스 · 현재 구현 현황, 운영 전환, Codex 협업 원칙' 50 254 780 28 15 7895160 $false | Out-Null
Add-Text $title '2026.10 · 개발 학습용 자료' 50 470 400 22 11 10066329 $false | Out-Null

Add-Page '1. 프로젝트 목표' '농가 사용자가 사진을 업로드해 AI 참고용 판별과 검사 이력을 확인하는 서비스' @(
  '대상 범위|사과 정상 / 사과 과수화상병 의심 2개 클래스만 사용합니다. AI 결과는 확진이 아닙니다.',
  '핵심 사용자 경험|사진 업로드 → YOLO 분석 → MySQL 기록 저장 → 갤러리·리포트 확인',
  '운영 원칙|실제 데이터만 표시하고, 모델·DB 미연동 시 임의 결과를 만들지 않습니다.'
)
Add-Page '2. 현재 아키텍처' '로컬 Docker Compose에서 프런트엔드·백엔드·MySQL을 통합 실행' @(
  'React + TypeScript|Farm Doctor UI, 업로드·갤러리·리포트·안내 페이지를 제공합니다.',
  'FastAPI + YOLO Detect|best.pt 모델을 불러와 객체 탐지·confidence·bounding box를 처리합니다.',
  'MySQL + Alembic|검사 배치, 이미지, 예측값, 리포트·챗봇 기반 데이터를 관리합니다.',
  '파일 저장 구조|로컬 볼륨을 기본으로 사용하며 AWS S3 전환 환경변수를 준비했습니다.'
)
Add-Page '3. Phase 1~5 개발 흐름' '기능을 단계별로 구축하고 실제 API와 DB 검증을 우선했습니다.' @(
  'Phase 1·2|React/FastAPI 실행, MySQL 연결, Alembic 테이블 생성과 저장·조회 검증',
  'Phase 3·4|다중 이미지 업로드, 파일 저장, YOLO Detect best.pt 실제 클래스·추론 검증',
  'Phase 5|통계, 갤러리, 탐지 상세, PDF 보고서, 오류·빈 상태 처리 개선'
)
Add-Page '4. 데이터와 AI 판별 흐름' '추론 결과와 원본 이미지는 분리해 저장하며, 모델 출력값을 그대로 사용합니다.' @(
  '입력 검증|JPG/JPEG/PNG/WEBP, 파일 크기·개수 제한, 다중 업로드 지원',
  '탐지 결과|클래스, confidence, 검출 수, 실제 bounding box 좌표를 predictions에 저장',
  '안전 문구|confidence는 확진 확률·심각도가 아니며 전문 기관 현장 확인이 필요'
)
Add-Page '5. 리포트·PDF 기능' '동일한 검색 조건을 화면 통계와 PDF에 적용합니다.' @(
  '조회 조건|기간, 결과, 요약/상세, 이미지 포함, 의심 사례 상세 출력',
  '화면 리포트|결과별 통계·비율, 기간별 추이, 의심 사례 썸네일, 빈 상태 안내',
  'PDF 출력|기본 요약·추이·상세 기록·선택 이미지·AI 한계 및 전문기관 안내'
)
Add-Page '6. 비용 없는 챗봇 기반' '외부 LLM은 AWS 운영 환경 안정화 이후 최종 연동합니다.' @(
  '현재 제공|서비스 사용법, confidence 의미, MySQL 검사 집계 안내를 FastAPI로 처리',
  '저장 구조|chat_sessions, chat_messages, knowledge_documents 테이블과 Alembic 마이그레이션 준비',
  '보류 항목|외부 LLM·RAG·API 키 사용은 AWS Secrets Manager 구성 이후 진행'
)
Add-Page '7. AWS 목표 아키텍처' '데이터와 컨테이너, 비밀 값을 분리해 운영 안정성을 확보합니다.' @(
  'ECR + ECS Fargate|프런트엔드·백엔드 이미지를 배포하고 롤링 업데이트',
  'RDS MySQL + S3|검사 데이터는 RDS, 이미지와 모델·문서는 S3 기반으로 운영',
  'CloudFront + ALB|정적 화면 배포와 API 트래픽 분리, HTTPS·도메인 확장 준비',
  'Secrets Manager|DB 비밀번호와 향후 LLM API 키를 코드·Git에서 분리'
)
Add-Page '8. Git 기반 수정·재배포 흐름' 'AWS 배포 후에도 기능 수정은 Git을 중심으로 반복합니다.' @(
  '1. 개발|로컬에서 수정·테스트·Docker Compose 검증 후 Git commit/push',
  '2. 빌드|GitHub Actions 또는 CodePipeline/CodeBuild가 이미지 생성 후 ECR 업로드',
  '3. 배포·롤백|ECS Task Definition을 새 이미지 태그로 교체하고, 문제 시 이전 태그로 롤백'
)
Add-Page '9. Codex 요청 시 주의사항' '작업 범위와 검증 기준을 명확히 하면 안전하고 빠르게 협업할 수 있습니다.' @(
  '명확한 범위|"리포트 UI만 수정", "DB 삭제 금지", "YOLO 추론 로직 변경 금지"처럼 범위를 명시',
  '사실 검증|"실제 테스트한 결과만 성공 처리", "API/DB 응답값을 함께 보고"를 요청',
  '민감정보 보호|API 키·DB 비밀번호·AWS Access Key를 채팅이나 코드에 직접 제공하지 않기',
  '변경 관리|작업 전 Git 상태 확인, 단계별 파일 목록·실행법·롤백 방법을 요청'
)
Add-Page '10. 다음 개발 체크리스트' 'AWS 이전에 로컬 품질을 고정하고, 이후 인프라와 외부 AI를 순차 적용합니다.' @(
  'AWS 전|환경변수 정리, Alembic 최신화, Docker 이미지 경량화, 회귀 테스트 정리',
  'AWS 구축|VPC·RDS·S3·ECR·ECS·ALB·CloudFront·CloudWatch·Secrets Manager 구성',
  '최종 연동|공식 문서 RAG, 외부 LLM, 인증·권한, 비용 제한·모니터링·백업 정책'
)

$presentation.SaveAs($outputPath)
$presentation.Close()
$ppt.Quit()
Write-Output $outputPath
