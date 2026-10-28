# Contracts

이 폴더의 JSON Schema가 기계 판독 계약의 정본이다. 설치 패키지에도 포함한다.

- agent/v1: 현재 companion의 요청 네 필드, 성공 관측 다섯 필드, 오류 봉투.
- records/v2: 공개 관측 열 필드와 확장 결과 구조, private truth, baseline, public manifest.
- records/v1: 기존 공개 로그를 읽기만 하는 명시적 legacy validator.
- detection/v1: drift/no_drift/abstain과 공개 근거.
- settings: 실행·suite·case·dataset·agent 설정.
- agent/v2: 7개 SemAlign 개념의 요청·응답. companion의 명시적 v2 모드와 연결한다.
- records/v3: nullable 관측, 의미 baseline, pair/series, 준비/검수 manifest, private attempt·truth 계약.
- semantics/v1: data 소유 의미 명세와 공개 스키마 제약.
- detection/v2: LOG/T1/T2 제출, 공개 입력에 묶인 manifest, 온라인 prefix별 제출.

JSON 중복 키, NaN/Infinity, bool/실수 건수, 추가 nested 필드를 거부한다. 날짜·기간의 교차 일관성은 Python validator가 검사한다. 업무 정의 v1/v2와 통신/레코드 버전은 서로 다르다.

`contracts.legacy.load_legacy(path)`는 과거 공개 로그를 읽지만 새로운 정답이나 결과형을 추측해 이관하지 않는다. 기존 C03 실행에는 records/v2를 사용한다. SemAlign 준비에는 records/v3를 사용하고 실제 생성 검수 결과로 표시하지 않는다. 새 버전의 교차 필드 검증 API는 contracts.semalign에 있다.
