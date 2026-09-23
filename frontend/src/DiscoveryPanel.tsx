import React, {useEffect, useRef, useState} from 'react';
import {groupByField,issueText,newIngredientHints} from './draftValidation';
import {COOKING_METHODS,MAX_METHODS,isCookingMethod,methodName,methodsFromStored,toggleMethod} from './cookingMethods';

type Api=(path:string,method?:string,body?:unknown,key?:string)=>Promise<any>;
type Ingredient={id:string;name:string;unit:string};
type Line={name:string;quantity:string;unit:string;optional:boolean};
type Payload={name:string;servings:string;minutes:string;equipment:string[];steps:string[];cooking_methods:string[];ingredients:Line[]};
type Check={payload:Payload;errors:any[];warnings:any[]};
const units:Record<string,string>={g:'克',kg:'千克',ml:'毫升',l:'升',piece:'个'};
const blank=():Line=>({name:'',quantity:'',unit:'g',optional:false});
const words=(value:string)=>value.split(/[,，]/).map(x=>x.trim()).filter(Boolean);
const lines=(value:string)=>value.split('\n').map(x=>x.trim()).filter(Boolean);
const asText=(value:unknown)=>value===null||value===undefined?'':String(value);
const toInt=(value:string)=>{const n=Math.trunc(Number(value));return value.trim()===''||!Number.isFinite(n)?undefined:n;};

function readPayload(stored:any):Payload{
 return {name:asText(stored?.name),servings:asText(stored?.servings),minutes:asText(stored?.minutes),
  equipment:Array.isArray(stored?.equipment)?stored.equipment.map(asText):[],
  steps:Array.isArray(stored?.steps)?stored.steps.map(asText):[],
  cooking_methods:methodsFromStored(stored?.cooking_methods),
  ingredients:Array.isArray(stored?.ingredients)?stored.ingredients.map((l:any)=>({name:asText(l.name),
   quantity:asText(l.quantity),unit:asText(l.unit),optional:l.optional===true})):[]};
}

// One claim key per set of conditions, held until the server answers: a request that never got
// a reply is retried under the same key, so the stored claim cannot spend a second model call,
// while a recorded failure retries only under a new key the user asked for by clicking again.
function claimKey(held:React.MutableRefObject<{sig:string;key:string;spent:boolean}>,sig:string,reuse:boolean){
 if(!reuse||held.current.sig!==sig||held.current.spent)held.current={sig,key:crypto.randomUUID(),spent:false};
 return held.current.key;
}

