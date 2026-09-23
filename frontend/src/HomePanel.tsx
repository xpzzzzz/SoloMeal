import React, {useEffect, useRef, useState} from 'react';
import {SessionChangedError} from './session';
import {errorText} from './errorText';
import RecommendationPanel from './RecommendationPanel';
import {attentionSummary, attentionText, emptyText, expiryTag, READ_ONLY_SECTIONS, recentSummary, recentText,
 sectionTitle, shoppingSummary, shoppingText} from './homeText';

type Api=(path:string,method?:string,body?:unknown,key?:string)=>Promise<any>;
type Section={status:string;data?:any;error?:{code?:string;message?:string}};
type Home={as_of:string;display_date:string;timezone:string;sections:Record<string,Section>};
type Rating='neutral'|'like'|'dislike';
type Saved={favorite:boolean;rating:Rating;version:number};

const ORDER=['attention','recommendations','shopping','recent'];
const HINTS:Record<string,string>={attention:'三天内到期与已过期',recommendations:'来自现有推荐服务',
 shopping:'未完成的采购清单',recent:'最近完成的用餐记录'};
const text=(e:unknown)=>e instanceof Error&&e.message?e.message:'这一栏暂时读不到，请稍后重试';

export default function HomePanel({api,emptyAccount,onImport,goTo,onHistory,preferenceText,onCook,onAdd,onSave,
onSettings,onDiscover,favorite}:{
 api:Api;emptyAccount:boolean;onImport:()=>Promise<void>;goTo:(tab:string)=>void;onHistory:(id:string)=>void;
 preferenceText:(candidate:any)=>string;onCook:(candidate:any)=>void;onAdd:(candidate:any)=>void;
 onSave:(candidate:any,request:any)=>Promise<void>;onSettings:()=>void;onDiscover:(constraints:any)=>void;
 favorite:(candidate:any,next:{favorite:boolean;rating:Rating})=>Promise<Saved>;
}){
 const [home,setHome]=useState<Home|null>(null);
 const [recos,setRecos]=useState<any>(null);
 const [favorites,setFavorites]=useState<Record<string,Saved>>({});
 const [busy,setBusy]=useState(false),[retrying,setRetrying]=useState(''),[notice,setNotice]=useState('');
 const [loadError,setLoadError]=useState('');
 const alive=useRef(true),edited=useRef(false),loadSeq=useRef(0);
 const say=(message:string)=>{if(alive.current)setNotice(message);};
 function apply(name:string,section:Section){
  if(!alive.current)return;
  setHome(old=>old?{...old,sections:{...old.sections,[name]:section}}:old);
  // A block that arrives late must not replace conditions the user has already changed.
  if(name==='recommendations'&&section.status==='ok'&&!edited.current){
   setRecos({...section.data,manualMinutes:null});
   setFavorites(section.data.favorites||{});
  }
 }
 async function retry(name:string){
  setRetrying(name);setNotice('');
  try{
   const one=await api('/home/'+name);
   apply(name,{status:one.status,data:one.data,error:one.error});
  }catch(e){if(!(e instanceof SessionChangedError))say(text(e));}
  finally{if(alive.current)setRetrying('');}
 }
 async function loadHome(retryingLoad=false){
  const sequence=++loadSeq.current;
  if(retryingLoad)setBusy(true);
  setLoadError('');setNotice('');
  try{
   const data:Home=await api('/home');
   if(!alive.current||sequence!==loadSeq.current)return;
   setHome(data);
   const section=data.sections.recommendations;
   if(section?.status==='ok')apply('recommendations',section);
   if(retryingLoad)say('今天的数据已更新。');
  }catch(e){if(alive.current&&sequence===loadSeq.current&&!(e instanceof SessionChangedError))setLoadError(text(e));}
  finally{if(retryingLoad&&alive.current&&sequence===loadSeq.current)setBusy(false);}
 }
 async function refresh(){
  if(!home){await loadHome(true);return;}
  setBusy(true);setNotice('');
  try{
   const data:Home=await api('/home?sections='+READ_ONLY_SECTIONS.join(','));
   ORDER.filter(n=>n!=='recommendations'&&data.sections[n]).forEach(n=>apply(n,data.sections[n]));
   say('今天的数据已更新，推荐条件保持不变。');
  }catch(e){if(!(e instanceof SessionChangedError))say(text(e));}
  finally{if(alive.current)setBusy(false);}
 }
 async function mark(candidate:any,next:{favorite:boolean;rating:Rating}){
  const saved=await favorite(candidate,next);
  if(!alive.current)return saved;
  setFavorites(old=>({...old,[candidate.recipe.id]:saved}));
  say(next.favorite?'已收藏「'+candidate.recipe.name+'」，可在我的菜谱里只看收藏。':'已取消收藏「'+candidate.recipe.name+'」。');
  return saved;
 }
 useEffect(()=>{
  alive.current=true;edited.current=false;
  void loadHome();
  return()=>{alive.current=false;loadSeq.current++;};
 },[]);
 const sections=home?.sections;
 const block=(name:string,children:React.ReactNode,footer?:React.ReactNode)=>{
  const section=sections?.[name];
  return <section className={'panel home-section home-'+name}>
   <div className="panel-heading"><h2>{sectionTitle(name)}</h2><span className="muted">{HINTS[name]}</span></div>
   {!section?<p role={loadError?'alert':'status'} className="muted">{loadError?'首页读取失败，请重试首页。':'正在读取…'}</p>
    :section.status!=='ok'?<><p role="alert">{errorText(section.error)}</p>
     <button className="secondary" disabled={!!retrying} onClick={()=>void retry(name)}>重试这一栏</button></>
    :children}
   {section?.status==='ok'&&footer}
  </section>;
 };
 const attention=sections?.attention?.data, shopping=sections?.shopping?.data, recent=sections?.recent?.data;
 return <div className="home">
  <section className="panel home-head"><p className="eyebrow">今天 · {home?.display_date||'…'}</p>
   <p>四块内容分别读取：任何一块失败，其余照常显示，可以单独重试。</p>
   <div className="row"><button className="secondary" disabled={busy} onClick={()=>void refresh()}>{loadError?'重试首页':'刷新今天'}</button>
    <button className="secondary" disabled={busy} onClick={()=>goTo('inventory')}>去库存处理</button></div>
   {loadError&&<p role="alert">{loadError}</p>}
   {notice&&<p role="status">{notice}</p>}
   <p className="footnote">是否过期由服务端按 UTC 判断，页面按 Asia/Shanghai 显示“今天”。到期日期来自你的记录，只用于提醒，不是食品安全结论。</p></section>
  {emptyAccount&&<section className="panel home-start"><h2>先把厨房装起来</h2>
   <p>下面三个入口都要你点击才会执行：导入示例菜谱只添加菜谱，不会替你增加库存，也不会生成用餐记录。</p>
   <div className="row"><button className="secondary" onClick={()=>goTo('inventory')}>添加库存</button>
    <button className="secondary" onClick={()=>goTo('discovery')}>去发现菜谱</button>
    <button className="secondary" onClick={()=>goTo('recipes')}>录入菜谱</button>
    <button disabled={busy} onClick={()=>void (async()=>{setBusy(true);setNotice('');try{await onImport();say('示例菜谱已就绪：库存和用餐记录还需要你按实际填写。');}catch(e){if(!(e instanceof SessionChangedError))say(text(e));}finally{if(alive.current)setBusy(false);}})()}>导入示例菜谱</button></div></section>}
  {block('attention',attention?.items?.length?<ul className="home-attention">{attention.items.map((row:any)=>
    <li key={row.batch_id}><span>{attentionText(row)}</span><span className={'tag '+(row.state==='expired'?'expired':'expiring_soon')}>{expiryTag(row.state)}</span></li>)}
   </ul>:<p className="muted">{emptyText('attention')}</p>,
  attention?.items?.length?<><p>{attentionSummary(attention)}</p>
   <p className="footnote">已过期批次不再参与推荐和做饭扣减，请检查后调整数量或归档。</p>
   <div className="row"><button className="secondary" onClick={()=>goTo('inventory')}>处理库存</button></div></>:undefined)}
  {block('recommendations',<RecommendationPanel api={api} result={recos}
   onResult={value=>{edited.current=true;setRecos(value);}} preferenceText={preferenceText} onCook={onCook}
   onAdd={onAdd} onSave={onSave} onSettings={onSettings} onDiscover={onDiscover} favorites={favorites}
   onFavorite={mark}/>)}
  {block('shopping',shopping?.items?.length?<><ul className="home-shopping">{shopping.items.map((list:any)=>
    <li key={list.id}><button className="text-button" onClick={()=>goTo('shopping')}>{shoppingText(list)}</button></li>)}</ul>
   <p>{shoppingSummary(shopping)}</p></>:<p className="muted">{emptyText('shopping')}</p>,
  shopping?.items?.length?<div className="row"><button className="secondary" onClick={()=>goTo('shopping')}>打开报价与采购</button></div>:undefined)}
  {block('recent',recent?.items?.length?<ul className="home-recent">{recent.items.map((row:any)=>
    <li key={row.id}><button className="text-button" onClick={()=>onHistory(row.id)}>{recentText(row)}</button></li>)}</ul>
   :<p className="muted">{emptyText('recent')}</p>,
  recent?.items?.length?<p>{recentSummary(recent)}</p>:undefined)}
 </div>;
}
