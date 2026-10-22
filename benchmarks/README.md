# Benchmarks

실험에서 **무엇의 의미가 달라지는지** 정의한다. 원천 데이터는 [datasets](../datasets/README.md), 실행 코드는 [패키지](../src/driftlens_benchmark/README.md)에 둔다.

- [catalog.yaml](catalog.yaml): 케이스 20개의 정의와 지원 상태.
- [cases/](cases/README.md): 질문, 업무 정의, 참조 SQL, 수작업 기대값.
- [suites/](suites/README.md): 기간, 변경 일정, 대조군과 실행 묶음.

탐지 입력은 실행 시 생성한 public bundle이다. 이 폴더의 변경 정의와 참조 SQL은 탐지기에 전달하지 않는다.
