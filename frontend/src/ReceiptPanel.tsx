import {receiptUnitProblem} from './receiptValidation';
import React, {useEffect,useRef,useState} from 'react';

type Api=(path:string,method?:string,body?:unknown,key?:string)=>Promise<any>;
type Ingredient={id:string;name:string;unit:string};
type Line={name:string;quantity:string|null;unit:string|null;amount:string|null;ingredient_id:string|null;uncertain:boolean;excluded:boolean;expires_on?:string|null;expiry_source?:string;location?:string};
const blank=():Line=>({name:'',quantity:null,unit:null,amount:null,ingredient_id:null,uncertain:true,excluded:false});
const units:Record<string,string>={g:'克',kg:'千克',ml:'毫升',l:'升',piece:'个'};

export default function ReceiptPanel({api,items,onChanged}:{api:Api;items:Ingredient[];onChanged:()=>Promise<void>}){
 const [records,setRecords]=useState<any[]>([]),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [feedback,setFeedback]=useState<{id:string;text:string}|null>(null);
 const [capability,setCapability]=useState({vision_enabled:false,daily_limit:10});
 const [file,setFile]=useState<File|null>(null);
 const [preview,setPreview]=useState('');
 const active=useRef(true);
 const uploadKey=useRef(crypto.randomUUID()),keys=useRef(new Map<string,string>());
 async function load(){const [rows,features]=await Promise.all([api('/receipts'),api('/receipts/capabilities')]);setRecords(rows);setCapability(features);}
 async function run(action:()=>Promise<void>,receiptId?:string){setBusy(true);setNotice('');setFeedback(null);try{await action();}catch(e){const text=e instanceof Error?e.message:'请求失败';if(receiptId)setFeedback({id:receiptId,text});else setNotice(text);}finally{setBusy(false);}}
 async function write(path:string,body:unknown){const sig=JSON.stringify([path,body]);let key=keys.current.get(sig);if(!key){key=crypto.randomUUID();keys.current.set(sig,key);}const result=await api(path,'POST',body,key);if(result.parse_status!=='parsing')keys.current.delete(sig);return result;}
 useEffect(()=>{active.current=true;void run(load);return()=>{active.current=false;};},[]);
 useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview);},[preview]);
 return <><p role="status">{notice}</p><section className="panel"><h2>小票草稿</h2><p>上传 PNG 或 JPEG 图片，最多 5 MiB。草稿可以保存、补录和排除非食材；保存后逐项核对，再确认整单入库。</p><p>{capability.vision_enabled?'可选择自动识别：图片将发送给已配置的模型服务，每24小时最多 '+capability.daily_limit+' 次。识别后仍须逐项人工核对。':'自动识别未配置，暂可按原图手工填写。'}数量、单位或金额不明确时请留空，不按包装名称猜测。</p>
 <form onSubmit={e=>{e.preventDefault();if(!file)return;void run(async()=>{if(file.size===0||file.size>5*1024*1024)throw new Error('请选择不超过 5 MiB 的非空图片');const row=await api('/receipts','POST',file,uploadKey.current);uploadKey.current=crypto.randomUUID();await load();setNotice(row.duplicate_of?'发现你曾上传相同文件，请核对已有草稿；当前没有入库。':'小票已私有保存，请补录草稿。');});}}><label>小票图片<input type="file" disabled={busy} accept="image/png,image/jpeg" required onChange={e=>{setFile(e.target.files?.[0]||null);uploadKey.current=crypto.randomUUID();}}/></label><button disabled={busy||!file}>上传小票</button></form>
 <button className="secondary" disabled={busy} onClick={()=>void run(load)}>刷新小票记录</button></section>
 {preview&&<section className="panel"><h2>小票原图</h2><img src={preview} alt="当前核对的小票原图" style={{maxWidth:'100%',maxHeight:600,objectFit:'contain'}}/><button className="secondary" onClick={()=>setPreview('')}>关闭原图</button></section>}
 {records.map(row=><Editor key={row.id+':'+row.version} row={row} feedback={feedback?.id===row.id?feedback?.text:undefined} items={items} busy={busy} visionEnabled={capability.vision_enabled} onPreview={()=>run(async()=>{const image=await api('/receipts/'+row.id+'/file');if(active.current)setPreview(URL.createObjectURL(image));})} onAction={action=>run(async()=>{await write('/receipts/'+row.id+'/'+action,{expected_version:row.version});await load();await onChanged();setNotice(action==='confirm'?'小票已整单入库。':action==='cancel'?'小票已取消。':'识别请求已处理，请查看小票状态并核对；失败时可手工补录。');},row.id)} onSave={draft=>run(async()=>{await write('/receipts/'+row.id+'/edit',{expected_version:row.version,draft});await load();setNotice('小票草稿已保存，库存未改变。');},row.id)}/>)}
 {!records.length&&<p>还没有小票记录。</p>}</>;
}

