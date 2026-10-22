# Quick start

설치 명령은 [루트 README](../README.ko.md)를 따른다. 아래 명령은 설치한 Python 환경에서 실행한다.

```text
python -m driftlens_benchmark validate --suite benchmarks/suites/smoke.yaml
python -m driftlens_benchmark run --config configs/runs/smoke.yaml --out runs/demo
python -m driftlens_benchmark detect --public runs/demo/public/L3 --detector sql-rules --out runs/demo/predictions/sql-rules.jsonl
python -m driftlens_benchmark evaluate --run runs/demo --predictions runs/demo/predictions/sql-rules.jsonl
```

run은 DB 생성·agent 호출·SQL/답변 검수·truth/public 저장까지 수행한다. detect와 evaluate를 분리하므로 탐지기 입력에 private 경로를 넣을 필요가 없다.

성공 시 관측 4건과 TP=1/TN=3/FP=0/FN=0, F1=1, coverage=1을 기대한다. 합성 fake 모델 연결 검증 수치다.

```text
runs/demo/
  environment/snapshot-0000.sqlite
  environment/snapshot-0001.sqlite
  private/
    agent/<opaque-id>/config.json
    agent/<opaque-id>/profile.json
    truth.jsonl
    scenarios.private.json
    run.private.json
    failures.jsonl
  public/L3/
    baseline.json
    logs.jsonl
    manifest.json
  predictions/
    sql-rules.jsonl
    sql-rules.jsonl.manifest.json
  reports/sql-rules/
    metrics.json
    report.md
```

반복 실행에서는 새 run 폴더를 쓴다. 동일 run에서 다른 detector 이름/다른 예측 파일 이름으로 비교할 수 있다. 보고서 경로를 바꾸려면 evaluate에 --out을 전달한다.

종료 코드: 성공 0, run의 부분 실패 1, 잘못된 설정/실행 요청 2. run.private.json의 status가 failed/running이면 채점할 수 없다. partial은 --allow-partial로 명시적으로 평가하되 분모와 실패를 함께 보고한다.

agent 시작 실패 시 먼저 같은 환경에서 python -m driftlens_sql_agent --version을 확인한다. 응답 오류의 진단은 private/run.private.json에 코드·종료 상태·stderr 길이/hash만 남긴다. 키나 stderr 원문을 공개 로그에 복사하지 않는다.
