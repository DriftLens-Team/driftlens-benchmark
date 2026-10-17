# 향후 실행 코드 위치
runner.py는 실행 관리, adapter.py는 별도 agent 프로세스 연결, logging.py는 공개·비공개 기록 분리, detector.py는 탐지, evaluation.py는 평가를 맡을 예정이다. 각 파일은 한국어 주석뿐이다. 세부 helper 파일이나 패키지 초기화 파일은 만들지 않았다. logging.py는 이 디렉터리를 PYTHONPATH에 넣어 표준 라이브러리 logging을 대체하도록 사용하지 않는다.
