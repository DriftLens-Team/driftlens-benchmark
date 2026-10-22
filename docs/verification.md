# Verification · 2026-10-22

검증 환경: Windows, Python 3.11.9. benchmark 0.2.0.dev0, SQL agent 0.1.0.dev0의 고정 commit `b67ec9cd8c62763ec68ca896aafeef674081c558`.

| 확인 | 결과 |
| --- | --- |
| `python -m pytest -q` | 72 passed; 실제 companion subprocess fake-provider 테스트 포함 |
| `python -m ruff check src tests examples` | 통과 |
| `python -m build --wheel` | 성공; versioned JSON Schema 리소스 포함 |
| 별도 환경에 wheel + 고정 Git revision agent 설치 | 성공; editable source 경로가 아닌 site-packages에서 로딩 |
| 저장소 밖 cwd에서 validate → run → detect → evaluate | 성공 |
| 외부 탐지기 제출 예시 → evaluate | 성공; constant no-drift F1=0, coverage=1 |
| 문서 상대 링크 | 존재 여부 확인 |

최종 wheel 실행 산출물은 로컬 `runs/demo/`에 있다. 이 폴더는 Git에서 제외된다. 코드·계약·입력·설정 hash와 agent commit은 private run manifest, 예측 구현 hash는 prediction sidecar에 기록한다.

## C03 결과

- 요청/응답/적격 관측 각각 4건, 생성 실패·검수 실패·미검증 0건.
- 변경군 주간 건수 3 → 2, 고정군 3 → 4.
- SQL 규칙 탐지: TP=1, TN=3, FP=0, FN=0.
- precision=recall=F1=coverage=1.0, 고정군 오탐률=0.

이는 합성 8행·L3·fake-provider 연결 검증이다. 실제 LLM API 호출이나 held-out 성능 평가를 수행한 것은 아니다. 로컬 실행은 unisolated다. CI workflow는 추가했지만 원격 GitHub Actions 실행 결과를 확인한 것은 아니다.

주요 실패 검증은 잘못된/중복 응답·ID·기간, 출력 상한·timeout, SQL 권한, nested 정답 누출, 미래 evidence, 불완전 예측 집합, partial 실행, 유보와 0분모, 동일 숫자/다른 의미와 잘못된 SQL의 우연한 숫자 일치를 포함한다.
