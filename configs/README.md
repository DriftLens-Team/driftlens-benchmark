# 실행 설정 예시
run.example.json은 향후 실행 관리자용 합성 예시이며 현재 CLI 입력이 아니다. 모든 상대 경로는 benchmark 저장소 루트 기준이다. 실제 변경 시점·profile 일정은 탐지기 금지 정보다. 모델·DB 상세는 agent configs/runtime.example.json에 분리한다. detector_input에는 공개 logs.jsonl과 선택해 복사한 기준 v1만 허용한다. 전체 agent profiles 폴더를 마운트하지 않는다.
필드 의미: scenario=실험명, agent_repository=형제 체크아웃, dataset=현재 합성 fixture, timezone=UTC, start=월요일 시작일, weeks=양의 주 수, effective_at=실제 UTC 변경 시점, profiles=변경 전후 선택 경로, detector_input=제한된 공개 입력 목록. 실행 전 별도 검증 구현이 필요하다.
