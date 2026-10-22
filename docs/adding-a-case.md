# Adding a case

원본 ID를 보존해 catalog에 후보를 등록한다. 현재 구현된 것은 C03뿐이다.

1. 경영 질문과 baseline/changed 정의의 차이를 쓴다.
2. 필요한 원천 테이블·단위·집계 행 단위·관측 이력을 명시한다.
3. 같은 snapshot·기간·as-of에 적용하는 두 참조 SQL과 손으로 계산한 경계 기대값을 만든다.
4. 동일 개념의 정의 고정군을 준비한다. 자연 변동을 제거해 답을 쉽게 만들지 않는다.
5. dataset/case/suite contract와 runtime capability를 구현하고 검증한다.
6. 실제로 지원되는 agent를 연결해 종단간 검증한다.

파일 구조는 [C03](../benchmarks/cases/C03_large_orders/README.md)을 따른다. 현행 settings schema는 C03/large_orders만 허용하므로 YAML만 추가한다고 새 case가 동작하지 않는다.

C05·C08·C10·I1·I2·I4·I5는 6개 테이블 확장 후보, C04/I3는 약한 신호 후보다. C01/C02는 추가 합성 이력이 필요하다. ranking/ratio/cohort와 공간적 정의 혼용은 별도 결과형·평가 규칙이 필요하다.

정의가 다르지만 숫자가 같은 샘플을 별도로 검사한다. SQL 숫자 일치가 의미 동등성의 증거를 대체하지 않는다.
