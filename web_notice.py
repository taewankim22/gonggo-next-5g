"""Turn an allowlisted official article into inspectable document choices.

HTML is data only. Navigation/scripts are excluded. Tables retain cell spans,
inline posters are included, and unavailable attachments are always disclosed.
"""
import io
import json
import re
from html import escape
from pathlib import Path
from urllib.parse import urljoin, urlsplit, parse_qsl

from bs4 import BeautifulSoup, NavigableString
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.platypus.doctemplate import LayoutError

from collect_notices import BOARD, collect, normalized
from core import fingerprint
from input_tools import inspect_input
from public_network import AgentError, fetch

SOURCE_NAME = '세종대학교 공식 장학 게시판'


def article_url(url):
    url = normalized(url)
    p, board = urlsplit(url), urlsplit(BOARD)
    q = dict(parse_qsl(p.query))
    if (p.scheme, p.netloc, p.path) != (board.scheme, board.netloc, board.path) or q.get('mode') != 'view' or not q.get('articleNo', '').isdigit():
        raise ValueError('연결된 공식 게시판의 공고만 가져올 수 있습니다.')
    # Only identity parameters: tracking and presentation parameters cannot fork a notice.
    return BOARD + '?articleNo=' + q['articleNo'] + '&mode=view'


def parse_article(html):
    soup = BeautifulSoup(html, 'html.parser')
    body = soup.select_one('.b-content-box .fr-view')
    title = soup.select_one('.b-title')
    if not body or not title:
        raise ValueError('공고 본문 영역을 찾지 못했습니다. 사이트 구조가 바뀌었는지 확인해주세요.')
    for node in body.select('script,style,iframe,form,button,input,object,embed'):
        node.decompose()
    if not body.get_text(strip=True) and not body.find('img'):
        raise ValueError('공고 본문이 비어 있어 분석하지 않았습니다.')
    if len(str(body)) > 400_000:
        raise ValueError('공고 본문이 너무 큽니다. 필요한 공고 파일을 직접 올려주세요.')
    return title.get_text(' ', strip=True), body


def source_pdf(title, body, url, images,include_provenance=True):
    font_path = Path('C:/Windows/Fonts/malgun.ttf')
    font = 'GonggoWebKorean' if font_path.exists() else 'HYSMyeongJo-Medium'
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font, str(font_path)) if font_path.exists() else UnicodeCIDFont(font))
    style = ParagraphStyle('source', fontName=font, fontSize=10, leading=15, wordWrap='CJK')
    story = [Paragraph(escape(title), style), Spacer(1, 10)]

    def inline(node):
        if isinstance(node, NavigableString):
            return escape(str(node))
        if node.name == 'br':
            return '<br/>'
        if node.name == 'img':
            return ''
        text = ''.join(inline(child) for child in node.children)
        if node.name == 'a' and node.get('href', '').startswith(('https://', 'http://')):
            text += ' (' + escape(node['href']) + ')'
        return text

    def image_block(node):
        key = urljoin(url, node.get('src', ''))
        data = images.get(key)
        if data is None:
            raise ValueError('본문 이미지가 누락되어 분석을 중단했습니다.')
        with PILImage.open(io.BytesIO(data)) as im:
            w, h = im.size
        scale = min(500 / w, 690 / h)
        story.extend([Image(io.BytesIO(data), width=w*scale, height=h*scale), Spacer(1, 8)])

    def table_block(node):
        matrix, spans, occupied = [], [], set()
        for y, row in enumerate(node.find_all('tr')):
            cells = []
            for cell in row.find_all(['td', 'th'], recursive=False):
                x = len(cells)
                while (x, y) in occupied:
                    cells.append(''); x += 1
                try:
                    cs, rs = int(cell.get('colspan', 1)), int(cell.get('rowspan', 1))
                except ValueError:
                    raise ValueError('공고 표의 병합 셀을 읽지 못했습니다.') from None
                if not 1 <= cs <= 12 or not 1 <= rs <= 30:
                    raise ValueError('공고 표가 지원 범위를 벗어납니다. 원문 파일을 직접 올려주세요.')
                cells.append(Paragraph(inline(cell), style))
                cells.extend([''] * (cs-1))
                if cs > 1 or rs > 1:
                    spans.append(('SPAN', (x, y), (x+cs-1, y+rs-1)))
                occupied.update((xx, yy) for yy in range(y, y+rs) for xx in range(x, x+cs))
            matrix.append(cells)
        width = max((len(r) for r in matrix), default=0)
        if not width or width > 12 or len(matrix) > 60 or node.find('img') or node.find('table'):
            raise ValueError('복잡한 중첩 표 또는 이미지 표입니다. 원본 공고 파일을 직접 올려주세요.')
        for row in matrix:
            row.extend([''] * (width-len(row)))
        if any(cmd[2][1] >= len(matrix) for cmd in spans):
            raise ValueError('표의 병합 범위를 확인하지 못했습니다.')
        table = Table(matrix, colWidths=[500/width]*width, hAlign='LEFT')
        table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.4,colors.grey),
                                   ('VALIGN',(0,0),(-1,-1),'TOP'),
                                   ('LEFTPADDING',(0,0),(-1,-1),5),
                                   ('RIGHTPADDING',(0,0),(-1,-1),5)] + spans))
        story.extend([table, Spacer(1, 10)])

    def walk(node):
        if isinstance(node, NavigableString):
            if str(node).strip():
                story.append(Paragraph(escape(str(node)), style))
        elif node.name == 'table':
            table_block(node)
        elif node.name == 'img':
            image_block(node)
        elif node.name in ('p','li','h1','h2','h3','h4') and not node.find(['table','p','div']):
            text = inline(node)
            if text.strip():
                story.extend([Paragraph(text, style), Spacer(1, 5)])
            for im in node.find_all('img'):
                image_block(im)
        else:
            for child in node.children:
                walk(child)
    walk(body)
    # Retrieval time is outside the PDF so unchanged content has a stable hash.
    if include_provenance:
        story += [Spacer(1, 15), Paragraph('공식 게시글 본문을 분석용 PDF로 재구성했습니다. 페이지 번호는 이 PDF 기준입니다. 첨부파일은 별도 문서입니다.', style),
                  Paragraph(escape(url), style)]
    out = io.BytesIO()
    try:
        SimpleDocTemplate(out, title=title, author='5G', leftMargin=45, rightMargin=45,
                          topMargin=40, bottomMargin=40, invariant=1).build(story)
    except LayoutError:
        raise ValueError('본문 표를 분석용 문서로 재구성하지 못했습니다. 원본 파일을 직접 올려주세요.') from None
    data = out.getvalue()
    inspect_input(data, 'article.pdf')
    return data


