"""Validate original document/image inputs without silent format conversion."""
import io
import zipfile
from pathlib import Path
import olefile
from PIL import Image, UnidentifiedImageError
from core import read_pdf

def inspect_hangul(data, ext):
    if ext == '.hwp':
        try:
            with olefile.OleFileIO(io.BytesIO(data)) as document:
                header = document.openstream('FileHeader').read(256)
                if len(header) != 256 or not header.startswith(b'HWP Document File\x00'):
                    raise ValueError('올바른 HWP 5.x 파일이 아닙니다. 한글에서 PDF로 저장해 올려주세요.')
                flags = int.from_bytes(header[36:40], 'little')
                if flags & 6:
                    raise ValueError('암호 또는 배포용 보호가 설정된 HWP입니다. 열람 권한이 있는 원문을 PDF로 저장해 올려주세요.')
                if not document.exists('DocInfo') or not document.exists('BodyText/Section0'):
                    raise ValueError('HWP 본문을 찾을 수 없습니다. 한글에서 파일을 확인해주세요.')
        except OSError:
            raise ValueError('손상되었거나 지원하지 않는 HWP입니다. 한글에서 PDF로 저장해 올려주세요.') from None
        mime = 'application/x-hwp'
    else:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as document:
                entries = document.infolist()
                if len(entries) > 2000 or sum(e.file_size for e in entries) > 64*1024*1024:
                    raise ValueError('HWPX 내부 문서가 너무 큽니다. 필요한 공고 페이지만 PDF로 저장해 올려주세요.')
                if any(e.flag_bits & 1 for e in entries):
                    raise ValueError('암호화된 HWPX는 지원하지 않습니다. 열람 가능한 PDF를 올려주세요.')
                names = document.namelist()
                if len(names) != len(set(names)) or not {'mimetype','Contents/header.xml','Contents/section0.xml','Contents/content.hpf'}.issubset(names):
                    raise ValueError('올바른 HWPX 문서 구조가 아닙니다.')
                if document.read('mimetype').strip() != b'application/hwp+zip':
                    raise ValueError('확장자와 실제 HWPX 형식이 다릅니다.')
                if document.testzip() is not None:
                    raise ValueError('손상된 HWPX 파일입니다.')
        except (zipfile.BadZipFile, KeyError, RuntimeError, NotImplementedError):
            raise ValueError('손상되었거나 지원하지 않는 HWPX입니다. 한글에서 PDF로 저장해 올려주세요.') from None
        mime = 'application/vnd.hancom.hwpx'
    # Local text/sections are not page evidence. Only the provider's Parse pages are used.
    return {'mime':mime, 'pages':[], 'kind':'hangul'}

def inspect_input(data, filename):
    if not data or len(data)>15*1024*1024:
        raise ValueError('비어 있지 않은 15MB 이하 파일을 사용해주세요.')
    ext=Path(filename).suffix.lower()
    if ext=='.pdf':
        return {'mime':'application/pdf','pages':read_pdf(data),'kind':'pdf'}
    if ext in ('.hwp','.hwpx'):
        return inspect_hangul(data,ext)
    if ext not in ('.jpg','.jpeg','.png'):
        raise ValueError('PDF, HWP, HWPX, JPG, JPEG, PNG 파일을 사용해주세요.')
    try:
        with Image.open(io.BytesIO(data)) as im:
            expected='PNG' if ext=='.png' else 'JPEG'
            if im.format!=expected:raise ValueError('확장자와 실제 이미지 형식이 다릅니다.')
            w,h=im.size
            if min(w,h)<200 or w*h>30_000_000:
                raise ValueError('이미지는 가로·세로 200px 이상, 총 3천만 화소 이하로 올려주세요.')
            im.verify()
        with Image.open(io.BytesIO(data)) as im:im.load()
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as exc:
        raise ValueError('손상되었거나 읽을 수 없는 이미지입니다.') from None
    return {'mime':'image/png' if expected=='PNG' else 'image/jpeg','pages':[], 'kind':'image','width':w,'height':h}

def parse_pages(steps):
    """Use only actual Parse response elements, never Extract-generated quotes."""
    import json
    pages={}
    for step in steps:
        if 'parse' not in str(step.get('model','')).lower():continue
        for content in step.get('content',[]):
            candidates=[content.get('text'),content.get('additional_values')]
            for value in candidates:
                if isinstance(value,str):
                    try:value=json.loads(value)
                    except ValueError:continue
                if not isinstance(value,dict):continue
                for element in value.get('elements',[]):
                    page=int(element.get('page',1))
                    c=element.get('content',{})
                    text=c.get('text','') or c.get('markdown','')
                    if not text:
                        from html import unescape
                        import re
                        text=unescape(re.sub('<[^>]+>',' ',c.get('html','')))
                    if text:pages.setdefault(page,[]).append(text)
    return ['\n'.join(pages.get(i,[])) for i in range(1,max(pages,default=0)+1)]

def map_image_page(notice,info):
    """Single original image is one page; this is file metadata, not AI extraction."""
    result=dict(notice)
    if info.get('kind')=='image':
        for key in ('eligibility','preference','commitment','documents','schedule'):
            if result.get(key+'_quote') and not result.get(key+'_page'):
                result[key+'_page']='1'
    return result
