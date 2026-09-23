import {useEffect,useRef,useState} from 'react';
import {SessionChangedError} from './session';

const units:Record<string,string>={g:'克',ml:'毫升',piece:'个'};
export default function CombinedShoppingPanel({api,basket,onBasket,budget,onBudget,operation,saving,onSave}:{
 api:(path:string,method?:string,body?:unknown,key?:string)=>Promise<any>;
 basket:any[];onBasket:(rows:any[])=>void;budget:string;onBudget:(value:string)=>void;
 operation:any;saving:boolean;onSave:(body?:unknown)=>Promise<void>;
}){
 const [preview,setPreview]=useState<any>(null);
 const [working,setBusy]=useState(false),[notice,setNotice]=useState('');
 const busy=working||saving;
 const alive=useRef(true);
 const signature=JSON.stringify(basket);
 const current=useRef('');current.current=signature+budget;
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{setPreview(null);},[signature,budget]);
 async function run(action:()=>Promise<void>){setBusy(true);setNotice('');try{await action();}catch(e){if(alive.current&&!(e instanceof SessionChangedError))setNotice(e instanceof Error?e.message:'请求失败');}finally{if(alive.current)setBusy(false);}}
 const request=()=>({recipes:basket.map(({name,...row})=>row),budget:budget||null});
 async function calculate(){const started=current.current;const data=await api('/shopping/combined-preview','POST',request());if(alive.current&&started===current.current)setPreview(data);}
 async function save(){await onSave(operation?undefined:{...request(),signature:preview.signature});if(alive.current)setPreview(null);}
 return <section className="panel combination-panel"><h2>多菜采购组合</h2><p>在菜谱或推荐卡片点“加入采购组合”。合并用量后只扣一次有效库存，保存清单不预留库存。</p>
 {operation&&<div role="status"><p>上次保存结果待确认。重试会恢复同一张清单，不会重复创建；确认结果前暂不能修改组合。</p><button disabled={busy} onClick={()=>void run(save)}>{saving?'正在确认保存…':'重试保存组合清单'}</button></div>}
 {basket.length===0?<p>还没有选菜，可加入1～10道不同菜谱。</p>:<><fieldset disabled={busy||!!operation}>{basket.map((r,n)=><div className="combination-row" key={r.recipe_id}><h3>{r.name}</h3><label>人数 · {r.name}<input id={'combination-'+r.recipe_id} type="number" min="1" max="10" step="1" value={r.servings} onChange={e=>onBasket(basket.map((v,i)=>i===n?{...v,servings:Number(e.target.value)}:v))}/></label><label>使用可选配料 · {r.name}<input type="checkbox" checked={r.include_optional} onChange={e=>onBasket(basket.map((v,i)=>i===n?{...v,include_optional:e.target.checked}:v))}/></label><button className="text-button" onClick={()=>onBasket(basket.filter((_,i)=>i!==n))}>移出组合</button></div>)}<label>组合预算（元，可留空）<input type="number" min="0" step="0.01" value={budget} onChange={e=>onBudget(e.target.value)}/></label><button onClick={()=>void run(calculate)}>{busy?'处理中…':'计算采购'}</button></fieldset>
 <p>菜谱已修改时，请移出该菜后重新加入，再计算采购。</p></>}
 {notice&&<p role="status">{notice}</p>}
 {preview&&<div className="combined-preview"><h3>合并采购预览</h3>{preview.lines.map((line:any)=><div key={line.ingredient_id}><h4>{line.name}</h4><p>总需求 {Number(line.required_quantity)} {units[line.unit]} · 有效库存 {Number(line.available_quantity)} · 缺口 {Number(line.missing_quantity)}</p><p>{line.contributions.map((c:any)=>c.name+'：'+Number(c.quantity)+units[line.unit]).join('；')}</p>{Number(line.missing_quantity)>0&&<p>{line.packages===null?'价格未知或报价过期':`购买${line.packages}包，共${Number(line.purchase_quantity)}${units[line.unit]}，估价 ¥${line.estimated_cost}`} · {line.source||'暂无报价'} {line.observed_on||''}</p>}</div>)}<p>{preview.price_complete?'合计估价':'估价不完整，已知费用下界'} ¥{preview.known_purchase_cost}{preview.budget_status==='exceeded'?' · 已知费用已超预算':preview.budget_status==='unknown'?' · 无法判断预算是否足够':''}</p><button disabled={busy||!!operation||!preview.lines.some((l:any)=>Number(l.missing_quantity)>0)} onClick={()=>void run(save)}>保存组合采购清单</button><p>库存或报价变化后需重新计算。清单保存后，到采购记录勾选已买、核对实际数量并显式确认入库。</p></div>}
 </section>;
}
