# Benchmarks

실험에서 **무엇의 의미가 달라지는지** 정의한다. 원천 데이터는 [datasets](../datasets/README.md), 실행 코드는 [패키지](../src/driftlens_benchmark/README.md)에 둔다.

- [catalog.yaml](catalog.yaml): 원본 시트의 20개 후보와 상태. C03만 구현했다.
- [cases/](cases/README.md): 질문, 업무 정의, 참조 SQL, 수작업 기대값.
- [suites/](suites/README.md): 기간, 변경 일정, 대조군과 실행 묶음.

이 개발용 폴더에는 변경 정의와 참조 SQL이 있다. 탐지기에 통째로 전달하지 않는다. 탐지 입력은 실행 시 생성한 public bundle이다.
