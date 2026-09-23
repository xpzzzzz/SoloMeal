import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import AgentPanel from './AgentPanel';
import InventoryEditor from './InventoryEditor';
import ShoppingPanel from './ShoppingPanel';
import CombinedShoppingPanel from './CombinedShoppingPanel';
import ReceiptPanel from './ReceiptPanel';
import DiscoveryPanel from './DiscoveryPanel';
import RecommendationPanel from './RecommendationPanel';
import HomePanel from './HomePanel';
import CookingMode,{CookingStart,DurationEditor} from './CookingMode';
import {clearTimers} from './cookingTimer';
import {sessionJson,SessionChangedError,browserOnline,watchBrowserOnline,pagedList} from './session';
import {errorText} from './errorText';
import {timeLabel} from './personalTime';
import {COOKING_METHODS,MAX_METHODS,methodName,methodsFromStored,toggleMethod,methodText} from './cookingMethods';

type Ingredient={id:string;name:string;unit:string;is_staple?:boolean};
type Batch={id:string;name:string;quantity:string;unit:string;location:string;expires_on:string|null;expiry_status:string;expiry_source:string;archived:boolean;version:number};
type Rating='neutral'|'like'|'dislike';
type Feedback={recipe_id:string;favorite:boolean;rating:Rating;version:number;updated_at:string|null};
type Recipe={id:string;name:string;version:number;source:string;minutes:number;servings:number;equipment:string[];steps:string[];cooking_methods:string[];feedback?:Feedback;ingredients:{ingredient_id:string;name:string;quantity:string;unit:string;optional?:boolean}[]};
type Cook={id:string;recipe:Recipe;servings:number;status:string;actual_minutes:number|null;duration_source:string|null;feedback_version:number};
const units:Record<string,string>={g:'克',kg:'千克',ml:'毫升',l:'升',piece:'个'};
// A recipe the server never annotated reads as the empty state, the same way the backend does.
const fbOf=(recipe:Recipe):Feedback=>recipe.feedback??{recipe_id:recipe.id,favorite:false,rating:'neutral',version:0,updated_at:null};
function preferenceText(candidate:any){
 const p=candidate.personalization;
 if(!p?.enabled)return '个性化排序已关闭';
 const reason=p.reasons?.[0];
 if(reason?.type==='feedback')return reason.rating==='dislike'?'根据你的不喜欢评价降低排序':'根据你的收藏/喜欢评价提高排序';
 if(!p.history_count)return '暂无完成记录，偏好仍在积累';
 if(reason?.type==='method')return `最近${reason.window_count}次完成记录中${reason.occurrence_count}次使用${methodName(reason.method)}${reason.window_count<5?'，偏好仍在积累':''}`;
 const line=candidate.recipe.ingredients.find((i:any)=>i.ingredient_id===reason?.ingredient_id);
 return line?`最近${reason.window_count}次完成记录中${reason.occurrence_count}次使用${line.name}${reason.window_count<5?'，偏好仍在积累':''}`:'基于最近完成记录个性化排序';
}

