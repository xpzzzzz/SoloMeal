import {useRef,useState} from 'react';
type Item={id:string;name:string;unit:string;is_staple?:boolean};
type Batch={id:string;name:string;quantity:string;unit:string;version:number;expires_on:string|null;expiry_source:string;location:string;archived:boolean};
const units:Record<string,string>={g:'克',ml:'毫升',piece:'个'};
type API=(path:string,method?:string,body?:unknown,key?:string)=>Promise<any>;
export default function InventoryEditor({items,batches,api,refresh}:{items:Item[];batches:Batch[];api:API;refresh:()=>Promise<void>}){
 const [selected,setSelected]=useState<Batch|null>(null),[quantity,setQuantity]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const [expires,setExpires]=useState(''),[source,setSource]=useState('unknown'),[location,setLocation]=useState('');
 const [archives,setArchives]=useState<Batch[]>([]),[showArchives,setShowArchives]=useState(false);
 const keys=useRef(new Map<string,string>());
 async function mutate(path:string,method:string,body:unknown){const signature=JSON.stringify([path,method,body]);let key=keys.current.get(signature);if(!key){key=crypto.randomUUID();keys.current.set(signature,key);}const value=await api(path,method,body,key);keys.current.delete(signature);return value;}
 async function loadArchives(){setArchives((await api('/inventory?include_archived=true')).filter((b:Batch)=>b.archived));}
 async function perform(fn:()=>Promise<void>){setBusy(true);setNotice('');try{await fn();await refresh();if(showArchives)await loadArchives();}catch(e){setNotice(e instanceof Error?e.message:'操作失败');}finally{setBusy(false);}}
 function select(batch:Batch|null){setSelected(batch);setQuantity(batch?.quantity||'');setExpires(batch?.expires_on||'');setSource(batch?.expiry_source||'unknown');setLocation(batch?.location||'');}
 return <details className="panel"><summary>盘点、编辑与归档批次</summary>
 <p>盘点填写实际剩余数量。归档保留数量与历史，并停止用于推荐和做饭；恢复后重新参与数量及日期检查。</p>
 <form onSubmit={e=>{e.preventDefault();if(selected)void perform(async()=>{await mutate('/inventory/'+selected.id,'PATCH',{quantity,location,expires_on:expires||null,expiry_source:expires?source:'unknown',expected_version:selected.version});select(null);setNotice('批次已保存');});}}>
 <label>需要编辑的批次<select value={selected?.id||''} required disabled={busy} onChange={e=>select(batches.find(b=>b.id===e.target.value)||null)}><option value="">请选择批次</option>{batches.map(b=><option key={b.id} value={b.id}>{b.name} · {Number(b.quantity)} {units[b.unit]} · {b.expires_on||'日期未知'} · {b.id.slice(0,6)}</option>)}</select></label>
 <label>实际剩余数量（{selected?units[selected.unit]:'规范单位'}）<input required type="number" min="0" step={selected?.unit==='piece'?'1':'0.001'} value={quantity} onChange={e=>setQuantity(e.target.value)}/></label>
 <div className="row"><label>到期日期<input type="date" value={expires} onChange={e=>{setExpires(e.target.value);if(source==='unknown')setSource('user');}}/></label><label>日期来源<select disabled={!expires} value={expires?source:'unknown'} onChange={e=>setSource(e.target.value)}><option value="unknown" disabled>日期未知</option><option value="user">自行填写</option><option value="package">包装标注</option><option value="estimate">估计</option></select></label></div>
 <label>存放位置<input required maxLength={40} value={location} onChange={e=>setLocation(e.target.value)}/></label>
 <div className="row"><button disabled={busy||!selected}>保存批次</button><button type="button" className="secondary" disabled={busy||!selected} onClick={()=>{if(selected&&window.confirm('归档此批次？保留数量和历史，归档期间不参与做饭。'))void perform(async()=>{await mutate('/inventory/'+selected.id+'/archive','POST',{expected_version:selected.version,archived:true});select(null);setNotice('批次已归档');});}}>归档批次</button></div>
 </form>
 <button type="button" className="text-button" disabled={busy} onClick={()=>void perform(async()=>{await loadArchives();setShowArchives(!showArchives);})}>{showArchives?'收起归档批次':'查看归档批次'}</button>
 {showArchives&&<div>{archives.length===0?<p>没有归档批次。</p>:archives.map(b=><div className="history-row" key={b.id}><span>{b.name} · {Number(b.quantity)} {units[b.unit]} · {b.expires_on||'日期未知'}</span><button className="secondary" disabled={busy} onClick={()=>void perform(async()=>{await mutate('/inventory/'+b.id+'/archive','POST',{expected_version:b.version,archived:false});setNotice('批次已恢复');})}>恢复批次</button></div>)}<small>撤销用餐会恢复原批次数量；已归档的批次仍保持归档。</small></div>}
 <h3>常备食材</h3><p>常备标记仅用于整理，做饭仍需实际库存。</p>{items.map(item=><label key={item.id} style={{display:'flex',alignItems:'center',gap:8}}><input style={{width:'auto'}} type="checkbox" disabled={busy} checked={!!item.is_staple} onChange={e=>void perform(async()=>{await mutate('/ingredients/'+item.id,'PATCH',{is_staple:e.target.checked});})}/>{item.name}</label>)}{notice&&<p role="status">{notice}</p>}</details>;
}
