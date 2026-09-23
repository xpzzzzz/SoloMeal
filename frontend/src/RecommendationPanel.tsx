import {useEffect,useRef,useState} from 'react';
import {SessionChangedError} from './session';
import {timeLabel} from './personalTime';

type Weights={inventory:number;expiry:number;repetition:number;purchase_cost:number};
const PRESETS:Record<string,{label:string;weights:Weights}>={
 default:{label:'默认',weights:{inventory:60,expiry:40,repetition:10,purchase_cost:0}},
 clear_fridge:{label:'清冰箱',weights:{inventory:40,expiry:80,repetition:10,purchase_cost:0}},
 quick:{label:'快速做',weights:{inventory:60,expiry:40,repetition:10,purchase_cost:0}},
 less_shopping:{label:'少买东西',weights:{inventory:100,expiry:20,repetition:10,purchase_cost:0}},
 variety:{label:'换换口味',weights:{inventory:60,expiry:40,repetition:30,purchase_cost:0}},
};
const rejectionLabels:Record<string,string>={TIME_LIMIT:'超出用时上限',MISSING_EQUIPMENT:'缺少厨具',EXCLUDED_INGREDIENT:'含排除食材',BUDGET_EXCEEDED:'已知补购费用超预算'};
const units:Record<string,string>={g:'克',ml:'毫升',piece:'个'};
export default function RecommendationPanel({api,result,onResult,preferenceText,onCook,onAdd,onSave,onSettings,onDiscover,favorites,onFavorite}:{
 api:(path:string,method?:string,body?:unknown)=>Promise<any>;result:any;onResult:(value:any)=>void;
 preferenceText:(candidate:any)=>string;onCook:(candidate:any)=>void;onAdd:(candidate:any)=>void;
 onSave:(candidate:any,request:any)=>Promise<void>;onSettings:()=>void;onDiscover:(constraints:any)=>void;
 favorites?:Record<string,{favorite?:boolean;rating?:string}>;
 onFavorite?:(candidate:any,next:{favorite:boolean;rating:'neutral'|'like'|'dislike'})=>Promise<unknown>;
}){
 const initial=result?.request||{};
 const [scenario,setScenario]=useState(initial.scenario||'default');
 const [weights,setWeights]=useState<Weights>(initial.score_weights||PRESETS.default.weights);
 const [minutes,setMinutes]=useState<number|null>(result&&'manualMinutes' in result?result.manualMinutes:initial.max_minutes??null);
 const [normalMinutes,setNormalMinutes]=useState<number|null>(null);
 const [budget,setBudget]=useState(initial.budget||'');
 const [optional,setOptional]=useState(initial.include_optional||false);
 const [extra]=useState(()=>Object.fromEntries(['servings','equipment','excluded_ingredients'].filter(k=>initial[k]!==undefined).map(k=>[k,initial[k]])));
 const skipped:string[]=result?.skipped||[];
 const setSkipped=(ids:string[])=>onResult({...result,skipped:ids});
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const alive=useRef(true);
 useEffect(()=>{alive.current=true;api('/me/preferences').then(p=>{if(alive.current)setNormalMinutes(p.max_minutes);}).catch(e=>{if(alive.current&&!(e instanceof SessionChangedError))setError(e.message);});return()=>{alive.current=false;};},[]);
 const baseMinutes=minutes??normalMinutes;
 // An unloaded preference is unknown, not a 20-minute allowance. Null lets the
 // server apply the saved limit before the quick-scene cap, even during a slow GET.
 const effectiveMinutes=baseMinutes===null?null:scenario==='quick'?Math.min(baseMinutes,20):baseMinutes;
 const candidates=result?.candidates||[];
 const remaining=candidates.filter((c:any)=>!skipped.includes(c.recipe.id));
 const visible=remaining.slice(0,3);
 function changed(){onResult(null);setError('');}
 function selectScenario(value:string){changed();setScenario(value);if(PRESETS[value])setWeights(PRESETS[value].weights);if(value==='default')setMinutes(null);}
 async function run(action:()=>Promise<void>){setBusy(true);setError('');try{await action();}catch(e){if(alive.current&&!(e instanceof SessionChangedError))setError(e instanceof Error?e.message:'请求失败，请重试');}finally{if(alive.current)setBusy(false);}}
 async function recommend(){
  if(effectiveMinutes!==null&&(!Number.isInteger(effectiveMinutes)||effectiveMinutes<1||effectiveMinutes>480))throw new Error('用时上限须为1至480的整数');
  const request={...extra,scenario,score_weights:weights,max_minutes:effectiveMinutes,include_optional:optional,budget:budget||null};
  const data=await api('/recommendations','POST',request);
  if(alive.current){onResult({...data,request,manualMinutes:minutes});}
 }
 const discovery=()=>onDiscover(result?.constraints||{...extra,max_minutes:effectiveMinutes});
 return <section className="panel recommendation-panel"><h2>用现有食材安排一餐</h2>
 <p className="muted">场景只调整本次推荐，不修改厨房偏好；推荐、换菜都不扣库存。</p>
 <fieldset disabled={busy} className="recommendation-controls">
 <label>推荐场景<select value={scenario} onChange={e=>selectScenario(e.target.value)}>{Object.entries(PRESETS).map(([key,p])=><option value={key} key={key}>{p.label}</option>)}<option value="custom">自定义</option></select></label>
 <label>本次用时上限（分钟）<input type="number" min="1" max="480" step="1" value={effectiveMinutes??''} placeholder="使用厨房偏好" onChange={e=>{changed();setScenario('custom');setMinutes(e.target.value===''?null:Number(e.target.value));}}/></label>
 {scenario==='quick'&&<small>最多20分钟；切换其他场景会恢复手动基线或厨房偏好的用时。</small>}
 {scenario==='less_shopping'&&<p>优先少缺几种食材，不代表价格最低。</p>}
 <label>本次补购预算（元，可留空）<input type="number" min="0" step="0.01" value={budget} onChange={e=>{changed();setScenario('custom');setBudget(e.target.value);}}/></label>
 <label>本餐使用可选配料<input type="checkbox" checked={optional} onChange={e=>{changed();setScenario('custom');setOptional(e.target.checked);}}/></label>
 <details><summary>推荐评分权重</summary><p>厨具、忌口、数量和预算检查始终有效。成本权重启用时，未知价格排在完整报价之后。</p>{(Object.keys(weights) as (keyof Weights)[]).map(k=><label key={k}>{{inventory:'库存覆盖',expiry:'临期优先',repetition:'近期重复惩罚',purchase_cost:'每元补购成本惩罚'}[k]}<input type="number" min="0" max="100" step="1" value={weights[k]} onChange={e=>{changed();setScenario('custom');setWeights({...weights,[k]:Number(e.target.value)});}}/></label>)}</details>
 <button onClick={()=>void run(recommend)}>{busy?'处理中…':'生成本餐推荐'}</button>{result&&<button className="secondary" onClick={()=>void run(recommend)}>重新推荐</button>}
 </fieldset>
 {error&&<p role="alert">{error}</p>}
 {result&&<>
 <p className="preference-explanation"><b>{result.personalization?.enabled?'个性化排序已开启':'个性化排序已关闭'}</b>{result.personalization?.history_count?` · 基于最近${result.personalization.history_count}次完成记录`:' · 偏好仍在积累'}</p>
 {candidates.length===0?<div><p>没有符合条件的菜谱，请核对厨具、用时与忌口设置。</p><ul>{Object.entries(result.rejection_counts||{}).filter(([,n])=>Number(n)>0).map(([code,n])=><li key={code}>{rejectionLabels[code]||code}：{String(n)}道</li>)}</ul><p className="muted">同一道菜可能有多个排除原因，以上数量不可相加为菜谱总数。</p><button className="secondary" onClick={onSettings}>调整厨房偏好</button><button className="secondary" onClick={discovery}>发现菜谱</button></div>:
 visible.length===0?<div role="status"><p>本次候选已看完</p><button disabled={busy} onClick={()=>setSkipped([])}>重置本次候选</button><button className="secondary" onClick={onSettings}>调整条件</button><button className="secondary" onClick={discovery}>发现菜谱</button></div>:<>
 <h3>本次推荐依据</h3>
 {visible.map((c:any)=><article className="history-row recommendation-card" key={c.recipe.id}><div><h3>{c.recipe.name} · {c.servings} 人份</h3>
 <p className="time-estimate">{timeLabel(c.time_estimate)}</p>
 <p>食材满足度 {Math.round(c.score_components.inventory_coverage*100)}% · 按食材行比例计算</p>
 <p>{c.can_cook_now?'现有库存足够，无需采购':`需采购${c.missing_ingredient_count??c.shopping.length}种食材：`+c.shopping.map((i:any)=>i.name+' '+Number(i.missing_quantity)+units[i.unit]).join('；')}</p>
 {c.shopping.length>0&&<p>{c.price_complete?'补购估计 ¥'+c.known_purchase_cost:Number(c.known_purchase_cost)>0?'估价不完整，已知部分 ¥'+c.known_purchase_cost:'价格未知 / 估价不完整'}</p>}
 <ul className="preference-explanation"><li>{c.recipe.name}：{preferenceText(c)}</li><li>{scenario==='less_shopping'?`缺口共${c.shopping.length}种，优先减少采购种类`:c.score_components.expiry_coverage>0?`可使用临期食材，临期满足度${Math.round(c.score_components.expiry_coverage*100)}%`:c.can_cook_now?'当前食材已满足本餐用量':`最近7天完成过${c.score_components.recent_repetitions}次，已按重复惩罚参与排序`}</li></ul>
 </div><div className="row"><button className="secondary" disabled={busy} onClick={()=>onAdd(c)}>加入采购组合</button><button disabled={busy} onClick={()=>onCook(c)}>开始做饭</button><button disabled={busy} onClick={()=>void run(()=>onSave(c,result.request))}>保存这餐方案</button><button className="secondary" disabled={busy} onClick={()=>setSkipped([...skipped,c.recipe.id])}>换一道</button>{onFavorite&&<button className={favorites?.[c.recipe.id]?.favorite?'chosen':'secondary'} aria-pressed={!!favorites?.[c.recipe.id]?.favorite} disabled={busy} onClick={()=>void run(async()=>{await onFavorite(c,{favorite:!favorites?.[c.recipe.id]?.favorite,rating:(favorites?.[c.recipe.id]?.rating as 'neutral'|'like'|'dislike')||'neutral'});})}>{favorites?.[c.recipe.id]?.favorite?'已收藏':'收藏'}</button>}</div></article>)}
 <p>显示{visible.length}道，本次还有{Math.max(0,remaining.length-visible.length)}道未显示。</p>
 </>}
 {candidates.length>0&&candidates.length<3&&<button className="secondary" onClick={discovery}>当前有 {candidates.length} 道符合条件的菜谱，发现更多</button>}
 <small>推荐不预留库存；记录做饭时会再次检查实际数量。</small>
 </>}
 </section>;
}
