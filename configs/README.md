# Configs

[runs/smoke.yaml](runs/smoke.yaml)은 suite·agent·seed를 선택하고, [agents/sql-agent-v1.yaml](agents/sql-agent-v1.yaml)은 실행 command·provider·timeout·capability를 정한다.

모든 데이터/설정 경로는 그 경로를 가진 파일의 부모 기준이다. command의 첫 항목에 경로를 쓰면 agent 설정 기준, bare executable은 PATH 기준이다. `{python}`은 benchmark를 실행하는 interpreter로 바뀐다. 나머지 command 인자에 들어가는 파일 경로는 절대 경로를 사용한다.

업무 정의는 case definitions.json 한 곳에만 둔다. 실제 agent config/profile은 실행마다 private/agent에 생성한다. API 키 값은 설정 파일에 넣지 않는다.

알 수 없는 키·중복 YAML 키·미지원 capability·입력 checksum 불일치는 실패한다. fake와 live는 명시적으로 선택하며 자동 대체하지 않는다. detector는 현재 CLI의 sql-rules/no-drift 두 이름으로 선택한다. 사용하지 않는 detector 설정 파일은 두지 않는다.
