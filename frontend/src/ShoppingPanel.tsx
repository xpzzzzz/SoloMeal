import React, {useEffect, useRef, useState} from 'react';

type Api=(path:string,method?:string,body?:unknown,key?:string)=>Promise<any>;
type Ingredient={id:string;name:string;unit:string};
const units:Record<string,string>={g:'克',kg:'千克',ml:'毫升',l:'升',piece:'个'};

export default function ShoppingPanel({api,items,onChanged}:{api:Api;items:Ingredient[];onChanged:()=>Promise<void>}){
 const [quotes,setQuotes]=useState<any[]>([]),[lists,setLists]=useState<any[]>([]);
 const [busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const [selected,setSelected]=useState('');
 const keys=useRef(new Map<string,string>());
 async function load(){const [q,s]=await Promise.all([api('/quotes'),api('/shopping')]);setQuotes(q);setLists(s);}
 async function run(action:()=>Promise<void>){setBusy(true);setNotice('');try{await action();}catch(e){setNotice(e instanceof Error?e.message:'请求失败，请重试');}finally{setBusy(false);}}
 async function write(path:string,body:unknown){const sig=JSON.stringify([path,body]);let key=keys.current.get(sig);if(!key){key=crypto.randomUUID();keys.current.set(sig,key);}const result=await api(path,'POST',body,key);keys.current.delete(sig);return result;}
 useEffect(()=>{void run(load);},[]);
 const quote=quotes.find(q=>q.ingredient_id===selected);
 return <><p role="status">{notice}</p><button className="secondary" disabled={busy} onClick={()=>void run(load)}>刷新报价与采购</button>
 <section className="panel"><h2>包装报价</h2><p>保存人民币估价供推荐使用，超过30天标为过期。数量按食材单位填写；报价不会增加库存。</p>
 <label>食材<select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">请选择</option>{items.map(i=><option key={i.id} value={i.id}>{i.name}（{units[i.unit]}）</option>)}</select></label>
 {selected&&<form key={selected} onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);void run(async()=>{await write('/quotes',{ingredient_id:selected,expected_version:quote?.version||0,package_quantity:f.get('quantity'),package_price:f.get('price'),source:f.get('source'),observed_on:f.get('date'),currency:'CNY'});await load();setNotice('报价已保存，重新生成推荐即可使用。');});}}>
 <div className="row"><label>每包装数量（{units[items.find(i=>i.id===selected)?.unit||'']}）<input name="quantity" required type="number" min="0.001" step="0.001" defaultValue={quote?.package_quantity}/></label><label>每包装价格（元）<input name="price" required type="number" min="0" step="0.01" defaultValue={quote?.package_price}/></label></div>
 <label>报价来源<input name="source" required maxLength={80} defaultValue={quote?.source||'手动记录'}/></label><label>观察日期<input name="date" required type="date" defaultValue={quote?.observed_on}/></label><button disabled={busy}>保存报价</button></form>}
 {quotes.map(q=><p key={q.id}>{q.name} · {Number(q.package_quantity)} {units[q.unit]} / 包 · ¥{q.package_price} · {q.source} · {q.observed_on} · {q.price_status==='stale'?'报价已过期':'估计价格'}</p>)}</section>
 <section className="panel"><h2>采购草稿与记录</h2><p>在菜谱页保存方案后，点击“准备采购”。修改后先保存草稿，再确认实际购买并入库。确认后需按最新库存更新原方案。</p>
 {!lists.length&&<p className="muted">还没有采购清单。</p>}
 {lists.map(list=><PurchaseEditor key={list.id+':'+list.version} list={list} busy={busy} onSave={lines=>run(async()=>{await write('/shopping/'+list.id+'/edit',{expected_version:list.version,items:lines});await load();setNotice('草稿已保存，尚未入库。');})} onAction={action=>run(async()=>{await write('/shopping/'+list.id+'/'+action,{expected_version:list.version});await load();await onChanged();setNotice(action==='confirm'?'整单已入库。请到菜谱页按当前库存更新方案。':'采购已取消。');})}/>)}</section></>;
}

