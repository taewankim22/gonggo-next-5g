공고다음 · 5G | 동료에게 공유하는 실행 코드

사이트: https://gonggo-next-5g-gjkapf7kye4lzappppjuy9s6.streamlit.app/
공개 코드: https://github.com/taewankim22/gonggo-next-5g
암호 없는 공개 테스트 연결 설정은 TEAM_SETUP.txt를 참고하세요.

사용 흐름
공고 넣기 → 핵심 확인 → 내 상황 → 준비 목록.
PDF, HWP 5.x, HWPX, JPG, PNG를 분석합니다.
사이트에 바로 접속한 뒤 설정에서 '실제 AI 분석' 또는 '예시 화면 체험'을 선택하세요.
예시는 API 호출 없는 고정 데이터입니다.

저장과 API 키
- 원본 공고, 추출 본문, 답변, 체크, 현재 단계는 각 브라우저의 IndexedDB에 자동 저장됩니다.
- '이 브라우저에 저장 완료' 표시 후 새로고침하거나 앱을 다시 열면 복원됩니다.
- 공유 모드는 운영자의 API 키를 Streamlit Secrets에 보관합니다. 방문자에게 키를 보내거나 브라우저에 저장하지 않습니다.
- 현재 공개 테스트는 암호 없이 사용합니다. 링크를 가진 누구나 운영자 크레딧으로 분석할 수 있습니다.
- 개인 실행 모드는 세션마다 직접 입력하고 키를 저장하지 않습니다. 서버 환경변수 키를 자동으로 읽지 않습니다.
- 같은 브라우저 프로필·같은 사이트 주소에서는 준비 내용이 공유됩니다. 여러 탭을 동시에 수정하면 마지막 저장이 남습니다.
- 브라우저/기기/사이트 주소가 바뀌면 자동 이동하지 않습니다. 브라우저 저장 삭제·시크릿 모드에서는 보존을 보장하지 않습니다.
- 설정의 '저장한 공고·답변·체크 지우기'로 해당 브라우저의 초안을 삭제합니다.
- 공용 컴퓨터에서는 사용 후 초안을 지우세요. 자동 저장은 로그인·암호화된 개인 계정 저장소가 아닙니다.
- 실제 분석할 때 원본과 답변이 앱 서버를 거쳐 Upstage에 전송됩니다. 영구 저장 위치와 분석 전송은 별개입니다.
- 상세 AI 검토 결과와 실행 로그는 자동 저장에서 제외합니다. 필요하면 검토 JSON을 내려받으세요.

동료가 실제 분석하는 방법
1. 운영자가 TEAM_SETUP.txt의 안내대로 Streamlit Secrets를 설정합니다.
2. 동료는 사이트에 접속합니다. 공개 테스트에서는 암호나 API 키 입력이 필요 없습니다.
3. 실제 AI 분석 모드에서 공개 공고 또는 분석 권한이 있는 공고를 선택합니다.
4. 공고 분석 후 필요한 답변만 입력하고 준비 목록을 확인합니다.
5. 내 조건과 대조하기를 누를 때만 맞춤 검토 API가 실행됩니다.
공고 분석과 맞춤 검토 각각 1회로 계산하며 기본 한도는 팀 전체 하루 20회입니다. 실패 요청도 포함합니다.
단일 서버 장부는 재생성 시 초기화될 수 있어 영구적인 요금 상한이 아닙니다.

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
4. TEAM_SETUP.txt에 따라 Cloud Secrets에 팀 연결을 설정합니다. 실제 키·암호는 코드 파일에 넣지 않습니다.
5. 배포된 https://...streamlit.app 주소를 공유합니다. 127.0.0.1은 타인 접속용 주소가 아닙니다.
비공개 GitHub 코드를 사용하면 호스팅의 저장소 접근 권한과 앱 방문 권한은 별도로 설정합니다.
계정 약관·OAuth 권한 승인은 계정 소유자가 확인해야 합니다.

공유 파일 범위
실행에 필요한 코드, 공개 예시 공고 1개, Studio 워크플로우 내보내기, 저장 기능 테스트만 포함합니다.
개인 실행 증거, 브라우저 초안, API 키, .env, 개발 환경, 전체 작업 폴더는 포함하지 않습니다.

검증
python -m pip install pytest
python -m pytest tests -q
브라우저 저장 데이터 필터, 팀 인증·호출 제한, 팀 접속 화면을 검증합니다. 실제 Upstage 호출은 별도 검증이 필요합니다.

주의할 한계
지원 자격이나 선발 결과를 확정하지 않습니다. 원문·최신 공지를 확인하세요.
사이트에 접속할 수 있다는 것만으로 Upstage API 권한이 생기지는 않습니다.
