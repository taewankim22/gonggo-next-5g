공고다음 · 5G | 동료에게 공유하는 실행 코드

사용 흐름
공고 넣기 → 핵심 확인 → 내 상황 → 준비 목록.
PDF, HWP 5.x, HWPX, JPG, PNG를 분석합니다.
로그인 없는 예시 체험은 설정에서 '예시 화면 체험'을 선택하세요.
예시는 API 호출 없는 고정 데이터입니다.

저장과 API 키
- 원본 공고, 추출 본문, 답변, 체크, 현재 단계는 각 브라우저의 IndexedDB에 자동 저장됩니다.
- '이 브라우저에 저장 완료' 표시 후 새로고침하거나 앱을 다시 열면 복원됩니다.
- API 키는 저장하지 않습니다. 새 접속 시 실제 AI 분석을 하려면 다시 입력하세요.
- 서버 환경변수의 API 키도 자동으로 읽지 않습니다. 사이트 운영자의 키를 방문자에게 공유하지 않습니다.
- 같은 브라우저 프로필·같은 사이트 주소에서는 준비 내용이 공유됩니다. 여러 탭을 동시에 수정하면 마지막 저장이 남습니다.
- 브라우저/기기/사이트 주소가 바뀌면 자동 이동하지 않습니다. 브라우저 저장 삭제·시크릿 모드에서는 보존을 보장하지 않습니다.
- 설정의 '저장한 공고·답변·체크 지우기'로 해당 브라우저의 초안을 삭제합니다.
- 공용 컴퓨터에서는 사용 후 초안을 지우세요. 자동 저장은 로그인·암호화된 개인 계정 저장소가 아닙니다.
- 실제 분석할 때 원본과 답변이 앱 서버를 거쳐 Upstage에 전송됩니다. 영구 저장 위치와 분석 전송은 별개입니다.
- 상세 AI 검토 결과와 실행 로그는 자동 저장에서 제외합니다. 필요하면 검토 JSON을 내려받으세요.

동료가 실제 분석하는 방법
1. Upstage Studio에서 agent_configs/notice.mission2.export.json과 review.mission2.export.json을 가져옵니다.
2. 본인이 접근할 수 있는 두 Agent ID와 설정 버전을 앱의 접힌 설정에 입력합니다.
3. 해당 계정의 API 키를 앱에 직접 입력합니다. 키를 메신저·GitHub·설정 파일로 공유하지 마세요.
4. 공고 분석 후 필요한 답변만 입력하고 준비 목록을 확인합니다.
5. 내 조건과 대조하기를 누를 때만 맞춤 검토 API가 실행됩니다.
다른 계정에서 기존 Agent에 접근할 수 있는지는 Upstage 권한에 따라 달라집니다.

내 컴퓨터에서 실행 (Python 3.12 권장)
python -m venv .venv
Windows: .venv\Scripts\python.exe -m pip install -r requirements.txt
Windows: .venv\Scripts\python.exe -m streamlit run app.py
macOS/Linux: .venv/bin/python -m pip install -r requirements.txt
macOS/Linux: .venv/bin/python -m streamlit run app.py

인터넷 배포 (Streamlit Community Cloud)
1. 이 폴더의 코드를 GitHub 저장소에 올립니다. .env나 개인 데이터는 넣지 않습니다.
2. https://share.streamlit.io/ 에 로그인하고 Create app을 선택합니다.
3. 저장소, main 브랜치, app.py를 선택합니다. Python 3.12를 선택해 배포합니다.
4. API 키는 Cloud Secrets에도 넣지 않습니다. 사용자가 사이트의 입력란에 직접 입력합니다.
5. 배포된 https://...streamlit.app 주소를 공유합니다. 127.0.0.1은 타인 접속용 주소가 아닙니다.
비공개 GitHub 코드를 사용하면 호스팅의 저장소 접근 권한과 앱 방문 권한은 별도로 설정합니다.
계정 약관·OAuth 권한 승인은 계정 소유자가 확인해야 합니다.

공유 파일 범위
실행에 필요한 코드, 공개 예시 공고 1개, Studio 워크플로우 내보내기, 저장 기능 테스트만 포함합니다.
개인 실행 증거, 브라우저 초안, API 키, .env, 개발 환경, 전체 작업 폴더는 포함하지 않습니다.

검증
python -m pip install pytest
python -m pytest tests -q
전체 개발 폴더의 통합 UI 테스트 및 새로고침/탭 재접속 검증과 구분된 저장 기능 테스트입니다.

주의할 한계
지원 자격이나 선발 결과를 확정하지 않습니다. 원문·최신 공지를 확인하세요.
사이트에 접속할 수 있다는 것만으로 Upstage API 권한이 생기지는 않습니다.
