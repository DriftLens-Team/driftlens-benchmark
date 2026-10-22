# Writing a detector

입력은 실행에서 생성한 public/L3 폴더뿐이다. baseline.json은 기준 정의, logs.jsonl은 허용 관측, manifest.json은 두 파일의 SHA-256과 포맷 버전이다.

현재 내장 탐지기는 sql-rules와 no-drift다. 다른 탐지기는 [prediction schema](../src/driftlens_benchmark/contracts/detection/v1/prediction.json)에 맞춘 JSONL을 낼 수 있다.

관측마다 정확히 한 prediction이 필요하다. log_id/result_id/concept_id, decision(drift/no_drift/abstain), evidence_log_ids, evidence_summary를 쓴다. 이미 본 공개 log만 근거로 사용할 수 있다. 실제 effective_at은 정답에서 복사하지 않는다.

예측 파일 옆에 <filename>.manifest.json도 만든다.

```json
{
  "contract_version": "detection/v1",
  "detector": "my-detector",
  "detector_version": "1",
  "isolation": "unisolated",
  "predictions_sha256": "<SHA-256 of prediction bytes>",
  "public_manifest_sha256": "<SHA-256 of public manifest bytes>"
}
```

해시는 benchmark.artifacts.digest 또는 표준 SHA-256 구현으로 계산한다. evaluate --run <run> --predictions <file>로 제출한다. ID 누락/중복/추가, 미래 evidence, hash 불일치는 실패한다. 외부 제출 example은 [예시 폴더](../examples/README.md)를 참고한다.

기본 내장 detector는 파일 접근 격리를 구현하지 않는다. 공식 격리 실행과 동적 플러그인 registry는 후속 범위다.
