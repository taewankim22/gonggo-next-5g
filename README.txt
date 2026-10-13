공고다음 · 5G
공고 속 조건을, 내 다음 행동으로.

서비스: https://gonggo-next-5g-gjkapf7kye4lzappppjuy9s6.streamlit.app/
코드: https://github.com/taewankim22/gonggo-next-5g

무엇을 하나요?
대학생이 장학금·대외활동·공모전 공고를 올리고 본인 상황을 답하면,
지원 조건, 제출서류, 준비 시점과 다음 행동을 정리합니다. 선발이나 최종 지원 자격은 결정하지 않습니다.

화면
1. 공고 넣기: PDF, HWP 5.x, HWPX, JPG/JPEG, PNG (15MB 이하, PDF 1~30쪽).
2. 핵심 확인: 지원 대상·제출 경로·마감·원문 확인.
3. 내 상황: 공고에 연결된 질문에 답변. 모르는 항목은 비워 둡니다.
4. 준비 목록: 다음 행동, 조건별 독립 판정표, 현재 서류, 이후 단계 서류, 상세 AI 검토.
인스타 색상의 4단계 화면이며 모바일에서는 판정표가 세로로 배치됩니다.

조건별 독립 판정 (2026-10-13)
- 학적·잔여학기·횟수·시간 등 원문 근거와 대조 가능한 항목을 각각 판정합니다.
- 확인된 수치 불일치는 다른 조건의 미입력 때문에 사라지지 않습니다.
- 자유서술 답변은 입력됐다는 이유만으로 개별 일치 판정하지 않습니다. AI 범주 검토를 별도로 확인합니다.
- 서류 이름과 원문의 상위 절을 연결해 시점을 정합니다. 후속연구 절은 다음 페이지에도 이어집니다.
- 이후 단계와 시점 미확정 서류는 현재 필수 누락 목록에서 분리합니다. 적용 대상 아님과 이후 단계는 다릅니다.
- 대상 여부와 준비 상태는 자기 확인이며 실제 증빙 내용·진위·접수 완료를 검증하지 않습니다.
- TXT와 검토 JSON에 독립 판정·원문 근거·시점을 포함합니다.

Upstage 구조
공고 원본 → 공고분석 Studio [Parse → Extract, 39필드, 설정 4]
→ 코드의 질문·체크리스트·독립 조건 검증 → 공고와 답변을 비교 PDF로 구성
→ 맞춤검토 Studio [Parse → Extract, 28필드, 설정 2]
→ JSON 형식·원문 인용 확인, 확인된 불일치 보존 → 화면과 다운로드.
현재 Classify·Instruct 노드를 사용하지 않습니다. 웹앱 코드가 저장·질문 연결·수치 대조·단계 분리를 맡습니다.
워크플로우 내보내기는 agent_configs/notice.mission2.export.json, review.mission2.export.json입니다.
다른 계정은 워크플로우를 가져온 뒤 자신의 Agent ID·Config ID로 연결해야 합니다.

내 컴퓨터에서 실행 (Python 3.12 권장)
python -m venv .venv
Windows: .venv\Scripts\python.exe -m pip install -r requirements.txt
Windows: .venv\Scripts\python.exe -m streamlit run app.py
macOS/Linux: .venv/bin/python -m pip install -r requirements.txt
macOS/Linux: .venv/bin/python -m streamlit run app.py
개인 모드에서는 연결 설정에 자신의 API 키와 Agent ID를 입력합니다.
공유 모드는 TEAM_SETUP.txt 안내대로 Streamlit Secrets를 설정합니다. 키를 코드에 쓰지 마세요.

저장·개인정보
공고 원본·본문, 답변·체크·현재 단계는 해당 브라우저 IndexedDB에 저장됩니다.
API 키·실행 로그·상세 AI 결과는 브라우저 자동 저장에서 제외됩니다.
같은 주소·브라우저 프로필에서 복원되며 기기 간 동기화 기능은 없습니다. 여러 탭은 마지막 저장이 남습니다.
공용 컴퓨터에서는 설정의 저장 내용 지우기를 사용하세요. 개인 계정으로 암호화된 저장소가 아닙니다.
실제 분석 시 원본과 비교 PDF가 앱 서버를 거쳐 Upstage로 전송됩니다.
공급자의 파일·실행 보존은 해당 서비스 정책과 계정 설정을 따릅니다. 결과 JSON 공유 전 답변을 확인하세요.

공개 테스트 운영
현재는 사용자가 선택한 무암호·일일 횟수 무제한 모드입니다. 방문자가 운영자의 크레딧을 사용합니다.
서버 Secrets의 키는 방문자 브라우저에 저장하지 않습니다. 동시 1건과 10초 간격 보호는 유지합니다.
공고 분석과 맞춤검토는 각각 별도 호출입니다. 대기 시간 초과·실패 시 자동 재호출하지 않습니다.
개인 모드의 직접 입력 키는 세션에서만 사용합니다. 제공사 사용량·크레딧 제한은 별개입니다.

배포
Streamlit Community Cloud에서 이 저장소 main 브랜치의 app.py를 실행합니다.
설정은 Cloud Secrets를 사용하며 .env·실제 키·사용자 실행 기록을 GitHub에 올리지 않습니다.
소스 변경을 main에 반영하면 배포 앱에 적용됩니다. 적용 후 화면과 실제 호출을 별도로 검증합니다.

검증
python -m pip install pytest
python -m pytest tests -q
공개 저장소의 테스트는 저장·호출 보호·조건 분리·실제 공개 문서의 단계 구분을 검증합니다.
전체 개발 작업 공간에는 별도의 문서 입력·앱 흐름·실제 API 실행 기록이 있습니다.
테스트 개수나 스키마 통과는 전체 추출 정확도를 뜻하지 않습니다.

한계
자유서술·복합 조건, 흐린 이미지, 잘못된 OCR, 인용 연결, 원문 자체의 충돌은 확인 필요가 남을 수 있습니다.
독립 표의 일치는 해당 수치나 자기 확인 항목만을 뜻하며 전체 자격이나 증빙 유효성을 보장하지 않습니다.
같은 서류가 여러 시점에 나오거나 시점 근거를 연결하지 못하면 제출 시점 확인 필요로 남깁니다.
HWP/HWPX는 Studio 변환 본문을 근거로 사용하며 원본의 시각적 페이지와 다를 수 있습니다.
별도 원본 여러 개 사이의 대조, 자동 수집·지원, 개인 계정·기기 동기화는 구현하지 않았습니다.
실제 사용자 시간 절감과 일반 정확도는 아직 측정하지 않았습니다.

참고
https://ku-sejong-hackathon-playbook.vercel.app/
https://github.com/SuWanKim-code/document-agent-hackathon-starter-code
