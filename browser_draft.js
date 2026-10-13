// IndexedDB is scoped to this browser and origin, not shared across visitors.
// Only the Python allowlisted payload reaches this component; no DOM input scraping.
const processed = new Map();
function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('gonggo-next-drafts', 1);
    req.onupgradeneeded = () => req.result.createObjectStore('drafts');
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function transaction(op, payload) {
  const db = await openDB();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction('drafts', op === 'load' ? 'readonly' : 'readwrite');
      const store = tx.objectStore('drafts');
      const req = op === 'load' ? store.get('current') : op === 'delete'
        ? store.delete('current') : store.put(payload, 'current');
      tx.oncomplete = () => resolve(req.result);
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
  transaction(data.op,data.payload).then(value=>{
    const message=data.op === 'save' ? '이 브라우저에 저장 완료 · API 키 제외'
      : data.op === 'delete' ? '저장한 준비 내용을 삭제했습니다.' : '';
    processed.set(key,{signature,message});
    label.textContent=message;
    if (data.op === 'load') setStateValue('loaded',{payload:value || null});
    else setStateValue('saved',{digest:data.digest,status:data.op === 'delete' ? 'deleted' : 'saved'});
  }).catch(()=>{
    const message='브라우저 저장에 실패했습니다. 준비 목록을 내려받고 저장 허용·남은 공간을 확인하세요.';
    label.textContent=message;
    processed.set(key,{signature,message});
    if (data.op === 'load') setStateValue('loaded',{error:true});
    else setStateValue('saved',{status:'error',digest:data.digest});
  });
}
