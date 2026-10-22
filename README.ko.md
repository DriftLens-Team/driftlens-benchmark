# DriftLens Benchmark

[English](README.md) | 한국어

**같은 지표 이름 아래 업무 정의가 바뀌었는지 SQL 에이전트의 답변과 쿼리에서 탐지하는 벤치마크입니다.**

C03 대형 주문의 기준을 2,000 → 3,000 cents로 바꾸는 변경군과, 2,000 cents를 유지하는 대조군을 함께 실행합니다. 계산상 정확한 SQL·답변에도 의미 변경이 있을 수 있고, 주문 건수가 변해도 정의는 같을 수 있습니다.

SQLite DB 생성, 외부 SQL 에이전트 실행, 답변·쿼리 검수, 드리프트 탐지 및 채점을 수행합니다. 현재 C03 케이스와 L3 관측 형식을 지원합니다.

## 빠른 시작

Python 3.11 이상과 Git이 필요합니다. 다음은 저장소 루트의 PowerShell 명령입니다. 첫 실행은 API 키 없는 companion agent의 fake 모델을 사용합니다.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe -m pip install "driftlens-sql-agent @ git+https://github.com/DriftLens-Team/driftlens-sql-agent.git@b67ec9cd8c62763ec68ca896aafeef674081c558"
.venv/Scripts/python.exe -m driftlens_benchmark validate --suite benchmarks/suites/smoke.yaml
.venv/Scripts/python.exe -m driftlens_benchmark run --config configs/runs/smoke.yaml --out runs/demo
.venv/Scripts/python.exe -m driftlens_benchmark detect --public runs/demo/public/L3 --detector sql-rules --out runs/demo/predictions/sql-rules.jsonl
.venv/Scripts/python.exe -m driftlens_benchmark evaluate --run runs/demo --predictions runs/demo/predictions/sql-rules.jsonl
```

Linux/macOS에서는 `.venv/Scripts/python.exe`를 `.venv/bin/python`으로 바꿉니다. 활성화된 환경에서는 `driftlens-benchmark` 명령도 사용할 수 있습니다. 잠긴 의존성 설치는 [개발 안내](CONTRIBUTING.md)를 따릅니다.

실행마다 새 `--out` 폴더를 사용하세요. 다른 에이전트를 연결하려면 [연결 안내](docs/connecting-an-agent.md)를 참고하세요.

## 예상 결과

자체 합성 주문 8건, 두 주, 변경/고정군 각각 2건으로 공개 관측은 총 4건입니다.

| 실행군 | 2025-W02 | 2025-W03 | 의미 변경 라벨 |
| --- | --- | --- | --- |
| 변경군 | 3건 | 2건 | false → true |
| 정의 고정군 | 3건 | 4건 | false → false |

fake provider에서 `sql-rules` 탐지기의 예상 결과는 TP=1, TN=3, FP=0, FN=0입니다. 파이프라인 연결 검증용 결과이며 실제 LLM 성능은 측정하지 않습니다. `no-drift` 기준선도 제공합니다.

보고서는 `runs/demo/reports/sql-rules/report.md`와 `metrics.json`에 생성됩니다. 점수 계산과 실패 처리는 [평가 기준](docs/evaluation.md)을 참고하세요.

## 저장소 구조

| 위치 | 역할 |
| --- | --- |
| [benchmarks/](benchmarks/README.md) | 케이스 정의·참조 SQL·질문·suite·대조군 |
| [datasets/](datasets/README.md) | 출처·스키마·합성 CSV·checksum |
| [configs/](configs/README.md) | 실행·외부 agent 선택 |
| [src/driftlens_benchmark/](src/driftlens_benchmark/README.md) | 환경·계약·연결·관측·탐지·평가 |
| [tests/](tests/README.md) | 경계 조건·프로토콜·종단간 검증 |
| [examples/](examples/README.md) | 외부 연결용 메시지 예시 |
| [docs/](docs/README.md) | 사용·확장·평가·이전 안내 |
| `runs/` | DB·정답·공개 관측·예측·보고서 — Git 제외 |

## 지원 범위

에이전트에는 주간 snapshot과 현재 정의를 전달합니다. 탐지기는 공개 관측과 기준 정의를 읽고, 평가기가 비공개 정답을 결합합니다.

로컬 실행에는 OS sandbox가 없습니다. SQL 검수는 기간과 금액 임계값이 있는 COUNT 쿼리를 지원하며, 그 밖의 표현은 미검증으로 처리합니다. [아키텍처](docs/architecture.md)를 참고하세요.

## 기여

개발 환경과 테스트는 [CONTRIBUTING.md](CONTRIBUTING.md), 새 케이스는 [케이스 기여 안내](docs/adding-a-case.md)를 참고하세요. 기존 루트 스크립트 사용자는 [이전 안내](docs/migration.md)를 확인하세요.

## 라이선스

코드와 포함된 합성 fixture는 [Apache-2.0](LICENSE)을 따릅니다. 외부 데이터에는 해당 데이터의 라이선스가 적용됩니다.
