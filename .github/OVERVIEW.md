# Collaboration and CI

workflows/ci.yml은 Windows/Ubuntu의 오프라인 core 테스트와 wheel build를 실행한다. 별도 companion job은 고정 revision을 설치한 뒤 실제 subprocess fake-provider 종단간 검증을 수행한다.

외부 LLM 키는 사용하지 않는다. case 제안과 PR은 목적·정의 차이·검증 근거를 포함한다. 기여 절차는 루트 CONTRIBUTING.md를 따른다.
