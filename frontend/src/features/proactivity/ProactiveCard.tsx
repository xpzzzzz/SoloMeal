import React from 'react';
import type {Item} from './api';
import {WhyRow} from './WhyRow';

export function ProactiveCard({item,busy,onAccept,onDismiss}:{item:Item;busy:boolean;onAccept:()=>void;onDismiss:(reason:string)=>void}){
 return <article className={'proactive-card'+(busy?' proactive-busy':'')}><h2>{item.title}</h2><p>{item.body}</p>
  <WhyRow why={item.why} hint={item.suppress_hint} onSuppress={item.status==='pending'?()=>onDismiss('too_often'):undefined} disabled={busy}/>
  <div className="row"><button disabled={busy} onClick={onAccept}>{item.status==='accepted'?'继续处理':'就做这个'}</button>
   <button className="secondary" disabled={busy} onClick={()=>onDismiss('not_useful')}>{item.status==='accepted'?'不再继续':'不是这个'}</button></div></article>;
}
