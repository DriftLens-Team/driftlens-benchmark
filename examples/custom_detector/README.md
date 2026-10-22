# Custom detector submission

submit.py는 baseline/logs/public manifest만 읽어 no_drift 예측을 내는 최소 외부 제출 예시다. 평가기는 이 예측 파일과 sidecar를 받아 채점한다.

모델을 연결할 때 decision과 evidence 생성만 자신의 방식으로 바꾼다. private truth·case의 v2 정의를 읽지 않는다. 근거가 부족하면 abstain을 내고 coverage로 드러낸다.

현재 이 예시는 로컬 unisolated 실행이다.