function PurchaseEditor({list,busy,onSave,onAction}:{list:any;busy:boolean;onSave:(lines:any[])=>Promise<void>;onAction:(action:string)=>Promise<void>}){
 const [lines,setLines]=useState<any[]>(list.items);
 const [dirty,setDirty]=useState(false),[confirming,setConfirming]=useState(false);
 function edit(index:number,field:string,value:string){setDirty(true);setConfirming(false);setLines(lines.map((line,n)=>n===index?{...line,[field]:value}:line));}
 return <section className="panel"><h3>{list.origin.recipe_name} · 采购版本 {list.version}</h3><p>{list.status==='draft'?'草稿 · 未入库':list.status==='completed'?'已购买入库':'已取消'} · {list.origin.budget===null?'未设置补购预算':'补购预算 ¥'+list.origin.budget}</p>
 <details><summary>原方案缺料与估价</summary>{list.origin.shopping.map((i:any)=><p key={i.ingredient_id}>{i.name} · 缺 {Number(i.missing_quantity)} {units[i.unit]} · {i.estimated_cost===null?'价格未知或过期':'估计 ¥'+i.estimated_cost} · {i.source||'无报价来源'} {i.observed_on||''}</p>)}</details>
 <form onSubmit={e=>{e.preventDefault();void onSave(lines.map(({name,...line})=>({...line,expires_on:line.expires_on||null,expiry_source:line.expires_on?line.expiry_source:'unknown',actual_cost:line.actual_cost===''?null:line.actual_cost})));}}>
 <fieldset disabled={busy||list.status!=='draft'}>{lines.map((line,n)=><div className="purchase-line" key={line.ingredient_id}><h4>{line.name}</h4><div className="row"><label>实际购买量（{units[line.unit]}）<input required type="number" min={line.unit==='piece'?'1':'0.001'} step={line.unit==='piece'?'1':'0.001'} value={line.quantity} onChange={e=>edit(n,'quantity',e.target.value)}/></label><label>本项实际总价（元，可留空）<input type="number" min="0" step="0.01" value={line.actual_cost??''} onChange={e=>edit(n,'actual_cost',e.target.value)}/></label></div>
 <div className="row"><label>存放位置<input required maxLength={40} value={line.location} onChange={e=>edit(n,'location',e.target.value)}/></label><label>到期日期<input type="date" value={line.expires_on||''} onChange={e=>{setDirty(true);setConfirming(false);setLines(lines.map((v,i)=>i===n?{...v,expires_on:e.target.value||null,expiry_source:e.target.value?'user':'unknown'}:v));}}/></label><label>日期来源<select disabled={!line.expires_on} value={line.expiry_source} onChange={e=>edit(n,'expiry_source',e.target.value)}><option value="unknown">未知</option><option value="user">用户填写</option><option value="package">包装标注</option><option value="estimate">估计</option></select></label></div>
 {list.status==='draft'&&<button type="button" className="text-button" disabled={lines.length===1} onClick={()=>{setDirty(true);setConfirming(false);setLines(lines.filter((_,i)=>i!==n));}}>不购买此项</button>}</div>)}</fieldset>
 {list.status==='draft'&&<div className="row"><button disabled={busy||!dirty}>保存采购修改</button><button type="button" className="secondary" disabled={busy} onClick={()=>void onAction('cancel')}>取消采购</button><button type="button" disabled={busy||dirty} onClick={()=>setConfirming(true)}>核对并入库</button></div>}</form>
 {dirty&&<p>有未保存的修改，请先保存。</p>}{confirming&&<div role="group" aria-label="采购确认"><p>确认以上食材、实际数量和金额均已核对？整单将新增 {lines.length} 个库存批次。</p><button disabled={busy} onClick={()=>void onAction('confirm')}>确认已购买并整单入库</button><button className="secondary" disabled={busy} onClick={()=>setConfirming(false)}>返回核对</button></div>}</section>;
}