function Editor({row,feedback,items,busy,onSave,onPreview,onAction,visionEnabled}:{row:any;feedback?:string;items:Ingredient[];busy:boolean;visionEnabled:boolean;onSave:(draft:unknown)=>Promise<void>;onPreview:()=>Promise<void>;onAction:(action:string)=>Promise<void>}){
 const [lines,setLines]=useState<Line[]>(row.draft.items),[date,setDate]=useState(row.draft.purchased_on||''),[dirty,setDirty]=useState(false),[confirming,setConfirming]=useState(false),[recognizing,setRecognizing]=useState(false);
 const problems=lines.map(line=>receiptUnitProblem(line,items));
 function edit(n:number,patch:Partial<Line>){setDirty(true);setConfirming(false);setLines(lines.map((line,i)=>i===n?{...line,...patch}:line));}
 return <section className="panel receipt-editor"><h3>小票 · 版本 {row.version}</h3><small>{row.created_at} · {row.status==='draft'?'草稿，未入库':row.status==='completed'?'已整单入库':'已取消'}</small>
 <button className="secondary" disabled={busy} onClick={()=>void onPreview()}>查看原图</button>
 <p>{row.status!=='draft'?'已保存的核对记录':row.parse_status==='parsed'?'识别结果待人工核对':row.parse_status==='failed'?'识别失败或已中断，请手工补录':row.parse_status==='parsing'?'正在识别；可刷新查看结果，也可手工编辑，迟到结果不会覆盖修改。':row.parse_status==='discarded'?'识别结果已丢弃，请继续手工核对':'等待手工补录'}</p>
 {visionEnabled&&row.status==='draft'&&row.version===1&&!row.parse_started_at&&<><button disabled={busy||dirty} onClick={()=>setRecognizing(true)}>自动识别小票</button>{recognizing&&!dirty&&<div role="group" aria-label="小票识别确认"><p>将把此小票图片发送给已配置的模型服务，可能产生调用费用。每份小票仅尝试一次，失败可手工填写。</p><button disabled={busy} onClick={()=>{setRecognizing(false);void onAction('parse');}}>发送图片并识别</button><button className="secondary" disabled={busy} onClick={()=>setRecognizing(false)}>暂不识别</button></div>}</>}
 <form onSubmit={e=>{e.preventDefault();void onSave({purchased_on:date||null,items:lines});}}><fieldset disabled={busy||row.status!=='draft'}>
 <label>购买日期（不是到期日期）<input type="date" value={date} onChange={e=>{setDate(e.target.value);setDirty(true);setConfirming(false);}}/></label>
 {lines.map((line,n)=><div className="purchase-line" key={n}><h4>第 {n+1} 项{line.excluded?' · 已排除':''}</h4>
 <label>小票名称<input required maxLength={80} value={line.name} onChange={e=>edit(n,{name:e.target.value})}/></label>
 <label>对应食材<select value={line.ingredient_id||''} onChange={e=>edit(n,{ingredient_id:e.target.value||null})}><option value="">待匹配</option>{items.map(i=><option key={i.id} value={i.id}>{i.name}（{units[i.unit]}）</option>)}</select></label>
 <div className="row"><label>数量（未知留空）<input type="number" min="0.001" step="0.001" value={line.quantity??''} onChange={e=>edit(n,{quantity:e.target.value||null})}/></label><label>单位<select aria-label="小票单位" value={line.unit||''} onChange={e=>edit(n,{unit:e.target.value||null})}><option value="">未知</option>{Object.entries(units).map(([v,label])=><option value={v} key={v}>{label}</option>)}</select></label><label>本项金额（元）<input type="number" min="0" step="0.01" value={line.amount??''} onChange={e=>edit(n,{amount:e.target.value||null})}/></label></div>
 <div className="row"><label>存放位置<input required maxLength={40} value={line.location??'fridge'} onChange={e=>edit(n,{location:e.target.value})}/></label><label>到期日期<input type="date" value={line.expires_on||''} onChange={e=>edit(n,{expires_on:e.target.value||null,expiry_source:e.target.value?'user':'unknown'})}/></label><label>日期来源<select disabled={!line.expires_on} value={line.expiry_source??'unknown'} onChange={e=>edit(n,{expiry_source:e.target.value})}><option value="unknown">未知</option><option value="user">用户填写</option><option value="package">包装标注</option><option value="estimate">估计</option></select></label></div>
 {row.status==='draft'&&problems[n]&&<p role="alert">第 {n+1} 项：{problems[n]}</p>}
 <label>仍需核对<input type="checkbox" checked={line.uncertain} onChange={e=>edit(n,{uncertain:e.target.checked})}/></label><label>排除非食材或不入库项<input type="checkbox" checked={line.excluded} onChange={e=>edit(n,{excluded:e.target.checked})}/></label>
 <button type="button" className="text-button" onClick={()=>{setDirty(true);setConfirming(false);setLines(lines.filter((_,i)=>i!==n));}}>删除此行</button></div>)}
 <button className="secondary" type="button" disabled={lines.length>=100} onClick={()=>{setLines([...lines,blank()]);setDirty(true);setConfirming(false);}}>添加小票行</button><button disabled={!dirty}>保存小票草稿</button></fieldset></form>
 {row.status==='draft'&&<div className="row"><button className="secondary" disabled={busy} onClick={()=>void onAction('cancel')}>取消小票</button><button disabled={busy||dirty||problems.some(Boolean)||!lines.some(l=>!l.excluded)||lines.some(l=>!l.excluded&&(l.uncertain||!l.ingredient_id||!l.quantity||!l.unit))} onClick={()=>setConfirming(true)}>核对小票入库</button></div>}
 {confirming&&!dirty&&row.status==='draft'&&<div role="group" aria-label="小票确认"><p>将按以上已保存内容新增 {lines.filter(l=>!l.excluded).length} 个库存批次，排除 {lines.filter(l=>l.excluded).length} 项。请确认食材、数量、单位、日期来源和位置；个数须为整数，购买日期不推断到期日期。</p><button disabled={busy||problems.some(Boolean)} onClick={()=>void onAction('confirm')}>{busy?'正在入库…':'确认小票并整单入库'}</button><button className="secondary" disabled={busy} onClick={()=>setConfirming(false)}>返回核对小票</button></div>}
 {feedback&&<p role="alert">{feedback}</p>}
 {row.status==='draft'&&problems.some(Boolean)&&<p role="status">暂不能整单入库，请先修正上方标出的单位或数量问题，再保存草稿。</p>}
 {row.result&&<p>已新增 {row.result.batches.length} 个库存批次，可到库存页查看。</p>}
 {dirty&&<p>有未保存的修改；刷新或离开页面会丢失这些修改。</p>}
 {row.parsed.items&&<details><summary>原始结构化识别结果</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify(row.parsed,null,2)}</pre></details>}</section>;
}
