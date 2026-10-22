# Examples

[submissions/request.json](submissions/request.json)과 [response.json](submissions/response.json)은 첫 주의 합성 C03 agent/v1 메시지다. 실제 fixture에서 threshold=2000으로 계산하면 3건이다.

request/response는 개별 JSON 객체다. 프로세스 통신에서는 UTF-8 한 줄 JSONL로 직렬화해 전달한다. version은 실행 인자 --protocol-version v1로 선택한다.

[custom_detector/submit.py](custom_detector/submit.py)는 공개 입력만 읽고 항상 no_drift인 외부 제출 파일과 hash sidecar를 만드는 실행 예시다.

```text
python examples/custom_detector/submit.py --public runs/demo/public/L3 --out runs/demo/predictions/example.jsonl
python -m driftlens_benchmark evaluate --run runs/demo --predictions runs/demo/predictions/example.jsonl
```