function App(){
 const refreshSequence=useRef(0);
 const sessionToken=useRef(''),sessionEpoch=useRef(0);
 function changeSession(next:string){if(userId)clearTimers(userId);setUserId('');setCookingStart(null);sessionToken.current=next;sessionEpoch.current++;refreshSequence.current++;retryKeys.current.clear();setToken(next);setRegister(false);setNotice('');setItems([]);setBatches([]);setRecipes([]);setHistory([]);setPlans([]);setPlanHistory({});setRecommendations(null);setEditingRecipe(null);setPending(null);setDiscoverySeed(null);setSavedFeedback(null);setOnlyFavorites(false);setBasket([]);setCombinationOperation(null);combinationPending.current=null;combinationInFlight.current=false;setCombinationSaving(false);setCombinationBudget('');setHistoryFocus('');}
 const retryKeys=useRef(new Map<string,string>());
 async function mutation(path:string,body?:unknown,method='POST'){const signature=JSON.stringify([token,path,method,body]);let key=retryKeys.current.get(signature);if(!key){key=crypto.randomUUID();retryKeys.current.set(signature,key);}const result=await api(path,method,body,key);retryKeys.current.delete(signature);return result;}
 const [token,setToken]=useState('');
 const [userId,setUserId]=useState('');
 const [cookingStart,setCookingStart]=useState<CookingStart|null>(null);
 const [tab,setTab]=useState('today');
 const [historyFocus,setHistoryFocus]=useState('');
 const [notice,setNotice]=useState('');
 const [busy,setBusy]=useState(false);
 const [items,setItems]=useState<Ingredient[]>([]);
 const [batches,setBatches]=useState<Batch[]>([]);
 const [recipes,setRecipes]=useState<Recipe[]>([]);
 const [history,setHistory]=useState<Cook[]>([]);
 const [plans,setPlans]=useState<any[]>([]);
 const [editingRecipe,setEditingRecipe]=useState<Recipe|null>(null);
 const [planHistory,setPlanHistory]=useState<Record<string,any[]>>({});
 const [recommendations,setRecommendations]=useState<any>(null);
 const [discoverySeed,setDiscoverySeed]=useState<Record<string,unknown>|null>(null);
 const [pending,setPending]=useState<{recipe:Recipe;key:string;planId?:string;version?:number}|null>(null);
 const [savedFeedback,setSavedFeedback]=useState<{id:string;text:string}|null>(null);
 const [shoppingRefresh,setShoppingRefresh]=useState(0);
 const [combinationBudget,setCombinationBudget]=useState('');
 const [combinationOperation,setCombinationOperation]=useState<any>(null);
 const combinationPending=useRef<any>(null),combinationInFlight=useRef(false);
 const [combinationSaving,setCombinationSaving]=useState(false);
 async function saveCombination(body?:unknown){
  if(combinationInFlight.current)return;
  const epoch=sessionEpoch.current;
  const operation=combinationPending.current||{body,key:crypto.randomUUID()};
  if(!operation.body)return;
  combinationPending.current=operation;setCombinationOperation(operation);
  combinationInFlight.current=true;setCombinationSaving(true);
  try{
   await api('/shopping/combined','POST',operation.body,operation.key);
   combinationPending.current=null;setCombinationOperation(null);setBasket([]);setCombinationBudget('');
   setShoppingRefresh(v=>v+1);setNotice('采购清单已保存，尚未入库。请勾选已买并核对。');setTab('shopping');
  }catch(e){
   // A definitive rejected request can be edited; an unknown result must retain its exact body and key.
   if(epoch===sessionEpoch.current&&e instanceof Error&&'status' in e&&[400,404,409,422].includes(Number(e.status))){combinationPending.current=null;setCombinationOperation(null);}
   throw e;
  }finally{if(epoch===sessionEpoch.current){combinationInFlight.current=false;setCombinationSaving(false);}}
 }
 const [basket,setBasket]=useState<any[]>([]);
 function addToBasket(recipe:Recipe,servings=recipe.servings,include_optional=false){
  if(combinationPending.current){setNotice('上次采购保存结果待确认，请先返回采购组合重试保存');return;}
  if(basket.some(r=>r.recipe_id===recipe.id)){document.getElementById('combination-'+recipe.id)?.focus();setNotice('这道菜已在采购组合中，可修改人数');return;}
  if(basket.length>=10){setNotice('采购组合最多10道菜');return;}
  setBasket([...basket,{recipe_id:recipe.id,version:recipe.version,name:recipe.name,servings,include_optional}]);setNotice('已加入采购组合，可继续选菜');
 }
 const [onlyFavorites,setOnlyFavorites]=useState(false);
 const [register,setRegister]=useState(false);
 const [online,setOnline]=useState(browserOnline);
 useEffect(()=>watchBrowserOnline(setOnline),[]);
 const offlineBar=!online&&<p role="alert" className="offline-bar">浏览器已离线，恢复网络后页面会自动同步</p>;
  async function api(path:string,method='GET',body?:unknown,key?:string,session=token){
   const epoch=sessionEpoch.current;
   const read=async(path:string)=>{
   const {response,data}=await sessionJson('/api/v1'+path,{method,headers:{'Content-Type':body instanceof Blob?body.type:'application/json',...(session?{Authorization:'Bearer '+session}:{}),...(key?{'Idempotency-Key':key}:{})},body:body===undefined?undefined:body instanceof Blob?body:JSON.stringify(body)},()=>epoch===sessionEpoch.current&&session===sessionToken.current,browserOnline,path.endsWith('/file')?response=>response.ok?response.blob():response.json():undefined);
   if(!response.ok){if(response.status===401&&session)changeSession('');throw Object.assign(new Error(response.status===429?'请求较频繁，请稍后重试（约 '+(response.headers.get('Retry-After')||'60')+' 秒）':errorText(data?.error)),{status:response.status});}
   return data;
   };
   return method==='GET'?pagedList(path,read):read(path);
 }
 async function refresh(){
   const sequence=++refreshSequence.current;
   const [i,b,r,h,p]=await Promise.all([api('/ingredients'),api('/inventory'),api('/recipes'),api('/cooking'),api('/plans')]);
   if(sequence!==refreshSequence.current)return;
   setItems(i);setBatches(b);setRecipes(r);setHistory(h);setPlans(p);
 }
 async function perform(action:()=>Promise<void>){setBusy(true);setNotice('');try{await action();}catch(e){if(!(e instanceof SessionChangedError))setNotice(e instanceof Error?e.message:'请求失败');}finally{setBusy(false);}}
 // Discovery keeps its own stored conditions; re-recommending replays them without relaxing anything.
 async function recommendWith(constraints:Record<string,any>|null){const stored=constraints||{};
  const body={include_optional:false,score_weights:{inventory:60,expiry:40,repetition:10,purchase_cost:0},use_saved_quotes:true,
   ...(typeof stored.servings==='number'?{servings:stored.servings}:{}),
   ...(typeof stored.max_minutes==='number'?{max_minutes:stored.max_minutes}:{}),
   ...(Array.isArray(stored.equipment)?{equipment:stored.equipment}:{}),
   ...(Array.isArray(stored.excluded_ingredients)?{excluded_ingredients:stored.excluded_ingredients}:{})};
  setRecommendations({...await api('/recommendations','POST',body),request:body});setTab('recipes');}
 useEffect(()=>{if(token)void perform(refresh);},[token]);
 useEffect(()=>{if(!token)return;const sync=()=>{if(document.visibilityState==='visible')void perform(refresh);};window.addEventListener('focus',sync);window.addEventListener('online',sync);document.addEventListener('visibilitychange',sync);return()=>{window.removeEventListener('focus',sync);window.removeEventListener('online',sync);document.removeEventListener('visibilitychange',sync);};},[token]);
 const count=batches.filter(b=>Number(b.quantity)>0&&b.expiry_status!=='expired').length;
 const expiring=batches.filter(b=>Number(b.quantity)>0&&b.expiry_status==='expiring_soon').length;
 const shownRecipes=onlyFavorites?recipes.filter(r=>fbOf(r).favorite):recipes;
 // The whole state goes back every time, so switching a rating replaces it instead of stacking,
 // and a saved answer is kept in the card rather than waiting for the next list refresh.
 async function saveFeedback(recipe:Recipe,next:{favorite:boolean;rating:Rating}){
  const saved=await mutation('/recipes/'+recipe.id+'/feedback',{...next,expected_version:fbOf(recipe).version},'PUT');
  setRecipes(rows=>rows.map(r=>r.id===recipe.id?{...r,feedback:saved}:r));
  setSavedFeedback({id:recipe.id,text:'评价已保存（版本 '+saved.version+'）。本阶段推荐排序不使用评价。'});
  return saved;
 }
 // The home recommendation cards carry no feedback of their own, so the version comes from
 // the recipe list already loaded for this account rather than a second read.
 async function favoriteCandidate(candidate:any,next:{favorite:boolean;rating:Rating}){
  const known=recipes.find(r=>r.id===candidate.recipe.id);
  if(!known)throw new Error('这道菜已不在你的菜谱里，请刷新后重试');
  return await saveFeedback(known,next);
 }
 function openHistory(id:string){
  setTab('history');setHistoryFocus(id);
 }
 useEffect(()=>{
  if(tab!=='history'||!historyFocus)return;
  const row=document.getElementById('meal-'+historyFocus);
  if(!row){setNotice('这条记录已不在当前列表，请刷新后重试');setHistoryFocus('');return;}
  row.focus();row.scrollIntoView({block:'center'});setHistoryFocus('');
 },[tab,historyFocus]);
 const submitLogin=(event:React.FormEvent<HTMLFormElement>)=>{event.preventDefault();const f=new FormData(event.currentTarget);void perform(async()=>{const body={username:f.get('username'),password:f.get('password')};if(register)await api('/auth/register','POST',body);const session=await api('/auth/login','POST',body);changeSession(session.access_token);const me=await api('/me','GET',undefined,undefined,session.access_token);setUserId(me.id);});};
 if(!token)return <main className="login"><div className="wordmark">SoloMeal<span>一人食，也认真吃</span></div><section className="login-card"><p className="eyebrow">我的厨房</p><h1>{register?'建立你的厨房':'欢迎回来'}</h1><p className="muted">记住冰箱里有什么，从下一顿饭开始。</p><form onSubmit={submitLogin}><label>用户名<input name="username" required minLength={3} maxLength={64} pattern="[A-Za-z0-9_]+" autoComplete="username" placeholder="字母、数字或下划线"/></label><label>密码<input name="password" type="password" required minLength={10} maxLength={128} autoComplete={register?'new-password':'current-password'} placeholder="至少 10 个字符"/></label><button disabled={busy}>{busy?'正在处理…':register?'创建账号':'登录'}</button></form><button className="text-button" onClick={()=>{setRegister(!register);setNotice('');}}>{register?'已有账号？登录':'第一次使用？创建账号'}</button><p role="alert" className="error">{notice}</p><small>当前版本刷新页面后需重新登录。</small></section>{offlineBar}</main>;
 return <div className="shell"><aside><div className="wordmark">SoloMeal<span>我的日常厨房</span></div><nav aria-label="主导航">{[['today','今天'],['agent','一人食助手'],['inventory','食材库存'],['recipes','我的菜谱'],['discovery','发现菜谱'],['shopping','报价与采购'],['receipts','小票录入'],['history','用餐记录'],['settings','厨房偏好']].map(([id,label])=><button key={id} className={tab===id?'active':''} onClick={()=>setTab(id)}>{label}</button>)}</nav><div className="aside-bottom"><small>先用已有的，再买需要的。</small><button className="text-button" onClick={()=>void perform(async()=>{await api('/auth/logout','POST');changeSession('');})}>退出登录</button></div></aside><main><header><div><p className="eyebrow">SOLOMEAL / KITCHEN</p><h1>{({today:'今天做点什么',agent:'一起安排下一餐',inventory:'把食材用在刚好的时候',recipes:'下一顿，做什么？',discovery:'发现新菜，先核对再加',shopping:'买好需要的，记入厨房',receipts:'核对小票，记好每一项',history:'每一餐都有记录',settings:'按你的习惯来'} as Record<string,string>)[tab]}</h1></div><button className="secondary" disabled={busy} onClick={()=>void perform(refresh)}>刷新库存</button></header><div role="status" className={notice?'notice':'notice hidden'}>{notice||' '}</div>{offlineBar}
 {userId&&<CookingMode key={token} userId={userId} start={cookingStart} onStartHandled={()=>setCookingStart(null)} api={api} onDone={()=>{setTab('history');setNotice('已记录，库存同步更新');void perform(refresh);}}/>}
 {tab==='today'&&<HomePanel key={'home:'+token} api={api} emptyAccount={!recipes.length&&!batches.length} onImport={async()=>{await api('/recipes/examples','POST');await refresh();}} goTo={setTab} onHistory={openHistory} preferenceText={preferenceText} onCook={c=>setCookingStart({recipe:c.recipe,servings:c.servings,includeOptional:c.include_optional})} onAdd={c=>{addToBasket(c.recipe,c.servings,c.include_optional);setTab('shopping');}} onSave={async(c,request)=>{await mutation('/plans',{recipe_id:c.recipe.id,constraints:request});await refresh();setNotice('已保存方案，可在我的菜谱里确认或更新');}} onSettings={()=>setTab('settings')} onDiscover={constraints=>{setDiscoverySeed(constraints);setTab('discovery');}} favorite={favoriteCandidate}/>}
 {tab==='agent'&&<AgentPanel api={api} token={token} onChanged={refresh}/>}
 {tab==='inventory'&&<><InventoryEditor items={items} batches={batches} api={api} refresh={refresh}/><div className="stats"><section><span>可用库存批次</span><strong>{count}<small>批</small></strong></section><section><span>三天内到期</span><strong>{expiring}<small>批</small></strong></section><section><span>已记录的餐食</span><strong>{history.filter(h=>h.status==='completed').length}<small>餐</small></strong></section></div><div className="columns"><section className="panel"><div className="panel-heading"><h2>冰箱与储物架</h2><span className="muted">按批次管理</span></div>{batches.length===0?<div className="empty"><h3>暂无未归档的库存批次</h3><p>可以录入新批次，或在上方查看并恢复已归档批次。</p></div>:<div className="table-wrap"><table><thead><tr><th>食材</th><th>剩余</th><th>日期</th><th>状态</th></tr></thead><tbody>{batches.map(b=><tr key={b.id}><td><b>{b.name}</b><small>{b.location}</small></td><td>{Number(b.quantity)} {units[b.unit]}</td><td>{b.expires_on||'未填写'}</td><td><span className={'tag '+b.expiry_status}>{({expired:'已到期',expiring_soon:'临期',fresh:'日期充足',unknown:'日期未知'} as Record<string,string>)[b.expiry_status]}</span></td></tr>)}</tbody></table></div>}<p className="footnote">日期用于提醒；已到期批次保留记录，不参与做饭扣减。</p></section><div><section className="panel"><h2>添加食材种类</h2><form onSubmit={e=>{e.preventDefault();const form=e.currentTarget;const f=new FormData(form);void perform(async()=>{await api('/ingredients','POST',{name:f.get('name'),unit:f.get('unit')});form.reset();await refresh();});}}><label>食材名称<input name="name" required maxLength={80} placeholder="例如：鸡蛋、番茄"/></label><label>计量单位<select name="unit"><option value="g">克</option><option value="ml">毫升</option><option value="piece">个</option></select></label><button disabled={busy}>添加种类</button></form></section><section className="panel"><h2>记一笔入库</h2><form onSubmit={e=>{e.preventDefault();const form=e.currentTarget;const f=new FormData(form);const selected=items.find(i=>i.id===f.get('ingredient'));void perform(async()=>{await mutation('/inventory',{ingredient_id:selected?.id,quantity:f.get('quantity'),unit:selected?.unit,expires_on:f.get('expires')||null,expiry_source:f.get('expires')?'user':'unknown',location:f.get('location')});form.reset();await refresh();});}}><label>食材<select name="ingredient" required defaultValue="" aria-label="入库食材"><option value="" disabled>选择已添加的食材</option>{items.map(i=><option value={i.id} key={i.id}>{i.name}（{units[i.unit]}）</option>)}</select></label><label>数量<input name="quantity" type="number" min="0.001" step="0.001" required/></label><div className="row"><label>到期日期<input name="expires" type="date"/></label><label>存放位置<select name="location"><option>冷藏</option><option>冷冻</option><option>常温</option></select></label></div><button disabled={busy||!items.length}>确认入库</button></form></section></div></div></>}
 {(tab==='recipes'||tab==='shopping')&&<CombinedShoppingPanel key={'combination:'+token} api={api} basket={basket} onBasket={setBasket} budget={combinationBudget} onBudget={setCombinationBudget} operation={combinationOperation} saving={combinationSaving} onSave={saveCombination}/>}
 {tab==='recipes'&&<><RecommendationPanel key={token} api={api} result={recommendations} onResult={setRecommendations} preferenceText={preferenceText} onAdd={c=>addToBasket(c.recipe,c.servings,c.include_optional)} onCook={c=>setCookingStart({recipe:c.recipe,servings:c.servings,includeOptional:c.include_optional})} onSave={async(c,request)=>{await mutation('/plans',{recipe_id:c.recipe.id,constraints:request});await refresh();setNotice('已保存方案，可在下方确认或更新');}} onSettings={()=>setTab('settings')} onDiscover={constraints=>{setDiscoverySeed(constraints);setTab('discovery');}}/><section className="panel"><h2>已保存的方案</h2>{plans.length===0?<p className="muted">先生成推荐，再保存想做的一餐。</p>:plans.map(p=><div className="history-row" key={p.id}><div><h3>{p.snapshot.candidate.recipe.name} · {p.snapshot.candidate.servings} 人份</h3><button className="text-button" disabled={busy} onClick={()=>void perform(async()=>setPlanHistory({...planHistory,[p.id]:await api('/plans/'+p.id+'/revisions')}))}>查看版本历史</button>{planHistory[p.id]&&<details open><summary>历史版本（只读）</summary>{planHistory[p.id].map(v=><div key={v.version}><b>版本 {v.version} · {v.snapshot.candidate.recipe.name}</b><p>{v.snapshot.candidate.servings} 人份 · {v.snapshot.state.date} · {v.snapshot.candidate.recipe.minutes} 分钟 · {v.snapshot.candidate.can_cook_now?'当时库存足够':'当时需要补购'}</p><small>评分 {v.snapshot.candidate.score} · {v.snapshot.candidate.include_optional?'使用可选配料':'不使用可选配料'}</small></div>)}</details>}<small>版本 {p.version} · {p.status==='completed'?'已完成':p.status==='cancelled'?'已取消':'待确认'}</small></div>{p.status==='pending'&&<div className="row">{p.snapshot.candidate.shopping.length>0&&<button className="secondary" disabled={busy} onClick={()=>void perform(async()=>{await mutation('/shopping',{plan_id:p.id,expected_version:p.version});setTab('shopping');})}>准备采购</button>}<button className="secondary" disabled={busy} onClick={()=>void perform(async()=>{await mutation('/plans/'+p.id+'/revisions',{recipe_id:p.snapshot.candidate.recipe.id,constraints:p.snapshot.request,expected_version:p.version});await refresh();setNotice('方案已按最新库存更新');})}>按当前库存更新</button><button className="text-button" disabled={busy} onClick={()=>void perform(async()=>{await mutation('/plans/'+p.id+'/cancel',{expected_version:p.version});await refresh();})}>取消方案</button><button disabled={busy} onClick={()=>setPending({recipe:{...p.snapshot.candidate.recipe,servings:p.snapshot.candidate.servings},key:crypto.randomUUID(),planId:p.id,version:p.version})}>确认做完</button></div>}</div>)}</section><section className="panel"><h2>示例菜谱</h2><p>导入3道原创定量示例，仅添加食材种类和菜谱，不添加库存。重复导入不会重复创建。</p><button disabled={busy} onClick={()=>void perform(async()=>{await api('/recipes/examples','POST');await refresh();setNotice('示例菜谱已就绪，请按实际数量录入库存');})}>导入示例菜谱</button></section><RecipeEditor key={editingRecipe?.id||'new'} initial={editingRecipe} onClose={()=>setEditingRecipe(null)} items={items} api={api} perform={perform} busy={busy} refresh={refresh}/><div className="recipe-filter"><label>只看收藏<input type="checkbox" checked={onlyFavorites} onChange={e=>setOnlyFavorites(e.target.checked)}/></label><small>收藏与评价只存在你的账号下；开启个性化排序时用于推荐。</small></div><div className="recipe-grid">{shownRecipes.length===0?<section className="panel empty"><h2>{onlyFavorites?'收藏里还没有菜谱':'还没有菜谱'}</h2><p>{onlyFavorites?'先在下面的菜谱上点「收藏」，它就会留在这份清单里。':'当前阶段可通过 API 添加定量菜谱。也可以在上方展开添加菜谱。'}</p></section>:shownRecipes.map(r=><section className="panel recipe" key={r.id}><p className="eyebrow">{r.minutes} 分钟 · {r.servings} 人份</p><h2>{r.name}</h2><p>{r.equipment.join(' / ')}</p>{r.cooking_methods.length>0&&<p className="methods">{r.cooking_methods.map((m,n)=><span className="tag" key={n}>{methodName(m)}</span>)}</p>}<ul>{r.ingredients.map((i,n)=><li key={n}>{i.name}{i.optional?'（可选）':''}<span>{Number(i.quantity)} {units[i.unit]}</span></li>)}</ul><details><summary>查看做法</summary><ol>{r.steps.map((s,n)=><li key={n}>{s}</li>)}</ol></details><div className="row feedback-row"><button className={fbOf(r).favorite?'chosen':''} aria-pressed={fbOf(r).favorite} disabled={busy} onClick={()=>void perform(()=>saveFeedback(r,{favorite:!fbOf(r).favorite,rating:fbOf(r).rating}))}>{fbOf(r).favorite?'已收藏':'收藏'}</button><button className={fbOf(r).rating==='like'?'chosen':'secondary'} aria-pressed={fbOf(r).rating==='like'} disabled={busy} onClick={()=>void perform(()=>saveFeedback(r,{favorite:fbOf(r).favorite,rating:'like'}))}>喜欢</button><button className={fbOf(r).rating==='dislike'?'chosen':'secondary'} aria-pressed={fbOf(r).rating==='dislike'} disabled={busy} onClick={()=>void perform(()=>saveFeedback(r,{favorite:fbOf(r).favorite,rating:'dislike'}))}>不喜欢</button>{fbOf(r).rating!=='neutral'&&<button className="text-button" disabled={busy} onClick={()=>void perform(()=>saveFeedback(r,{favorite:fbOf(r).favorite,rating:'neutral'}))}>清除评价</button>}</div>{savedFeedback&&savedFeedback.id===r.id&&<p role="status" className="footnote">{savedFeedback.text}</p>}<div className="row"><button className="secondary" onClick={()=>addToBasket(r)}>加入采购组合</button><button disabled={busy||!userId} onClick={()=>setCookingStart({recipe:r})}>开始做饭</button><button disabled={busy} onClick={()=>setPending({recipe:r,key:crypto.randomUUID()})}>记录做完这道菜</button><button className="secondary" disabled={busy} onClick={()=>setEditingRecipe(r)}>编辑菜谱</button><button className="text-button" disabled={busy} onClick={()=>{if(window.confirm('删除「'+r.name+'」？已有用餐与方案历史会保留。'))void perform(async()=>{await api('/recipes/'+r.id,'DELETE',{expected_version:r.version},crypto.randomUUID());if(editingRecipe?.id===r.id)setEditingRecipe(null);await refresh();});}}>删除菜谱</button></div></section>)}</div></>}
 {tab==='receipts'&&<ReceiptPanel api={api} items={items} onChanged={refresh}/>}
 {tab==='discovery'&&<DiscoveryPanel api={api} items={items} seed={discoverySeed} onChanged={refresh} onRecommend={recommendWith}/>}
 {tab==='shopping'&&<ShoppingPanel key={'shopping:'+token} refreshSignal={shoppingRefresh} api={api} items={items} onChanged={refresh}/>}
 {tab==='history'&&<section className="panel">{history.length===0?<div className="empty"><h2>还没有用餐记录</h2><p>确认做完一道菜后，这里会保留记录。</p></div>:history.map(h=><div className="history-row" id={'meal-'+h.id} tabIndex={-1} key={h.id}><div><h3>{h.recipe.name}</h3><small>{h.servings} 人份 · {h.status==='retracted'?'已撤销':'已完成'} · {h.actual_minutes===null?'未记录用时':h.actual_minutes+' 分钟'}</small>{h.status==='completed'&&<DurationEditor key={h.id} record={h} api={api} onSaved={data=>{setHistory(rows=>rows.map(row=>row.id===h.id?{...row,...data}:row));setNotice('用时已保存，库存未改变');}}/>}</div><button className="secondary" disabled={busy||h.status==='retracted'} onClick={()=>{if(window.confirm('撤销本次用餐，并恢复对应食材数量？'))void perform(async()=>{await mutation('/cooking/'+h.id+'/undo');await refresh();});}}>撤销并恢复食材</button></div>)}</section>}
 {tab==='settings'&&<Preferences api={api} perform={perform} busy={busy} items={items}/>}
 {pending&&<div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title"><p className="eyebrow">确认记录</p><h2 id="confirm-title">已经做完「{pending.recipe.name}」？</h2><p>将记录 {pending.recipe.servings} 人份，并按方案选择扣减库存。直接记录菜谱时默认不使用可选配料。库存不足时整笔操作取消。</p><div className="row"><button className="secondary" disabled={busy} onClick={()=>setPending(null)}>暂不记录</button><button autoFocus disabled={busy} onClick={()=>void perform(async()=>{if(pending.planId){await api('/plans/'+pending.planId+'/confirm','POST',{expected_version:pending.version},pending.key);}else{await api('/cooking','POST',{recipe_id:pending.recipe.id,servings:pending.recipe.servings},pending.key);}setPending(null);await refresh();setNotice('已记录，库存同步更新');})}>确认做完</button></div>{notice&&<p role="alert" className="error">{notice}</p>}</section></div>}
 </main></div>;
}

function Preferences({api,perform,busy,items}:{api:(path:string,method?:string,body?:unknown,key?:string)=>Promise<any>;perform:(action:()=>Promise<void>)=>Promise<void>;busy:boolean;items:Ingredient[]}){
 const [value,setValue]=useState({equipment:[] as string[],excluded_ingredients:[] as string[],default_servings:1,max_minutes:30,personal_time_enabled:true,personalization_enabled:true});
 const [personalization,setPersonalization]=useState<any>(null);
 const edited=useRef(false);
 const edit=(next:typeof value)=>{edited.current=true;setValue(next);};
 useEffect(()=>{void perform(async()=>{const [stored,summary]=await Promise.all([api('/me/preferences'),api('/me/personalization')]);if(!edited.current)setValue(stored);setPersonalization(summary);});},[]);
 return <section className="panel preferences"><h2>厨房偏好</h2><form onSubmit={e=>{e.preventDefault();void perform(async()=>{const saved=await api('/me/preferences','PUT',{...value,equipment:value.equipment.map(x=>x.trim()).filter(Boolean),excluded_ingredients:value.excluded_ingredients.map(x=>x.trim()).filter(Boolean)});setValue(saved);setPersonalization(await api('/me/personalization'));});}}><label>现有厨具（逗号分隔）<input value={value.equipment.join(',')} onChange={e=>edit({...value,equipment:e.target.value.split(/[,，]/)})}/></label><label>不吃的食材（逗号分隔）<input value={value.excluded_ingredients.join(',')} onChange={e=>edit({...value,excluded_ingredients:e.target.value.split(/[,，]/)})}/></label><div className="row"><label>默认人数<input type="number" min="1" max="10" value={value.default_servings} onChange={e=>edit({...value,default_servings:Number(e.target.value)})}/></label><label>最多用时（分钟）<input type="number" min="1" max="480" value={value.max_minutes} onChange={e=>edit({...value,max_minutes:Number(e.target.value)})}/></label></div><label>按我做过的实际用时估计<input type="checkbox" checked={value.personal_time_enabled} onChange={e=>edit({...value,personal_time_enabled:e.target.checked})}/></label><label>按我的习惯个性化推荐<input type="checkbox" checked={value.personalization_enabled} onChange={e=>edit({...value,personalization_enabled:e.target.checked})}/></label><p className="footnote">开启后，完成记录和收藏/评价会影响推荐排序；关闭后恢复原有库存、临期和重复次数排序。它与个人用时估计开关独立。</p><button disabled={busy}>保存偏好</button></form>{personalization&&<div className="preference-summary"><h3>我的偏好摘要</h3><p>{personalization.message} · 最近{personalization.window_days}天完成记录 {personalization.history_count} 条。</p>{personalization.top_ingredients.length>0&&<p>常用食材：{personalization.top_ingredients.map((x:any)=>items.find(i=>i.id===x.ingredient_id)?.name||x.ingredient_id).join('、')}</p>}{personalization.top_methods.length>0&&<p>常用方式：{personalization.top_methods.map((x:any)=>methodName(x.method)).join('、')}</p>}<small>这是基于你的真实完成记录与反馈的可解释摘要，不是模型训练结果。</small></div>}</section>;
}

function RecipeEditor({items,api,perform,busy,refresh,initial,onClose}:{initial:Recipe|null;onClose:()=>void;items:Ingredient[];api:(path:string,method?:string,body?:unknown,key?:string)=>Promise<any>;perform:(action:()=>Promise<void>)=>Promise<void>;busy:boolean;refresh:()=>Promise<void>}){
 const [lines,setLines]=useState(initial?initial.ingredients.map(i=>({ingredient_id:i.ingredient_id,quantity:i.quantity,optional:!!i.optional})):[{ingredient_id:'',quantity:'',optional:false}]);
 const [methods,setMethods]=useState<string[]>(methodsFromStored(initial?.cooking_methods));
 const editKeys=useRef(new Map<string,string>());
 return <details className="panel" open={initial?true:undefined}><summary>{initial?'编辑「'+initial.name+'」':'添加自己的菜谱'}</summary><form onSubmit={e=>{e.preventDefault();const form=e.currentTarget;const f=new FormData(form);void perform(async()=>{const body={...(initial?{expected_version:initial.version}:{}),name:f.get('name'),servings:Number(f.get('servings')),minutes:Number(f.get('minutes')),equipment:String(f.get('equipment')).split(/[,，]/).map(x=>x.trim()).filter(Boolean),source:f.get('source'),steps:String(f.get('steps')).split('\n').map(x=>x.trim()).filter(Boolean),cooking_methods:methods,ingredients:lines.map(line=>({...line,unit:items.find(i=>i.id===line.ingredient_id)?.unit}))};const signature=JSON.stringify(body);let key=editKeys.current.get(signature);if(!key){key=crypto.randomUUID();editKeys.current.set(signature,key);}await api(initial?'/recipes/'+initial.id:'/recipes',initial?'PUT':'POST',body,key);editKeys.current.delete(signature);onClose();form.reset();setLines([{ingredient_id:'',quantity:'',optional:false}]);setMethods([]);await refresh();});}}><label>菜谱名称<input name="name" required maxLength={100} defaultValue={initial?.name}/></label><div className="row"><label>人数<input name="servings" type="number" min="1" max="10" defaultValue={initial?.servings||1} required/></label><label>用时（分钟）<input name="minutes" type="number" min="1" max="480" defaultValue={initial?.minutes||20} required/></label></div><label>厨具（逗号分隔）<input name="equipment" defaultValue={initial?.equipment.join(',')} required placeholder="电饭锅,炒锅"/></label><label>来源<input name="source" required defaultValue={initial?.source||'个人食谱'} maxLength={500}/></label><label>做法（每行一步）<textarea name="steps" defaultValue={initial?.steps.join('\n')} required rows={4}/></label><div className="method-picker"><span>烹饪方式（最多 {MAX_METHODS} 个，用于以后筛选）</span><div className="method-options">{COOKING_METHODS.map(m=><label key={m}><input type="checkbox" checked={methods.includes(m)} disabled={!methods.includes(m)&&methods.length>=MAX_METHODS} onChange={()=>setMethods(old=>toggleMethod(old,m))}/>{methodName(m)}</label>)}</div>{methods.length>0&&<small>已选：{methodText(methods)}</small>}</div><p>用量以以上人数为准，勾选可选配料后，默认不使用；明确选用时才计入需求与扣减。至少保留一种必需食材。</p>{lines.map((line,n)=><div className="row" key={n}><label>食材<select required value={line.ingredient_id} onChange={e=>setLines(lines.map((v,i)=>i===n?{...v,ingredient_id:e.target.value}:v))}><option value="">请选择</option>{items.map(i=><option key={i.id} value={i.id}>{i.name}（{units[i.unit]}）</option>)}</select></label><label>数量<input required type="number" min="0.001" step="0.001" value={line.quantity} onChange={e=>setLines(lines.map((v,i)=>i===n?{...v,quantity:e.target.value}:v))}/></label><label>可选配料<input type="checkbox" checked={line.optional} onChange={e=>setLines(lines.map((v,i)=>i===n?{...v,optional:e.target.checked}:v))}/></label><button type="button" className="secondary" disabled={lines.length===1} onClick={()=>setLines(lines.filter((_,i)=>i!==n))}>移除</button></div>)}<div className="row"><button className="secondary" type="button" disabled={lines.length>=40} onClick={()=>setLines([...lines,{ingredient_id:'',quantity:'',optional:false}])}>增加食材</button><button disabled={busy||!items.length}>保存菜谱</button>{initial&&<button type="button" className="secondary" disabled={busy} onClick={onClose}>取消编辑</button>}</div></form></details>;
}

createRoot(document.getElementById('root')!).render(<App/>);
