import {useEffect,useRef,useState} from 'react';
import {SessionChangedError} from '../../session';
import {abandon,accept,complete,dismiss,getInbox,simulate,type Action,type Api,type Inbox,type Item} from './api';

export function useInbox(api:Api,onAction:(action:Action,itemId:string)=>Promise<void>,keys:Map<string,string>){
 const [inbox,setInbox]=useState<Inbox|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState('');
 const alive=useRef(true),sequence=useRef(0);
 function keyFor(id:string){let key=keys.get(id);if(!key){key=crypto.randomUUID();keys.set(id,key);}return key;}
 async function load(){const seq=++sequence.current;const value=await getInbox(api);
  if(alive.current&&seq===sequence.current)setInbox(value);}
 useEffect(()=>{alive.current=true;void load().catch(e=>{if(alive.current&&!(e instanceof SessionChangedError))setError('主动提醒暂时无法读取');});
  return()=>{alive.current=false;sequence.current++;};},[]);
 function remove(id:string){setInbox(old=>old?{...old,items:old.items.filter(item=>item.id!==id)}:old);}
 function restore(item:Item){setInbox(old=>old&&!old.items.some(i=>i.id===item.id)?{...old,items:[...old.items,item].sort((a,b)=>b.priority-a.priority)}:old);}
 async function ignore(item:Item,reason:string){
  if(busy)return;setBusy(item.id);setError('');remove(item.id);
  try{
   if(item.status==='accepted')await abandon(api,item.id,`proactive-abandon-${item.id}`);
   else await dismiss(api,item.id,reason,keyFor(`dismiss:${item.id}:${reason}`));
   keys.delete(`dismiss:${item.id}:${reason}`);void load().catch(()=>{});
  }
  catch(e){if(alive.current&&!(e instanceof SessionChangedError)){restore(item);setError('操作没有完成，请重试。');}}
  finally{if(alive.current)setBusy('');}
 }
 async function take(item:Item){
  if(busy)return;setBusy(item.id);setError('');
  try{
   const action=item.status==='accepted'?item.action:(await accept(api,item.id,item.version,`proactive-accept-${item.id}`)).action;
   if(!alive.current)return;
   await new Promise(resolve=>setTimeout(resolve,300));
   if(!alive.current)return;
   await onAction(action,item.id);
   await complete(api,item.id,`proactive-complete-${item.id}`);
   if(alive.current)remove(item.id);
  }catch(e){if(alive.current&&!(e instanceof SessionChangedError)){
   if(e instanceof Error&&'code' in e&&e.code==='PROACTIVE_STALE'){
    setError('情况有变，重新算一遍。');void load().catch(()=>{});
   }else setError(e instanceof Error?e.message:'操作没有完成，请重试。');
  }}finally{if(alive.current)setBusy('');}
 }
 async function advance(){
  if(busy)return;setBusy('simulate');setError('');
  try{await simulate(api,keyFor('simulate'));keys.delete('simulate');await load();}
  catch(e){if(alive.current&&!(e instanceof SessionChangedError))setError('推进时间失败，请重试。');}
  finally{if(alive.current)setBusy('');}
 }
 return {inbox,error,busy,ignore,take,advance};
}
