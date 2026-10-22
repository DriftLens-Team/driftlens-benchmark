# Connecting an agent

현재 연결은 agent/v1 JSONL subprocess다. 설치 위치는 자유이며 benchmark와 companion 사이에 내부 import는 없다.

[agent 설정](../configs/agents/sql-agent-v1.yaml)의 command는 인자 배열이다. 기본 `{python}`은 benchmark Python을 뜻한다. 다른 환경은 첫 항목에 해당 Python 실행 파일을, 별도 브리지 스크립트는 절대 경로를 지정한다.

runner가 매 요청에 다음 인자를 붙인다.

```text
--config <absolute-runtime-config> --profile <absolute-current-profile> --protocol-version v1
```

config에는 읽기 전용 DB 경로, 고정 3컬럼 mapping, cents, provider·환경변수 이름이 있다. profile에는 현재 large_orders 정의 하나만 있다. 에이전트가 미래 정의·일정·truth를 읽어서는 안 된다.

## 메시지

```json
{"request_id":"req-001","request":"이번 주 대형 주문은 몇 건인가요?","timestamp":"2025-01-12T23:59:59Z","period":"2025-W02"}
```

성공 응답은 request_id/status=ok/observation이고 observation은 sql, answer_text, definition_note, reported_values, referenced_concepts다. [정확한 합성 예시](../examples/submissions/response.json)를 참고한다.

오류 응답은 request_id/status=error/error(code,message)다. response와 요청 period/ID가 같아야 한다. stdout에는 응답 한 줄만 쓰고 flush한다. 입력 EOF 후 정상 종료한다. 한 줄은 UTF-8 65,536 bytes 이하다. 현재 부모는 한 요청 뒤 프로세스를 종료하므로 계속 살아서 새 요청을 기다리는 서버형 브리지는 지원하지 않는다.

현재 지원: orders(order_id TEXT, ordered_at TEXT, order_total_cents INTEGER), large_orders, weekly, 음수가 아닌 정수 건수. agent의 실제 테이블 검사 때문에 임의 추가 컬럼/뷰를 대신 전달하면 안 된다.

## Companion

검증한 revision: b67ec9cd8c62763ec68ca896aafeef674081c558. 설치:

```text
python -m pip install "driftlens-sql-agent @ git+https://github.com/DriftLens-Team/driftlens-sql-agent.git@b67ec9cd8c62763ec68ca896aafeef674081c558"
```

개발 체크아웃은 python -m pip install -e <agent-checkout>으로 설치해도 된다. 설치 version·가능한 commit/dirty 상태를 private manifest에 기록한다. 다른 command의 바이너리 provenance는 자동 추측하지 않는다.

live 호출은 agent 설정을 복사해 provider를 upstage로 바꾸고 run 설정에서 선택한다. UPSTAGE_API_KEY와 UPSTAGE_MODEL을 환경에 설정한다. 키 없이 시작하면 실패하고 fake로 대체하지 않는다. 모델 ID는 사용 가능한 값을 지정한다. 자동 테스트는 fake provider를 사용한다.