def prepare_article(candidate, folder):
    """Return document choices, never personal state or instructions for the agent."""
    candidate = {'url':article_url(candidate['url']), 'title':str(candidate['title'])[:300]}
    collected = collect(candidate, folder)
    if collected['status'] != 'collected':
        raise ValueError(collected.get('error', '공고를 가져오지 못했습니다.'))
    base = Path(folder) / collected['id']
    title, body = parse_article((base/(collected['html_sha256']+'.html')).read_bytes())
    images = {}
    for node in body.find_all('img'):
        link = urljoin(candidate['url'], node.get('src', ''))
        if link in images:
            continue
        if len(images) >= 6 or urlsplit(link).netloc != urlsplit(BOARD).netloc:
            raise ValueError('외부 이미지 또는 이미지가 많은 공고입니다. 원문 파일을 직접 올려주세요.')
        response = fetch(link)
        with PILImage.open(io.BytesIO(response.body)) as im:
            if im.format not in ('PNG','JPEG') or im.width*im.height > 30_000_000:
                raise ValueError('본문 이미지 형식을 확인하지 못했습니다.')
            im.verify()
        images[link] = response.body
    body_data = source_pdf(title, body, candidate['url'], images)
    documents = [dict(name='게시글 본문과 포스터', filename='article.pdf', data=body_data,
                      document_url=candidate['url'], basis='공식 게시글 재구성 PDF · 페이지는 재구성본 기준')]
    warnings = []
    for a in collected['attachments']:
        if a['status'] != 'ok':
            warnings.append('첨부 다운로드 실패: '+a['url']); continue
        try:
            data = (base/a['file']).read_bytes()
            inspect_input(data, a['file'])
        except ValueError:
            warnings.append('자동 분석 불가 첨부: '+a.get('name', '이름 미확인')); continue
        documents.append(dict(name=a['name'], filename=a['file'], data=data,
                              document_url=a['url'], basis='공식 첨부 원본 · 첨부 자체 페이지 기준'))
    return dict(title=title, url=candidate['url'], checked_at=collected['checked_at'],
                documents=documents, attachments=collected['attachments'], warnings=warnings,
                attachment_limit_reached=collected.get('attachment_limit_reached', False),
                body_text=body.get_text(' ', strip=True))
