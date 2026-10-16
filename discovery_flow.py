"""User-triggered public collection and sequential analysis; profiles stay local."""
from pathlib import Path
from core import fingerprint
from collect_notices import discover
from live_catalog import LiveCatalog, analyze_public, now_iso
from upstage_client import StudioError
from web_notice import prepare_article, article_url


def refresh_latest(root, connection, limit=3, progress=None, candidates=None, national=False, document_urls=None):
    if not connection or not connection.get('enabled'):
        raise ValueError('실제 AI 분석 모드와 Upstage 연결을 확인해주세요.')
    if not isinstance(limit,int) or not 1<=limit<=100:raise ValueError('분석 묶음 크기를 다시 선택해주세요.')
    def report(text):
        if progress:progress(text)
    report('공식 게시판에서 최신 공고를 가져오는 중…')
    candidates=discover() if candidates is None else candidates
    cache=LiveCatalog(root)
    summary=dict(checked_at=now_iso(),found=len(candidates),selected=min(limit,len(candidates)),
                 analyzed=0,reused=0,failed=0,notices=[])
    config={'agent_id':connection['agent_id'],'config_id':str(connection['version'])}
    for position,candidate in enumerate(candidates[:limit],1):
        report(f'{position}/{summary["selected"]} 공고 · 본문과 첨부를 가져오는 중…')
        from nationwide_notice import source_url,prepare_public_article
        from national_search import DiscoveryStore
        url=candidate['url']
        manifest=dict(url=url,title=candidate['title'],checked_at=now_iso(),config=config,
                      documents=[],warnings=[],complete=False)
        try:
            url=source_url(url) if national else article_url(url)
            manifest['url']=url
            if national:DiscoveryStore(root).attempted(url)
            article=(prepare_public_article if national else prepare_article)(candidate,Path(root)/'runtime/collected')
        except (ValueError,OSError,StudioError) as exc:
            manifest['warnings']=['최신 원문을 가져오지 못했습니다. 이전 분석은 최신 여부 확인이 필요합니다.',str(exc)]
            manifest['fetch_failed']=True
            cache.save_scan(manifest);summary['failed']+=1;summary['notices'].append(manifest)
            continue
        manifest.update(title=article['title'],checked_at=article['checked_at'],warnings=list(article['warnings']),
                        attachments=article.get('attachments',[]),
                        resolved_url=article.get('resolved_url',url))
        if article.get('attachment_limit_reached'):
            manifest['warnings'].append('첨부는 처음 5개까지 수집했습니다. 나머지는 원문에서 확인해주세요.')
        manifest['documents']=[dict(url=d['document_url'],name=d['name'],sha256=fingerprint(d['data']),status='pending')
                               for d in article['documents']]
        # Persist the current inventory before starting any paid call. A changed
        # or unfinished document must not silently reuse an older verdict.
        cache.save_scan(manifest)
        for index,doc in enumerate(manifest['documents']):
            prefix=f'{position}/{summary["selected"]} 공고 · 문서 {index+1}/{len(manifest["documents"])}'
            report(prefix+' · '+doc['name'])
            if document_urls is not None and doc['url'] not in document_urls:
                # A targeted retry must not charge for a different, newly changed file.
                match=next((r for r in cache.records() if r.get('source_url')==url and
                            r.get('document_url')==doc['url'] and r.get('sha256')==doc['sha256'] and r.get('config')==config),None)
                if match:doc.update(status='ready',record_id=match['id'])
                cache.save_scan(manifest)
                continue
            try:
                record,reused=analyze_public(root,article,index,connection['agent_id'],connection['version'],
                    connection['runner'],lambda message:report(prefix+' · '+message))
                doc.update(status='ready',record_id=record['id'])
                summary['reused' if reused else 'analyzed']+=1
            except (ValueError,StudioError) as exc:
                doc.update(status='failed',error=str(exc));summary['failed']+=1
            except OSError:
                doc.update(status='failed',error='문서 저장 오류입니다. 다시 검색하면 완료된 분석을 재사용합니다.')
                summary['failed']+=1
            cache.save_scan(manifest)
        manifest['complete']=not manifest['warnings'] and all(d['status']=='ready' for d in manifest['documents'])
        cache.save_scan(manifest);summary['notices'].append(manifest)
    return summary
