import React, {useState} from 'react';
import type {Action,Api} from './api';
import {ProactiveCard} from './ProactiveCard';
import {useInbox} from './useInbox';

export default function ProactiveInbox({api,onAction,keys}:{api:Api;onAction:(action:Action,itemId:string)=>Promise<void>;keys:Map<string,string>}){
 const {inbox,error,busy,ignore,take,advance}=useInbox(api,onAction,keys);
 const [expanded,setExpanded]=useState(false);
 if(!inbox?.items.length&&!inbox?.meta.demo_mode&&!error)return null;
 const items=inbox?.items||[],visible=expanded?items:items.slice(0,1);
 return <section className="proactive-inbox" aria-label="主动提醒">
  {visible.map(item=><ProactiveCard key={item.id} item={item} busy={!!busy}
   onAccept={()=>void take(item)} onDismiss={reason=>void ignore(item,reason)}/>)}
  {items.length>1&&<button className="text-button" onClick={()=>setExpanded(!expanded)}>{expanded?'收起':`还有 ${items.length-1} 条`}</button>}
  {inbox?.meta.demo_mode&&Object.entries(inbox.meta.suppression_until).map(([kind,date])=>
   <p key={kind} role="status">{kind==='shopping_stale'?'采购草稿':kind==='expiring_batch'?'临期食材':kind}提醒已暂停至 {date}</p>)}
  {inbox?.meta.demo_mode&&<button className="secondary" disabled={!!busy} onClick={()=>void advance()}>⏩ 推进 1 天</button>}
  {error&&<p role="alert">{error}</p>}
 </section>;
}
