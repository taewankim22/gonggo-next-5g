// IndexedDB is scoped to this browser and origin, not shared across visitors.
// Only the Python allowlisted payload reaches this component; no DOM input scraping.
const processed = new Map();
let knownRevision;
let queue=Promise.resolve();
function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('gonggo-next-drafts', 1);
    req.onupgradeneeded = () => req.result.createObjectStore('drafts');
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function transaction(op, payload, revision, digest) {
  const db = await openDB();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction('drafts', op === 'load' ? 'readonly' : 'readwrite');
      const store = tx.objectStore('drafts');
      const req = store.get('current');
      let result;
      req.onsuccess=()=>{
        const existing=req.result;
        const current=existing?._revision || 0;
        if(op==='load'){result={payload:existing || null,revision:current};return;}
        if(op==='save' && existing?._digest===digest){result={status:'saved',revision:current};return;}
        if(current !== (revision || 0)){result={status:'conflict',revision:current};return;}
        if(op==='delete'){
          store.delete('current');store.delete('legacy-v1-backup');
          result={status:'deleted',revision:0};return;
        }
        if(existing?.version===1)store.put(existing,'legacy-v1-backup');
        store.put({...payload,_revision:current+1,_digest:digest},'current');
        result={status:'saved',revision:current+1};
      };
      tx.oncomplete = () => resolve(result);
      tx.onerror = tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}
export default function(component) {
  const {data, key, parentElement, setStateValue} = component;
  if (data.op === 'idle') return;
  const label=parentElement.querySelector('[role="status"]');
  const signature=data.op+':'+(data.digest || '');
  if (processed.get(key)?.signature === signature) {
    label.textContent=processed.get(key).message;
    return;
  }
  label.textContent=data.op === 'load' ? '저장한 내용 확인 중…' : '이 브라우저에 저장 중…';
  processed.set(key,{signature,message:label.textContent});
  queue=queue.then(()=>transaction(data.op,data.payload,knownRevision ?? data.revision,data.digest)).then(value=>{
    if(value?.status!=='conflict' && value?.revision!==undefined) knownRevision=value.revision;
    const message=value?.status==='conflict' ? '다른 탭의 변경을 보호하기 위해 저장을 중지했습니다.' : data.op === 'save' ? '이 브라우저에 저장 완료 · API 키 제외'
      : data.op === 'delete' ? '저장한 준비 내용을 삭제했습니다.' : '';
    processed.set(key,{signature,message});
    label.textContent=message;
    if (data.op === 'load') setStateValue('loaded',value);
    else setStateValue('saved',{digest:data.digest,...value});
  }).catch(()=>{
    const message='브라우저 저장에 실패했습니다. 준비 목록을 내려받고 저장 허용·남은 공간을 확인하세요.';
    label.textContent=message;
    processed.set(key,{signature,message});
    if (data.op === 'load') setStateValue('loaded',{error:true});
    else setStateValue('saved',{status:'error',digest:data.digest});
  });
}
