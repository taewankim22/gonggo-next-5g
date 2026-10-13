"""Studio Responses API, based on the official hackathon starter's agent_client.py."""
import json
import logging
import time
from openai import OpenAI

class StudioError(RuntimeError):
    pass

def decode_output(text):
    try:
        value = json.loads(text)
        # Some workflows wrap the one Extract node in its node name.
        if isinstance(value, dict) and len(value) == 1 and isinstance(next(iter(value.values())), dict):
            value = next(iter(value.values()))
        return value
    except (ValueError, TypeError):
        raise StudioError('Studio 응답이 JSON이 아닙니다. Extract 결과와 스키마를 확인해주세요.') from None

def decode_steps(steps, fallback=''):
    extracts=[s for s in steps if 'extract' in str(s.get('model','')).lower() and any(c.get('text') for c in s.get('content',[]) if c.get('type')=='output_text')]
    texts=[c.get('text','') for s in (extracts[-1:] or steps[-1:]) for c in s.get('content',[]) if c.get('type')=='output_text']
    result=decode_output(''.join(texts) if texts else fallback)
    if isinstance(result,dict) and '공고유형' in result:
        classified=[c.get('text','').strip().strip('"') for step in steps if 'classify' in str(step.get('model','')).lower() for c in step.get('content',[]) if c.get('type')=='output_text']
        if classified and classified[-1] in ('장학금','대외활동·봉사','대회·공모전','기타'):result['공고유형']=classified[-1]
        reviews=[]
        for step in steps:
            if 'instruct' not in str(step.get('model','')).lower():continue
            for c in step.get('content',[]):
                if c.get('type')!='output_text':continue
                text=c.get('text','')
                try:
                    decoded=json.loads(text)
                    if isinstance(decoded,str):text=decoded
                except (ValueError,TypeError):pass
                # Studio citation identifiers are not page numbers; resolve the supplied mapping.
                import re
                extra=c.get('additional_values') or {}
                if isinstance(extra,str):
                    try:extra=json.loads(extra)
                    except ValueError:extra={}
                citations={str(v.get('index')):v.get('page') for v in extra.get('citations',[]) if isinstance(v,dict)} if isinstance(extra,dict) else {}
                def source_page(match):
                    page=citations.get(match[1])
                    return f' (원문 {page}쪽)' if isinstance(page,int) and page>0 else ''
                text=re.sub(r'【†(\d+)】',source_page,text)
                reviews.append(text)
        result['_workflow_review']='\n\n'.join(reviews)
    return result

def run_agent(api_key, agent_id, config_id, pdf, filename='notice.pdf', progress=None, timeout=600, mime='application/pdf', trace=None):
    if not api_key or not agent_id.startswith('agt_'):
        raise StudioError('연결 설정에 API 키와 올바른 Agent ID를 입력해주세요.')
    started = time.monotonic()
    phase = 'connect'
    try:
        with OpenAI(api_key=api_key, base_url='https://api.upstage.ai/v2', timeout=45, max_retries=0) as client:
            if trace and trace.get('job_id'):
                phase = 'resume'
                if (trace.get('agent_id'), str(trace.get('config_id'))) != (agent_id, str(config_id)):
                    raise StudioError('진행 중인 분석과 현재 에이전트 설정이 다릅니다. 기존 실행 내역을 확인해주세요.')
                response = client.responses.retrieve(trace['job_id'], include=['all'])
                file_id = trace['file_id']
            else:
                if progress: progress('원본 파일을 Upstage에 전달하고 있습니다.')
                phase = 'upload'
                # Upload retry does not start an agent run. Keep submission
                # retries disabled so an ambiguous response cannot double-run it.
                file = client.with_options(max_retries=2).files.create(file=(filename, pdf, mime), purpose='user_data', timeout=120)
                file_id = file.id
                phase = 'submit'
                response = client.responses.create(model=agent_id, include=['all'],
                    input=[{'role':'user','content':[{'type':'input_file','file_id':file_id}]}],
                    extra_body={'config_id':config_id or '1'}, timeout=timeout)
                # Save before any UI callback can interrupt the script. Reruns
                # retrieve this same job instead of paying for another request.
                if trace is not None:
                    trace.update(job_id=response.id,agent_id=agent_id,config_id=config_id,file_id=file_id,started_at=time.time())
            while response.status in ('queued','in_progress'):
                phase = 'poll'
                elapsed = time.time()-trace['started_at'] if trace and trace.get('started_at') else time.monotonic()-started
                if elapsed > timeout:
                    raise StudioError('분석 대기 시간이 초과되었습니다. Studio 실행 내역을 먼저 확인하세요. 자동 재실행하지 않았습니다.')
                if progress: progress('Studio에서 문서를 읽고 조건을 추출하고 있습니다…')
                time.sleep(2)
                response = client.responses.retrieve(response.id, include=['all'])
            if response.status != 'completed':
                hint = ' 한글 파일이 열리는지 확인하고, 계속 실패하면 한글에서 PDF로 저장해 다시 올려주세요.' if filename.lower().endswith(('.hwp','.hwpx')) else ''
                raise StudioError('Studio 분석이 완료되지 않았습니다. 실행 내역과 크레딧, 워크플로우 설정을 확인해주세요.'+hint)
            dumped=response.model_dump()
            steps=dumped.get('output',[])
            if trace is not None:
                trace.update(job_id=response.id,agent_id=agent_id,config_id=config_id,file_id=file_id,created_at=response.created_at,steps=steps)
            return decode_steps(steps,getattr(response,'output_text',''))
    except StudioError:
        raise
    except Exception as exc:
        code = getattr(exc, 'status_code', None)
        # Provider messages/headers may contain user data: log only fixed phase
        # names, exception class and numeric HTTP status, never the error body.
        logging.getLogger(__name__).warning('Studio request failed: phase=%s type=%s status=%s',phase,type(exc).__name__,code if isinstance(code,int) else None)
        if code in (401,403):
            message = 'API 키 또는 워크플로우 접근 권한을 확인해주세요.'
        elif code == 429:
            message = '사용량 제한에 도달했습니다. 크레딧과 호출 제한을 확인해주세요.'
        elif code == 404:
            message = 'Agent ID 또는 설정 버전을 찾을 수 없습니다.'
        elif code in (400,415,422) and filename.lower().endswith(('.hwp','.hwpx')):
            message = 'Studio가 이 한글 파일을 처리하지 못했습니다. 한글에서 파일을 확인한 뒤 PDF로 저장해 다시 올려주세요. 자동 재실행하지 않았습니다.'
        else:
            message = 'Upstage 연결 또는 응답 처리에 실패했습니다. 네트워크와 Studio 실행 내역을 확인해주세요.'
        # Never expose provider error bodies, headers or API keys to the UI/logs.
        raise StudioError(message) from None
