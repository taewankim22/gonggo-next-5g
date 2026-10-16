"""Public source adapters. Never execute source scripts or trust search snippets."""
import io
import re
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup
from PIL import Image
from collect_notices import decode_html, normalized
from core import fingerprint
from input_tools import inspect_input
from live_catalog import now_iso
from national_search import aggregator,NOTICE_WORDS
from public_network import fetch

BODY_SELECTORS = ('#bo_v_atc','#bo_v_con','.contest_view .detail','.bbs_view .conwrap','.program_view',
    '#VIEW_MCONTENT','.b-content-box .fr-view','.artclView','.board-view-content','.board_view_cont',
    '.board-view-cont','.board_view_contents','.bbs-view-content','.view-content','.view_cont',
    '.viewCon','.view_conts','.view-con','.board_txt','.board-content','.board_view .cont',
    '.board_view .contents','.boardView .content','.board-view .content','.view_txt',
    '.viewCon .cont','.bbs_con','#view_content','#boardContents','.se-contents',
    '.viewTypeSec1 .viewContent .cont','.viewTypeSec1 .viewContent','.viewTypeSec1 .viewCont','.view-detail','.board-view-detail',
    '[itemprop="articleBody"]','article')
TITLE_SELECTORS=('#bo_v_title','.contest_view h3.tit','.bbs_view .titarea .tit','.program_view_head .desc_title .title',
                 '.b-title','.artclViewHead h2','.artclViewHead','.view-title','.view_title',
                 '.board_view .subject','.subject','article h1','article h2','title')
EXTENSIONS=('.pdf','.hwp','.hwpx','.png','.jpg','.jpeg','.zip','.docx','.xlsx')
# Verified bulletin structures, scoped to their hosts so generic layout classes
# cannot accidentally include menus or unrelated announcements elsewhere.
SITE_SELECTORS={
    'scatch.ssu.ac.kr':(('#contents .col-lg-9 > .bg-white > div:last-child',),
                       ('#contents .col-lg-9 h1',)),
}


def source_url(url):
    url=normalized(url)
    if aggregator(url):raise ValueError('보도·공고 모음 사이트입니다. 주최기관 원문을 연결해야 자동 분석할 수 있습니다.')
    return url


def parse_public_article(response, fallback_title):
    soup=BeautifulSoup(decode_html(response),'html.parser')
    title=fallback_title
    body=None
    extra_body,extra_title=SITE_SELECTORS.get(urlsplit(response.url).hostname,((),()))
    for sel in extra_body+BODY_SELECTORS:
        for n in soup.select(sel):
            if len(n.get_text(' ',strip=True))>=70 or n.find('img'):
                body=n;break
        if body is not None:break
    if body is None:
        raise ValueError('이 사이트의 공고 본문 구조를 아직 지원하지 않습니다. 공식 원문 파일을 직접 올려주세요.')
    for selector in extra_title+TITLE_SELECTORS:
        node=soup.select_one(selector)
        value=node.get_text(' ',strip=True) if node else ''
        if 8<=len(value)<=300 and NOTICE_WORDS.search(value):
            title=value;break
    # Work on a copy so attachment areas elsewhere in the source remain intact.
    body=BeautifulSoup(str(body),'html.parser')
    for n in body.select('script,style,iframe,form,button,input,object,embed,nav,header,footer'):
        n.decompose()
    if len(str(body))>400_000:raise ValueError('본문이 너무 큽니다. 원본 공고 파일로 확인해주세요.')
    return title,body,soup


def file_name(response, hint=''):
    disposition=response.headers.get('content-disposition','')
    match=re.search(r"filename\*?\s*=\s*(?:UTF-8''|\")?([^\";]+)",disposition,re.I)
    hints=[unquote(match[1]) if match else '',hint,unquote(urlsplit(response.url).path)]
    name=next((Path(s).name for s in hints if Path(s).suffix.lower() in EXTENSIONS),'')
    # Some source servers encode UTF-8 bytes as Latin-1 twice in HTTP headers.
    # Only a lossless round trip is accepted; ordinary Korean filenames stay as-is.
    for _ in range(2):
        try:fixed=name.encode('latin-1').decode('utf-8')
        except (UnicodeEncodeError,UnicodeDecodeError):break
        if fixed==name:break
        name=fixed
    if not name:
        data=response.body
        ext=('.pdf' if data.startswith(b'%PDF-') else '.png' if data.startswith(b'\x89PNG') else
             '.jpg' if data.startswith(b'\xff\xd8') else '.hwp' if data.startswith(b'\xd0\xcf\x11\xe0') else '')
        if data.startswith(b'PK'):
            import zipfile
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    ext='.hwpx' if 'Contents/content.hpf' in z.namelist() else '.zip'
            except zipfile.BadZipFile:ext='.bin'
        name='document'+(ext or '.bin')
    return name


