# 케이스 목록과 구현 순서

상태: 승인 당시 제안 기록. 현재 C03 구현과 나머지 후보 상태는 [실제 catalog](../../../benchmarks/catalog.yaml)를 따른다. [Drifts Data v0.1](https://docs.google.com/spreadsheets/d/1Cb72YOTOXoL8SKgs7ulR0KI9WT5WsE04RsISl_SBcqA/edit?gid=1475341752)와 [설계 문서](https://docs.google.com/document/d/1RJzZjKqDIeIE_QokJdtjtV0WRs8pyqf2-XRr4ESzR6s/edit)를 2026-10-22에 읽었다. 시트의 ‘통과’는 구현 가능성에 대한 예비 판정이며 탐지 성능이 아니다.

## 식별자

원본 시트의 숫자 ID는 `C01`부터 `C15`로, 추가 제안은 `I1`부터 `I5`로 보존한다. 문서의 시간축 절 번호로 재번호를 붙이지 않는다. 예를 들어 문서의 ‘시간축 06 음식 매출’은 원본 ID 08이므로 **C08**이다. 기존 Scenario A는 C03의 alias로 기록한다.

## 후보 20개

| 새 ID | 개념 | 정의 차이 | 초기 배치 |
| --- | --- | --- | --- |
| C01 | 재구매 고객 | 전체 이력 2회 → 최근 달력상 1년 2회 | 추가 합성 이력 필요, 보류 |
| C02 | 신규 고객 | 브랜드 최초 → 매장 최초 | 교차 매장 고객 합성 필요, 보류 |
| C03 | 대형 주문 | 총액 ≥2000 → ≥3000 cents | 1단계 smoke, 기존 agent 연동 |
| C04 | 객단가 | 세전 평균 → 세후 평균 | challenge, 평균 결과형 |
| C05 | 음식 주문 | 음식 포함 → 음식만 포함 | core, orders/items/products |
| C06 | 재구매율 | 고객 비율 → 주문 비율 | 후속 contextual 트랙 |
| C07 | 인기 상품 | 판매 개수 순위 → 고객 수 순위 | 후속 ranking |
| C08 | 음식 매출 | 음식 품목 금액 → 음식 포함 주문의 세전 전체 금액 | core, 중복 합산 검사 |
| C09 | 음식 비중 | 금액 비중 → 품목 수 비중 | 후속 contextual·ratio |
| C10 | 주문 원가 | 전체 공급품 → 부패성 공급품만 | core, SKU 원가 선집계 |
| C11 | 수익성 높은 상품 | 이익액 순위 → 이익률 순위 | 후속 ranking |
| C12 | 누적 매출 | 전체 관측 이력 → 연초 이후 | 후속 누적 시계열 |
| C13 | 매출 성장률 | 전체 매장 → 기존 매장군 | 기간·기존점 정의 재설계 |
| C14 | 월 고객 매출 | 거래 월 → 획득 월 코호트 누적 | 후속 cohort |
| C15 | 평균 세율 | 거래 가중 실효세율 → 매장 동일가중 명목세율 | 후속 contextual·ratio |
| I1 | orders | 주문 건수 → 품목 행수 | core |
| I2 | active_customers | 주 1회 이상 → 주 2회 이상 | core |
| I3 | small_orders | <1000 → <1500 cents | challenge, 2000 대안은 미확정 |
| I4 | items_sold | 전체 품목 → 음식 품목 | core |
| I5 | beverage_orders | 음료 포함 주문, 정의 고정 | core 대조군 |

전체 후보를 catalog에 등록하되 미구현 폴더 20개를 한 번에 만들지 않는다. 해당 케이스를 구현할 때 필요한 case bundle과 테스트를 함께 추가한다. 상태는 `candidate`, `blocked_data`, `implemented`, `validated`로 관리하고 ‘예비 통과’ 원문 판정은 별도 provenance에 둔다.

## suite 구성

| suite | 구성 | 에이전트 요구 |
| --- | --- | --- |
| `smoke` | C03의 v1→v2 변경군 + C03 v1 고정군 | 현재 sql-agent v1 가능 |
| `temporal-core` | C03/C05/C08/C10/I1/I2/I4와 각 정의 고정군, I5 | 현재 agent는 C03만 가능; 나머지는 fixture/reference 또는 확장 agent |
| `temporal-challenge` | C04/I3와 동일 개념 고정군 | 평균·새 개념 지원 필요 |
| 후속 contextual | C06/C07/C09/C11/C14/C15 | 팀·목적 비교, ratio/ranking/cohort 필요 |

I5 하나만 모든 케이스의 대조군으로 쓰지 않는다. **각 시간축 케이스의 동일 snapshot·질문·기간에 v1을 고정한 paired control**을 기본으로 하고 I5를 자연 변동 대조 사례로 추가한다. control 여부는 private에만 기록한다.

suite의 실행 모드는 `fixture/reference`와 `external_agent`로 구분한다. 참조 SQL·템플릿으로 만든 케이스 데이터가 외부 챗봇에서 성공했다는 뜻은 아니다. 지원하지 않는 외부 agent 실행은 reference 모드로 자동 대체하지 않는다.

## 날짜와 난이도

- C03의 2025-01-15는 기존 코드 기본값이다. 새 core suite의 확정 변경일로 복사하지 않는다.
- I1 2025-05-05, I2 2025-01-27, I3 2024-12-09, I4 2025-06-02는 원문 제안일로 기록한다. 확정 suite가 선택한 날짜와 출처를 private manifest에 남긴다.
- 개발 fixture는 별도 합성 달력·변경일로 경계를 검증할 수 있다. 연구용 core suite 날짜와 혼동하지 않는다.
- 초기 주간 트랙은 UTC 월요일 경계로 전환일을 맞추는 안을 권장한다. 현재 agent v1의 일요일 timestamp 기준으로 주 전체에 선택된 profile을 적용하는 규칙과 함께 명시한다.
- 브루클린 첫 주문이 속한 2025-03-10 주와 2025-06-23 주의 자연 변동은 제거하지 않는다. 시트의 +56%는 전체 주문 관련 보고이며 I5 자체의 변화율이라고 주장하지 않는다.
- 변화량·신호/변동 수치는 공식 점수로 복사하지 않고 산식·구간을 정한 후 다시 계산한다.

## 구현 단계와 완료 조건

1. **패키지·계약 정리:** 설치 후 CLI discovery, 버전별 schema, 기존 C03 fixture 의미 보존. 새 package에서 돌아가는 검증을 확보한 뒤 루트 단일 파일을 제거.
2. **C03 종단간 실행:** 3컬럼 agent snapshot, 실제 JSONL subprocess, fake 모델, paired control, private→public 투영, 기준 탐지기·채점. API 키 없이 성공하고 프로토콜 오류도 검증.
3. **DB·케이스 확장:** 6개 테이블과 referential integrity, C05/C08/C10/I1/I2/I4/I5의 참조 SQL·수작업 fixture. 이 단계의 완료는 외부 agent의 범용 지원을 뜻하지 않음.
4. **확장 agent·실험:** 별도 agent 계약 합의, 실제 모델 E2E, L0–L2 누출 검사, challenge, 시간순 평가. 실행 격리와 평가 split 고정 후 성능 보고.

각 단계는 `planned → implemented → verified` 근거를 기록한다. 구현하지 않은 기능을 루트 README의 완료 기능으로 나열하지 않는다.
