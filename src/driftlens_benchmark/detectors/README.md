# Detectors

baselines.py는 public manifest·baseline·logs만 읽는다. 실제 변경일·case 정의·private truth는 읽지 않는다.

- sql-rules: 해석 가능한 SQL의 threshold를 baseline과 비교한다. 관측 기간 불일치나 미지원 SQL은 abstain.
- no-drift: 항상 no_drift인 비교 기준선.

결과에는 log/result/concept ID, decision, 공개 evidence ID, 근거가 들어간다. 숫자가 바뀌었다는 사실만으로 drift를 판정하지 않는다.

로컬 실행은 unisolated로 표시한다. 외부 탐지기의 파일 제출 방식과 정보 경계는 [안내](../../../docs/writing-a-detector.md)를 따른다.
