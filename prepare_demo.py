"""Human-curated fixture from the public PDF. Never represented as an API result."""
from pathlib import Path
import json
import shutil
from pypdf import PdfReader
from schema_builder import notice_schema, review_schema, QUESTION_KEYS, CATEGORIES

ROOT=Path(__file__).parent
def prepare():
    folder=ROOT/'data'; folder.mkdir(exist_ok=True)
    source=ROOT.parent/'research/opportunity/hyundai_jump_13.pdf'
    shutil.copyfile(source,folder/'hyundai_jump_13.pdf')
    pages=[p.extract_text() for p in PdfReader(source).pages]
    n={k:[] if v['type']=='array' else '' for k,v in notice_schema()['properties'].items()}
    n.update(notice_title='2026 현대점프스쿨 13기 대학생 봉사자(장학샘) 모집',notice_type='장학연계활동',
      application_deadline='2026-01-26',deadline_note='2026.01.15.(목) ~ 2026.01.26.(월). 현재 마감된 평가용 공고.',
      question_keys=QUESTION_KEYS,allowed_statuses=['재학','휴학'],minimum_remaining_terms='2',
      minimum_weekly_visits='2',minimum_weekly_hours='4',preference_center='여명학교',
      preference_skill='중국어 활용 또는 북한·한반도 관련 분야 관심 및 교육 현장 활용 의사',
      required_documents=['공통 필수: 성적 증명서 — 온라인 서류 접수','해당자 선택: 사회적 배려 대상 증빙 — 온라인 서류 접수'],
      source_conflicts=['발대식 날짜(2026.02.26~27)와 표기 요일(수~목)이 달라 운영기관 확인 필요.','활동센터의 실제 요일·시간은 공고에 명시되지 않음.'])
    spans={
      'eligibility':(1,'재학생 및 휴학생 (학습센터로의','<현대점프스쿨 장학샘 인재상>'),
      'preference':(1,'희망 활동 학습센터를','- 탈북 배경을'),
      'commitment':(2,'주 2회, 4시간','2)  활동 기간:'),
      'documents':(1,'① (공통,필수)','※우대사항'),
      'schedule':(2,'사전교육 및 발대식','\n 3 '),
    }
    rules={
      'eligibility':'4년제 대학 재학생·휴학생, 2026년 3월 기준 잔여학기 2학기 이상. 수료생·졸업예정자 불가. 지역 및 안정적 이동 조건 별도 확인.',
      'preference':'중국어 활용 또는 북한·한반도 관련 관심 및 교육 현장 활용 의사에 대한 우대는 여명학교 선택자에게만 적용.',
      'commitment':'주 2회, 총 4시간. 방학에도 동일하며 총 10개월 활동.',
      'documents':'성적증명서 공통 필수. 사회적 배려 증빙은 해당자 선택 서류.',
      'schedule':'면접 2월 6~12일 지역별 상이, 발대식 2월 26~27일 예정. 센터별 실제 요일·시간은 확인 필요.',
    }
    for key,(page,start,end) in spans.items():
        text=pages[page]; begin=text.index(start); finish=text.index(end,begin)
        n[key+'_quote']=text[begin:finish].strip()
        n[key+'_page']=str(page+1); n[key+'_rule']=rules[key]
    (folder/'demo_notice.json').write_text(json.dumps(n,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'provenance.json').write_text(json.dumps({'source':'https://kuds.korea.ac.kr/bbs/kuds/154/175731/download.do','fixture':'공개 PDF를 사람이 읽어 작성한 예시 데이터. Studio 실행 결과 아님.','deadline':'2026-01-26','usage':'마감된 공고의 조건 검증용'},ensure_ascii=False,indent=2),encoding='utf-8')

def sample_review(notice, a):
    result={k:[] if v['type']=='array' else '' for k,v in review_schema()['properties'].items()}
    result['summary']='예시 데이터와 고정 규칙을 이용한 화면 체험입니다. 실제 AI 분석 결과가 아닙니다.'
    for key in CATEGORIES:
        result[key+'_status']='확인 필요'
        result[key+'_reason']='이 항목의 조건과 내 상황을 원문에서 확인해주세요.'
        result[key+'_quote']=notice[key+'_quote']; result[key+'_page']=notice[key+'_page']
        result[key+'_action']={'eligibility':'학적·잔여학기 외에 4년제 대학, 지역·통학 조건도 확인하세요.',
          'preference':'선택한 기관에 적용되는 우대인지 원문을 확인하세요.',
          'commitment':'주 2회 방문과 총 4시간을 10개월 동안 확보할 수 있는지 확인하세요.',
          'documents':'성적증명서를 준비하고 해당하는 경우에만 추가 증빙을 준비하세요.',
          'schedule':'요일 표기 오류와 센터별 활동 시간을 운영기관에 문의하세요.'}[key]
    if a.get('enrollment_status') in ('재학','휴학') and (a.get('remaining_terms') or 0)>=2:
        result['eligibility_reason']='입력한 학적·잔여학기는 추출된 두 조건과 일치합니다. 대학 유형·지역·통학 등은 별도로 확인해야 합니다.'
    if a.get('selected_center')=='여명학교' and a.get('skills'):
        result['preference_reason']='여명학교를 선택했으므로 역량 우대 검토 대상입니다. 입력한 역량과 교육 현장에서의 활용 의사를 함께 확인하세요.'
    if a.get('weekly_visits') is not None and a.get('weekly_hours') is not None:
        result['commitment_reason']=f"주 {a['weekly_visits']}회, 총 {a['weekly_hours']}시간으로 답했습니다. 10개월 지속 가능 여부는 추가 확인이 필요합니다."
    result['documents_reason']=f"현재 단계: {a.get('review_stage') or '미입력'}. 증빙 파일을 받지 않았으므로 완비 여부는 판정하지 않습니다."
    result['schedule_reason']='센터별 활동 요일·시간이 명시되지 않았고, 발대식 날짜와 요일 표기도 충돌합니다.'
    return result

if __name__=='__main__':prepare()
