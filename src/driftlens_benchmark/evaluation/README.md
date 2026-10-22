# Evaluation

scoring.py만 private truth와 predictions를 ID로 결합한다. public projection·파일 hash·완료 상태·ID 집합·미래 근거 사용을 검증한다. 부분 실행은 --allow-partial이 있어야 채점한다.

TP/FP/TN/FN, 양성/음성 유보, precision/recall/F1, coverage, 고정군 FPR을 제공한다. 양성 유보는 recall에서 FN에 포함한다. 생성 실패·검수 실패를 no_drift로 바꾸지 않는다. 분모가 0이면 null이다.

보고서는 reports/<prediction-file-stem>/에 metrics.json과 report.md로 생성되며 기존 경로를 덮어쓰지 않는다. 변화 시점 점수는 미구현이다. 상세 정의는 [평가 기준](../../../docs/evaluation.md)을 따른다.
