# DriftLens Benchmark

[English](README.md) | 한국어

**같은 지표 이름 아래 업무 정의가 바뀌었는지 SQL 에이전트의 답변과 쿼리에서 탐지하는 벤치마크입니다.**

C03 대형 주문의 기준을 2,000 → 3,000 cents로 바꾸는 변경군과, 2,000 cents를 유지하는 대조군을 함께 실행합니다. 계산상 정확한 SQL·답변에도 의미 변경이 있을 수 있고, 주문 건수가 변해도 정의는 같을 수 있습니다.

현재 **C03 생성 → 외부 SQL agent JSONL 연결 → 관측 검수 → L3 공개 데이터 → 탐지 → 채점**이 구현되어 있습니다. 초기 DB는 3컬럼 SQLite이며 6개 테이블·추가 케이스·L0–L2·격리 실행은 후속 범위입니다.

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

기존 출력 폴더는 덮어쓰지 않습니다. 다시 실행할 때 새 `--out`을 사용하세요. 다른 위치에 설치된 에이전트도 [연결 설정](docs/connecting-an-agent.md)으로 실행할 수 있습니다.

## 예상 결과

자체 합성 주문 8건, 두 주, 변경/고정군 각각 2건으로 공개 관측은 총 4건입니다.

| 실행군 | 2025-W02 | 2025-W03 | 의미 변경 라벨 |
| --- | --- | --- | --- |
| 변경군 | 3건 | 2건 | false → true |
| 정의 고정군 | 3건 | 4건 | false → false |

규칙 탐지기의 예상 혼동행렬은 TP=1, TN=3, FP=0, FN=0입니다. 이는 **fake 모델 연결 검증 결과**이며 실제 LLM의 일반 탐지 성능을 뜻하지 않습니다. `no-drift` 기준선도 비교할 수 있습니다.

보고서는 `runs/demo/reports/sql-rules/report.md`와 `metrics.json`에 생성됩니다. 생성 실패·검수 실패·미검증·유보를 따로 세고, 부분 실행은 기본적으로 채점하지 않습니다.

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

## 데이터와 정보 경계

에이전트에는 해당 주까지의 DB와 선택된 현재 정의만 전달합니다. 공개 로그는 비공개 truth에서 허용된 필드만 추출합니다. 탐지기는 공개 bundle과 기준 정의만 읽고, 평가기만 정답을 결합합니다.

현재 실행은 **로컬 비격리 개발 실행**입니다. 폴더 분리가 OS 접근 통제를 제공하지는 않습니다. SQL 규칙 탐지기는 제한된 COUNT/기간/임계값 형태만 해석하고, 지원하지 않는 표현은 유보합니다. [평가 기준](docs/evaluation.md)을 참고하세요.

## 검증과 기여

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check src tests examples
```

companion 설치 시 실제 별도 프로세스 연결 테스트도 실행됩니다. 미설치 시 해당 테스트는 명시적으로 skip됩니다. 기본 테스트는 외부 LLM을 호출하지 않습니다.

새 케이스는 [케이스 기여 안내](docs/adding-a-case.md), 에이전트는 [연결 안내](docs/connecting-an-agent.md)를 따릅니다. 기존 루트 스크립트는 새 패키지로 교체했습니다. [이전 내역](docs/migration.md)을 확인하세요.

## 라이선스

코드와 자체 합성 fixture: [Apache-2.0](LICENSE). 외부 Jaffle Shop 원천 CSV는 포함하지 않습니다. 업스트림 데이터의 라이선스·출처는 별도로 확인해야 하며, 코드 라이선스가 데이터 재배포 권한을 대신하지 않습니다.
