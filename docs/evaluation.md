# Evaluation

## 분리된 라벨

| 필드 | 의미 |
| --- | --- |
| semantic_drift | 실험에서 적용한 업무 정의가 baseline과 달라짐 |
| output_changed | 같은 snapshot/기간에서 baseline과 적용 정의의 결과가 다름 |
| query_correct_for_used_definition | 지원 SQL 구조가 적용 정의와 일치하는지; 미지원은 null |
| answer_matches_query_result | 제한된 한국어 답변 형식과 실제 SQL 건수가 일치 |
| query_result_matches_reference | 실제 쿼리 결과와 적용 정의 참조 결과 일치 |
| reported_value_matches_query_result | agent가 제출한 구조화 건수와 재실행 값 일치 |

주입한 정의는 바뀌었지만 agent가 이전 SQL을 쓴 경우 생성 검수 실패로 분리한다. 이 C03 트랙은 validated 관측에 대한 정의 변경 탐지 성능을 측정한다. 전체 요청 중 통과 비율도 함께 보고하므로 agent 실패를 숨기지 않는다.

## 분모

요청 수·시도 수·성공 응답 수·생성 실패 수·validated/rejected/unverified 수를 보고한다. private truth에는 성공 응답의 관측 검수 결과를, failures에는 생성/프로토콜/실행 실패를 둔다. query 검수 전에 실패한 경우 성공 응답 수와 truth 수는 다를 수 있다.

공개 입력에는 validated만 포함한다. partial 실행을 평가하려면 --allow-partial이 필요하다. 실패/진행중 실행은 평가하지 않는다. 적격 관측이 0이어도 실패를 음성으로 바꾸지 않고 coverage·점수를 null로 보고한다.

## 점수

- precision = TP / (TP + FP).
- recall = TP / (TP + FN). 양성 abstain은 FN에 포함한다.
- F1 = 2TP / (2TP + FP + FN).
- coverage = (drift 또는 no_drift로 결정한 수) / 적격 전체.
- false_positive_rate = FP / 적격 음성 전체. 음성 유보도 분모에 포함하므로 coverage와 함께 읽는다.
- control_false_positive_rate = 고정 대조군에서 drift 판정 수 / 적격 고정군 수.

음성 abstain은 TN으로 세지 않는다. F1과 precision의 분모가 각각 0이면 null이다. 예를 들어 항상 no_drift인 기준선은 precision=null, 양성 1건을 놓치므로 recall=0/F1=0이다. macro는 케이스별 정의된 값의 평균이며 현재 C03 하나만 있다.

실제 변경일, 최초 관측 가능 시점, 최초 경보 시점은 다른 개념이다. 이번에는 시간 지연 점수를 구현하지 않았으며 temporal.score=null과 사유를 보고한다.

기본 smoke는 development split·합성 fixture·fake model·로컬 unisolated 환경이다. 점수 1.0을 실제 LLM이나 미지 케이스에 일반화하지 않는다.