export default function DiscoveryPanel({api,items,onChanged,onRecommend,seed}:{api:Api;items:Ingredient[];
 onChanged:()=>Promise<void>;onRecommend:(constraints:any)=>Promise<void>;seed?:Record<string,any>|null}){
 const [drafts,setDrafts]=useState<any[]>([]),[batches,setBatches]=useState<any[]>([]);
 const [capability,setCapability]=useState({model_enabled:false,candidates:3,output_tokens:3000,timeout_seconds:60,prompt_version:''});
 const [conditions,setConditions]=useState(()=>({servings:asText(seed?.servings),maxMinutes:asText(seed?.max_minutes),
  equipment:Array.isArray(seed?.equipment)?seed.equipment.join('，'):'',
  excluded:Array.isArray(seed?.excluded_ingredients)?seed.excluded_ingredients.join('，'):'',
  requirement:'',preferInventory:seed?.prefer_inventory!==false}));
 const [busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[failure,setFailure]=useState('');
 const [running,setRunning]=useState(false),[newCall,setNewCall]=useState(false);
 const [checks,setStateChecks]=useState<Record<string,Check|undefined>>({});
 const [added,setAdded]=useState<{batchId:string|null;constraints:any;name:string}|null>(null);
 const edited=useRef(!!seed),claim=useRef<{sig:string;key:string;spent:boolean}>({sig:'',key:crypto.randomUUID(),spent:true}),keys=useRef(new Map<string,string>());
 const edit=(patch:Partial<typeof conditions>)=>{edited.current=true;setConditions(v=>({...v,...patch}));};
 function request(){
  return {servings:toInt(conditions.servings),max_minutes:toInt(conditions.maxMinutes),
   equipment:conditions.equipment.trim()===''?undefined:words(conditions.equipment),
   excluded_ingredients:words(conditions.excluded),requirement:conditions.requirement.trim().slice(0,500),
   prefer_inventory:conditions.preferInventory};
 }
 async function load(){
  const [rows,recent,features,stored]=await Promise.all([api('/recipe-drafts?status=draft'),api('/recipe-discoveries'),
   api('/recipe-discoveries/capabilities'),api('/me/preferences')]);
  // Every batch stays in state: a draft from any earlier batch has to be re-recommended under
  // the conditions it was generated with, so the map cannot be capped to what is displayed.
  setDrafts(rows);setBatches(recent);setCapability(features);setStateChecks({});
  // A preferences read that lands after the user typed must not rewrite the form.
  if(!edited.current)setConditions(v=>({...v,servings:v.servings||asText(stored?.default_servings),
   maxMinutes:v.maxMinutes||asText(stored?.max_minutes),equipment:v.equipment||words(asText(stored?.equipment)).join('，'),
   excluded:v.excluded||words(asText(stored?.excluded_ingredients)).join('，')}));
 }
 async function run(action:()=>Promise<void>){setBusy(true);setNotice('');setFailure('');
  try{await action();}catch(e){setFailure(e instanceof Error?e.message:'请求失败，请重试');}finally{setBusy(false);}}
 async function write(path:string,payload:unknown,method='POST'){
  const sig=JSON.stringify([path,method,payload]);let key=keys.current.get(sig);
  if(!key){key=crypto.randomUUID();keys.current.set(sig,key);}
  const result=await api(path,method,payload,key);keys.current.delete(sig);return result;
 }
 function generate(){
  const body=request(),sig=JSON.stringify(body),key=claimKey(claim,sig,newCall);
  setRunning(true);setNewCall(false);
  void run(async()=>{
   try{
    const batch=await api('/recipe-discoveries','POST',body,key);
    claim.current={sig,key,spent:true};await load();setAdded(null);
    setNotice(`本次返回 ${batch.drafts.length} 道候选${batch.model_name?'（模型 '+batch.model_name+'）':''}，逐道核对后才会入库。`);
   }catch(error){
    const lost=error instanceof Error&&/网络|离线|连接/.test(error.message);
    claim.current={sig,key,spent:!lost};await load().catch(()=>{});setNewCall(true);throw error;
   }finally{setRunning(false);}
  });
 }
 const batchOf=(id:string|null)=>batches.find(b=>b.id===id)||null;
 useEffect(()=>{void run(load);},[]);
 return <><p role="status" className={notice?'notice':'notice hidden'}>{notice||' '}</p>
  {failure&&<p role="alert" className="error">{failure}</p>}
  <section className="panel"><h2>发现新菜谱</h2>
   <p>{capability.model_enabled
    ?'候选由已配置的模型生成：每次点击最多一次请求、最多 '+capability.candidates+' 道、输出上限 '+capability.output_tokens+' token。生成结果只是草稿，必须逐道人工核对并确认后才进入菜谱库。'
    :'当前未配置可用的生成模型，仍可手工新建并核对候选草稿；配好模型地址、名称和密钥后，这里的生成会自动开放。'}</p>
   <div className="row">
    <label>人数（留空用厨房偏好）<input type="number" min="1" max="10" step="1" value={conditions.servings} onChange={e=>edit({servings:e.target.value})}/></label>
    <label>最多用时（分钟，留空用厨房偏好）<input type="number" min="1" max="480" step="1" value={conditions.maxMinutes} onChange={e=>edit({maxMinutes:e.target.value})}/></label>
   </div>
   <label>本次可用厨具（逗号分隔，留空用厨房偏好）<input value={conditions.equipment} onChange={e=>edit({equipment:e.target.value})}/></label>
   <label>不可放宽的排除食材（逗号分隔）<input value={conditions.excluded} onChange={e=>edit({excluded:e.target.value})}/></label>
   <label>其他要求（最多 500 字）<textarea rows={2} maxLength={500} value={conditions.requirement} onChange={e=>edit({requirement:e.target.value.slice(0,500)})} placeholder="例如：少油、一锅出"/></label>
   <label>优先使用现有库存食材<input type="checkbox" checked={conditions.preferInventory} onChange={e=>edit({preferInventory:e.target.checked})}/></label>
   <div className="row">
    <button disabled={busy||running||!capability.model_enabled} onClick={generate}>{newCall?'重新发起生成（会产生新的一次模型调用）':'生成候选'}</button>
    <button className="secondary" disabled={busy} onClick={()=>void run(load)}>刷新候选列表</button>
   </div>
   {running&&<p role="status">正在生成候选，请勿重复点击。</p>}
   {newCall&&<p role="status">上一次生成没有成功。再点一次会新建一次请求，可能产生新的模型调用费用；填写的条件保持不变。</p>}
   {batches.length>0&&<details><summary>最近的生成记录</summary>{batches.slice(0,5).map(b=><p key={b.id}>
    {b.status==='completed'?'已完成':b.status==='failed'?'未成功':'处理中或已中断'} · {b.drafts.length} 道候选 · {b.model_name||'未使用模型'}
    {b.error_code?' · 代码 '+b.error_code:''}{b.usage?' · 实际 token '+b.usage.total_tokens:' · 无实际用量'}</p>)}</details>}
  </section>
  <section className="panel"><h2>候选草稿</h2>
   <p>逐道编辑并校验。「确认加入菜谱库」才会写入正式菜谱；「丢弃」不改变库存与菜谱。生成、编辑、校验都不扣减库存。</p>
   <button className="secondary" disabled={busy} onClick={()=>void run(async()=>{await write('/recipe-drafts',{payload:readPayload({})});
    await load();setNotice('已创建一份空白手工草稿，请补全内容后校验。');})}>手工新建草稿</button>
   {drafts.length===0&&<p className="muted">还没有待核对的候选。可以「生成候选」，或手工新建一份草稿。</p>}
   {drafts.map(d=><DraftEditor key={d.id} draft={d} items={items} busy={busy} batch={batchOf(d.batch_id)} check={checks[d.id]}
    onCheck={payload=>run(async()=>{const result=await api('/recipe-drafts/'+d.id+'/validate','POST',{payload});
     setStateChecks(c=>({...c,[d.id]:{payload,errors:result.errors,warnings:result.warnings}}));})}
    onSave={payload=>run(async()=>{await write('/recipe-drafts/'+d.id,{expected_version:d.version,payload},'PUT');
     setStateChecks(c=>({...c,[d.id]:undefined}));await load();setNotice('草稿已保存，库存未改变。');})}
    onAccept={ack=>run(async()=>{const result=await write('/recipe-drafts/'+d.id+'/accept',{expected_version:d.version,acknowledge_warnings:ack});
     setStateChecks(c=>({...c,[d.id]:undefined}));
     setAdded({batchId:d.batch_id,constraints:batchOf(d.batch_id)?.constraints??null,name:result.recipe.name});
     await load();await onChanged();setNotice('「'+result.recipe.name+'」已加入菜谱库，可在「我的菜谱」查看。');})}
    onDiscard={()=>run(async()=>{await write('/recipe-drafts/'+d.id+'/discard',{expected_version:d.version});
     await load();setNotice('草稿已丢弃，没有写入菜谱或库存。');})}/>)}
  </section>
  {added&&<section className="panel"><h2>加入之后</h2>
   {added.batchId===null
    ?<p>「{added.name}」已进入菜谱库。这是手工草稿，重新推荐会按当前厨房偏好进行。</p>
    :added.constraints
     ?<p>「{added.name}」已进入菜谱库。可以按本次发现的条件（{added.constraints.servings} 人、最多 {added.constraints.max_minutes} 分钟）继续生成推荐，条件不会被自动放宽。</p>
     :<p role="alert" className="error">「{added.name}」已进入菜谱库，但这一批的发现条件没能读取到；重新推荐已停用，请到「我的菜谱」按需要的条件推荐。</p>}
   <div className="row"><button disabled={busy||added.batchId!==null&&!added.constraints} onClick={()=>void run(async()=>{await onRecommend(added.constraints);
    setNotice(added.batchId===null?'已按当前厨房偏好重新推荐，结果在「我的菜谱」页。':'已按本次发现条件重新推荐，结果在「我的菜谱」页。');})}>用当前条件重新推荐</button>
    <button className="secondary" disabled={busy} onClick={()=>setAdded(null)}>留在本页</button></div></section>}
 </>;
}

function DraftEditor({draft,items,busy,batch,check,onSave,onCheck,onAccept,onDiscard}:{draft:any;items:Ingredient[];busy:boolean;
 batch:any;check?:Check;onSave:(payload:Payload)=>Promise<void>;onCheck:(payload:Payload)=>Promise<void>;
 onAccept:(ack:boolean)=>Promise<void>;onDiscard:()=>Promise<void>}){
 const [value,setValue]=useState<Payload>(readPayload(draft.payload));
 // The typed text is kept verbatim: cleaning it on every keystroke deletes the comma or newline
 // the user just pressed, so a second tool or step could never be entered. Parsing stays at
 // the point where a list is actually needed — the value sent for checking and saving.
 const [raw,setRaw]=useState(()=>({equipment:value.equipment.join('，'),steps:value.steps.join('\n')}));
 const [touched,setTouched]=useState(false),[ack,setAck]=useState(false),[seen,setSeen]=useState(draft.version);
 // The version only advances when the server stored something, so the field report shown
 // here is the saved one; the typed text itself is never reloaded from the list refresh.
 useEffect(()=>{if(draft.version!==seen){setSeen(draft.version);setTouched(false);}},[draft.version]);
 const dirty=touched;
 const fresh=check&&JSON.stringify(check.payload)===JSON.stringify(value);
 const errors:any[]=fresh?check!.errors:draft.validation_errors;
 const warnings:any[]=fresh?check!.warnings:draft.validation_warnings;
 const grouped=groupByField(errors);
 const at=(field:string)=>(grouped[field]||[]).map(issueText);
 const set=(patch:Partial<Payload>)=>{setTouched(true);setAck(false);setValue(v=>({...v,...patch}));};
 const setLine=(n:number,patch:Partial<Line>)=>set({ingredients:value.ingredients.map((l,i)=>i===n?{...l,...patch}:l)});
 const setTools=(text:string)=>{setRaw(r=>({...r,equipment:text}));set({equipment:words(text)});};
 const setSteps=(text:string)=>{setRaw(r=>({...r,steps:text}));set({steps:lines(text)});};
 const creating=newIngredientHints(value.ingredients,items);
 const stray=value.cooking_methods.filter(m=>!isCookingMethod(m));
 return <section className="panel draft-editor"><h3>{value.name||'未命名候选'}</h3>
  <small>{draft.source_type==='llm'?'模型生成，待人工核对':'手工草稿'} · 已保存版本 {draft.version}
   {batch?' · 本次条件：'+batch.constraints.servings+' 人、最多 '+batch.constraints.max_minutes+' 分钟':''}</small>
  {dirty&&<p role="status">有未保存的修改；保存后才会写入草稿。</p>}
  <label>菜谱名称<input maxLength={100} value={value.name} onChange={e=>set({name:e.target.value})}/></label>
  {at('name').map((t,n)=><p role="alert" key={n}>{t}</p>)}
  <div className="row">
   <label>人数<input maxLength={4} value={value.servings} onChange={e=>set({servings:e.target.value})}/></label>
   {at('servings').map((t,n)=><p role="alert" key={n}>{t}</p>)}
   <label>用时（分钟）<input maxLength={4} value={value.minutes} onChange={e=>set({minutes:e.target.value})}/></label>
   {at('minutes').map((t,n)=><p role="alert" key={n}>{t}</p>)}
  </div>
  <label>厨具（逗号分隔）<input value={raw.equipment} onChange={e=>setTools(e.target.value)}/></label>
  {at('equipment').map((t,n)=><p role="alert" key={n}>{t}</p>)}
  <label>做法（每行一步）<textarea rows={4} value={raw.steps} onChange={e=>setSteps(e.target.value)}/></label>
  {at('steps').map((t,n)=><p role="alert" key={n}>{t}</p>)}
  <div className="method-picker"><span>烹饪方式（由人工选择，最多 {MAX_METHODS} 个）</span>
   <div className="method-options">{COOKING_METHODS.map(m=><label key={m}><input type="checkbox" checked={value.cooking_methods.includes(m)} disabled={!value.cooking_methods.includes(m)&&value.cooking_methods.length>=MAX_METHODS} onChange={()=>set({cooking_methods:toggleMethod(value.cooking_methods,m)})}/>{methodName(m)}</label>)}</div>
   {stray.length>0&&<p className="stray">无法识别的写法需要改成上面的标签：{stray.map(t=><span className="tag invalid" key={t}>{t}<button type="button" className="text-button" onClick={()=>set({cooking_methods:value.cooking_methods.filter(x=>x!==t)})}>移除</button></span>)}</p>}
   {at('cooking_methods').map((t,n)=><p role="alert" key={n}>{t}</p>)}
  </div>
  <p>数量与单位逐项填写。「适量」「一碗」这类无法换算的写法会标在对应行上，修正后才能入库。</p>
  {value.ingredients.map((line,n)=><div className="draft-line" key={n}>
   <div className="row">
    <label>食材<input maxLength={80} value={line.name} onChange={e=>setLine(n,{name:e.target.value})} placeholder="例如：鸡蛋"/></label>
    <label>数量<input maxLength={12} value={line.quantity} onChange={e=>setLine(n,{quantity:e.target.value})} placeholder="例如：2"/></label>
    <label>单位<select value={line.unit} onChange={e=>setLine(n,{unit:e.target.value})}><option value="">未填</option>
     {Object.entries(units).map(([k,l])=><option value={k} key={k}>{l}</option>)}</select></label>
    <label>可选配料<input type="checkbox" checked={line.optional} onChange={e=>setLine(n,{optional:e.target.checked})}/></label>
    <button type="button" className="text-button" disabled={value.ingredients.length<=1} onClick={()=>set({ingredients:value.ingredients.filter((_,i)=>i!==n)})}>删除该行</button>
   </div>
   {(['name','quantity','unit','resolved_ingredient_id'] as const).flatMap(part=>at(`ingredients[${n+1}].${part}`)).map((t,i)=><p role="alert" key={i}>{t}</p>)}
  </div>)}
  {at('ingredients').map((t,n)=><p role="alert" key={n}>{t}</p>)}
  {creating.length>0&&<p role="status">确认后将新建食材：{creating.map(x=>x.name+'（'+x.unit+'）').join('、')}。已有食材的单位不会被改写。</p>}
  <button type="button" className="secondary" disabled={busy||value.ingredients.length>=40} onClick={()=>set({ingredients:[...value.ingredients,blank()]})}>增加食材行</button>
  {warnings.length>0&&<div className="warn-list"><h4>需要人工核对的提示</h4>
   {warnings.map((w,n)=><p key={n}>{issueText(w)}</p>)}
   <label>我已核对以上提示<input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/></label></div>}
  <div className="row">
   <button className="secondary" disabled={busy} onClick={()=>void onCheck(value)}>按当前填写校验</button>
   <button disabled={busy||!dirty} onClick={()=>void onSave(value)}>保存草稿</button>
   <button disabled={busy||dirty||errors.length>0||(warnings.length>0&&!ack)} onClick={()=>void onAccept(ack)}>确认加入菜谱库</button>
   <button className="text-button" disabled={busy} onClick={()=>{if(window.confirm('丢弃这份草稿？正式菜谱和库存都不会改变。'))void onDiscard();}}>丢弃草稿</button>
  </div>
  {dirty&&(!fresh)&&(errors.length>0||warnings.length>0)&&<p role="status">上面的提示对应已保存的版本；保存草稿或点「按当前填写校验」可看到当前填写的结果。</p>}
 </section>;
}
