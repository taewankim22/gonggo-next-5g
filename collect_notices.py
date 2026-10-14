"""Official-board collector, shared by the CLI and the app's discovery flow.

Adapted from contest-agent's bounded public fetch and URL/link discovery approach.
Run: python collect_notices.py --output verification/discovery/collected --limit 3
No scheduler, credentials, personal profile, database, Slack, or submission integration.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin,urlsplit,urlunsplit,parse_qsl,urlencode
from public_network import fetch,canonical_url,AgentError

BOARD='https://www.sejong.ac.kr/kor/intro/notice7.do'

def decode_html(response):
    match=re.search(r'charset=["\s]*([\w-]+)',response.content_type,re.I)
    if match:
        try:return response.body.decode(match[1])
        except (LookupError,UnicodeDecodeError):pass
    try:return response.body.decode('utf-8')
    except UnicodeDecodeError:return response.body.decode('cp949',errors='replace')

class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.current=None;self.parts=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='a' and attrs.get('href'):self.current=[attrs['href'],'']
    def handle_data(self,text):
        self.parts.append(text)
        if self.current:self.current[1]+=text
    def handle_endtag(self,tag):
        if tag=='a' and self.current:self.links.append(tuple(self.current));self.current=None

def normalized(url):
    p=urlsplit(canonical_url(url))
    values=parse_qsl(p.query)
    identified=any(k in ('articleNo','seqNo','contentNo','idx','nttId','boardSeq') for k,v in values)
    ignored={'article.offset','articleLimit','fbclid','gclid'}
    if identified:ignored|={'page','pageNo','pageIndex','layout','title','keyword','where','searchType','searchWord'}
    keep=sorted((k,v) for k,v in values if k not in ignored and not k.startswith('utm_'))
    return urlunsplit((p.scheme,p.netloc,p.path,urlencode(keep),''))

def discover(board=BOARD):
    response=fetch(board);parser=Links();parser.feed(decode_html(response))
    seen=set();out=[]
    for href,title in parser.links:
        url=urljoin(response.url,href)
        if urlsplit(url).netloc!=urlsplit(board).netloc:continue
        if urlsplit(url).path!=urlsplit(board).path:continue
        query=dict(parse_qsl(urlsplit(url).query))
        if query.get('mode')!='view' or not query.get('articleNo'):continue
        url=normalized(url)
        if url in seen:continue
        seen.add(url);out.append({'url':url,'title':' '.join(title.split())})
    return out

def collect(candidate,output):
    now=dt.datetime.now(dt.timezone.utc).isoformat();url=candidate['url']
    ident=hashlib.sha256(url.encode()).hexdigest()[:16];folder=Path(output)/ident;folder.mkdir(parents=True,exist_ok=True)
    prior=json.loads((folder/'manifest.json').read_text(encoding='utf-8')) if (folder/'manifest.json').exists() else {}
    result={**candidate,'id':ident,'checked_at':now,'attachments':[],'status':'failed'}
    try:
        response=fetch(url);digest=hashlib.sha256(response.body).hexdigest();(folder/(digest+'.html')).write_bytes(response.body)
        parser=Links();parser.feed(decode_html(response))
        result.update(html_sha256=digest,status='collected',html_changed=bool(prior) and prior.get('html_sha256')!=digest)
        seen=set()
        downloads={urljoin(response.url,h) for h,t in parser.links if urlsplit(urljoin(response.url,h)).netloc==urlsplit(url).netloc and 'mode=download' in h}
        result['attachment_limit_reached']=len(downloads)>5
        for href,title in parser.links:
            link=urljoin(response.url,href)
            if urlsplit(link).netloc!=urlsplit(url).netloc or 'mode=download' not in link or link in seen:continue
            seen.add(link)
            try:
                attachment=fetch(link);sha=hashlib.sha256(attachment.body).hexdigest()
                suffix=Path(title.strip()).suffix.lower()
                if suffix not in ('.pdf','.hwp','.hwpx','.jpg','.png','.zip'):suffix='.bin'
                filename=sha+suffix;(folder/filename).write_bytes(attachment.body)
                old=next((a for a in prior.get('attachments',[]) if a['url']==link),{})
                result['attachments'].append({'url':link,'name':title.strip(),'sha256':sha,'file':filename,'status':'ok','changed':bool(old) and old.get('sha256')!=sha})
            except AgentError as exc:result['attachments'].append({'url':link,'status':'failed','error':str(exc)})
            if len(result['attachments'])>=5:break
    except AgentError as exc:result['error']=str(exc)
    (folder/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',default='verification/discovery/collected');ap.add_argument('--limit',type=int,default=3);args=ap.parse_args()
    candidates=discover();results=[collect(c,args.output) for c in candidates[:max(1,min(args.limit,10))]]
    Path(args.output,'collection.json').write_text(json.dumps({'board':BOARD,'candidates':candidates,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'candidates':len(candidates),'collected':len(results),'attachments':sum(len(r['attachments']) for r in results),'status':[r['status'] for r in results]}))