def attachment_links(soup,base):
    out=[];seen=set()
    for a in soup.select('a[href]'):
        # Footer accessibility certificates and navigation downloads are not
        # attachments to the current announcement (observed on silla.ac.kr).
        if any(p.name in ('footer','header','nav') or p.get('role') in ('contentinfo','navigation','banner')
               or re.search(r'(^|[\s_-])(?:footer|gnb|lnb)(?:$|[\s_-])',
                            str(p.get('id',''))+' '+' '.join(p.get('class',[])),re.I)
               for p in a.parents):continue
        href=a['href'];name=a.get_text(' ',strip=True) or a.get('title','')
        if href.startswith(('javascript:', '#')):continue
        full=urljoin(base,href)
        is_file=any(unquote(urlsplit(full).path).lower().endswith(e) or name.lower().endswith(e) for e in EXTENSIONS)
        is_download=bool(re.search(r'download|fileDown|downFile|attachNo=',full,re.I))
        if not is_file and not is_download:continue
        try:full=normalized(full)
        except ValueError:continue
        if full in seen:continue
        seen.add(full);out.append((full,name))
    return out


def prepare_public_article(candidate,folder):
    from web_notice import source_pdf
    url=source_url(candidate['url'])
    response=fetch(url)
    resolved=source_url(response.url)
    folder=Path(folder)/fingerprint(url)[:16];folder.mkdir(parents=True,exist_ok=True)
    documents=[];warnings=[];attachments=[];images={}
    title=candidate['title'];text='';source_title_verified=False
    content_type=response.content_type.lower()
    if 'html' not in content_type and (response.body[:4] in (b'%PDF',b'\x89PNG',b'\xd0\xcf\x11\xe0') or response.body.startswith((b'PK',b'\xff\xd8'))):
        name=file_name(response);inspect_input(response.body,name)
        documents.append(dict(name=name,filename=name,data=response.body,document_url=url,basis='공개 웹 문서 원본 · 문서 자체 페이지 기준'))
    else:
        title,body,soup=parse_public_article(response,title)
        _,extra_titles=SITE_SELECTORS.get(urlsplit(response.url).hostname,((),()))
        source_title_verified=any(n.get_text(' ',strip=True)==title
                                  for selector in extra_titles+TITLE_SELECTORS for n in soup.select(selector))
        text=body.get_text(' ',strip=True)
        for styled in body.select('[style]'):
            bg=re.search(r'background-image\s*:\s*url\([\'\"]?([^\)\'\"]+)',styled.get('style',''),re.I)
            if bg:
                tag=body.new_tag('img',src=bg[1]);styled.append(tag)
        for node in list(body.find_all('img')):
            src=node.get('src') or node.get('data-src','')
            if not src:node.decompose();warnings.append('주소 없는 본문 이미지가 있습니다.');continue
            full=urljoin(response.url,src)
            if full in images:continue
            if len(images)>=12:
                node.decompose();warnings.append('본문 이미지 12개를 넘는 나머지는 원문 확인 필요');continue
            try:
                picture=fetch(full)
                with Image.open(io.BytesIO(picture.body)) as im:
                    if im.width*im.height>30_000_000:raise ValueError('이미지 크기 초과')
                    if max(im.size)<120:node.decompose();continue
                    if im.format not in ('PNG','JPEG'):
                        out=io.BytesIO();im.convert('RGB').save(out,format='PNG');picture.body=out.getvalue()
                    else:im.verify()
                node['src']=full;images[full]=picture.body
            except (ValueError,OSError,Image.DecompressionBombError):
                node.decompose();warnings.append('본문 이미지 다운로드·읽기 실패: '+full)
        if len(text)>=70 or images:
            try:
                data=source_pdf(title,body,response.url,images,include_provenance=False)
                documents.append(dict(name='게시글 본문과 포스터',filename='article.pdf',data=data,
                    document_url=url,basis='공개 게시글 재구성 PDF · 페이지는 재구성본 기준'))
            except ValueError as exc:warnings.append(str(exc))
        links=attachment_links(soup,response.url)
        for link,name in links[:10]:
            try:
                attachment=fetch(link);filename=file_name(attachment,name)
                inspect_input(attachment.body,filename)
                documents.append(dict(name=name or filename,filename=filename,data=attachment.body,
                    document_url=link,basis='공개 첨부 원본 · 첨부 자체 페이지 기준'))
                attachments.append(dict(url=link,name=name or filename,status='ok'))
            except (ValueError,OSError) as exc:
                attachments.append(dict(url=link,name=name,status='failed'))
                warnings.append('첨부 확인 필요: '+(name or link)+' · '+str(exc))
        if len(links)>10:warnings.append('첨부 10개를 넘는 나머지는 원문 확인 필요')
        # Script-only downloads are not silently reported as complete.
        if any(re.search(r'(?:fileDown|download|downFile|attachFile)\s*\(',a.get('href','')+' '+a.get('onclick',''),re.I)
               for a in soup.select('a[href^="javascript:"],a[href="#"]')):
            warnings.append('스크립트 방식 첨부가 있습니다. 원문에서 추가 확인해주세요.')
    if not documents:raise ValueError('읽을 수 있는 본문·첨부를 확보하지 못했습니다. 원문 파일로 확인해주세요.')
    for doc in documents:(folder/(fingerprint(doc['data'])+Path(doc['filename']).suffix)).write_bytes(doc['data'])
    return dict(title=title,url=url,resolved_url=resolved,checked_at=now_iso(),documents=documents,
                source_title_verified=source_title_verified,
                attachments=attachments,warnings=list(dict.fromkeys(warnings)),body_text=text,
                attachment_limit_reached=False,source_name=candidate.get('source_name','웹 검색'),
                source_kind=candidate.get('source_kind','웹 검색 원문 · 기관 확인 필요'))
