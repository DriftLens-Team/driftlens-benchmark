# 아키텍처와 구현 상태

[English overview](../README.md) | [한국어 개요](../README.ko.md)

이 문서는 현재 실행 경로와 계획된 구성요소의 책임, 정보 경계, 버전 기록을 설명한다. 설정 예시와 주석 전용 Python 파일은 설계 안내이며 실행 기능을 제공하지 않는다. 실제 사용 방법은 저장소 루트 README를 따른다.

## 현재와 예정
현재 루트 generate.py·driftlens.py·public_logs.py·sql_tool.py가 생성·검수·공개 로딩·SQLite 조회를 담당한다. data는 합성 fixture, 루트 테스트는 오프라인 검증, runs는 생성 산출물 위치다. src/ 아래 파일은 전부 주석만 있으며 자동 실행·패키지·CLI가 아니다.

| 경로 | 향후 역할 |
| --- | --- |
| ../contracts/v1/README.md | 공개 로그와 프로세스 통신 계약 |
| ../datasets/README.md | 원본 출처·스키마·단위 기록 |
| ../scenarios/A_definition_change/README.md | 정의 변경 실험 |
| ../scenarios/controls/README.md | 정의 고정 대조군 |
| ../configs/README.md | 실행 관리자 전용 설정 |
| ../src/README.md | 실행 관리자·adapter·logging·detector·evaluation |

[agent 저장소](https://github.com/DriftLens-Team/driftlens-sql-agent)의 공통 엔진을 별도 프로세스로 호출하고 JSONL로 요청·응답하는 것이 목표다. 현재 agent.py는 benchmark 내부 유틸리티를 import하는 공개 로그 SQL replay이며 이 의존성은 현재 유지된다.

## 정보 경계
탐지기에는 허용 공개 로그와 기준 v1만 전달한다. truth, 미래 v2, 실제 적용 profile, 실제 변경 시점, 실행 메타데이터는 평가용 비공개 영역이다. 생성 관리자만 실험 생성을 위해 실제 profile과 변경 시점을 사용하고, 선택된 profile만 agent에 전달한다. 탐지기는 저장소 전체나 설정 폴더에 접근하지 않도록 향후 실행 환경에서도 격리해야 한다. 파일 분리는 접근 통제 구현 자체가 아니다.
SQLite를 우선 사용한다. 다른 DB는 agent의 조회 경계와 설정 매핑을 교체하는 지점만 설계하며 연결을 구현하지 않는다.

## 독립적인 버전 기록 (향후 계획)
코드 변경·DB 변경을 업무 정의 변경과 혼동하지 않도록 다음 축을 서로 독립적으로 private run metadata에 기록한다. 기존 공개 로그 10필드와 truth 4필드는 확장하지 않는다.

| 축 | 기록할 식별자 |
| --- | --- |
| agent 코드 | agent_repo_commit |
| 실행 설정 | profile_id, config_hash |
| 프롬프트·모델·생성 조건 | prompt_hash, model_id, generation_settings |
| 업무 정의 | ontology_version_used, definition_hash |
| DB·데이터와 매핑 | dataset_id, snapshot_hash, schema_mapping_hash |
| 탐지기 | detector_version, detector.config_hash |
| 교환 계약 | contract_version |

설정의 config_hash와 탐지기 config_hash는 별도 영역으로 구분한다. 코드 커밋, DB 스냅샷 또는 매핑 해시가 바뀌어도 그것만으로 업무 정의 변경이나 contaminated=true를 뜻하지 않는다. 정의 버전과 해시를 별도로 비교한다. 이 기록 방식은 향후 계획이며 현재 자동 기록 기능은 없다.
실제 실행 profile, 미래 정의, 실제 변경 시점은 비공개 실행 기록에만 두고 공개 agent_id나 파일명에 인코딩하지 않는다. agent_id는 실제 적용 버전을 누설하지 않는 안정적인 식별자로 유지한다. 생성 관리자는 선택된 설정으로 실행하고 evaluator만 평가 시 비공개 기록과 정답을 읽는다. 탐지기는 자신의 버전·설정 외에 허용 공개 로그와 기준 v1만 받는다.
