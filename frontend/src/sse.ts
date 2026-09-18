export type ServerEvent={id?:string;event:string;data:string};
export class SSEParser{
 private buffer='';
 feed(chunk:string):ServerEvent[]{
  this.buffer+=chunk;
  if(this.buffer.length>1_000_000)throw new Error('事件数据过大');
  const events:ServerEvent[]=[];
  for(;;){const match=/\r?\n\r?\n/.exec(this.buffer);if(!match)break;const frame=this.buffer.slice(0,match.index);this.buffer=this.buffer.slice(match.index+match[0].length);let id:string|undefined,event='message';const data:string[]=[];
   for(const line of frame.split(/\r?\n/)){if(line.startsWith(':'))continue;const colon=line.indexOf(':');const key=colon<0?line:line.slice(0,colon);let value=colon<0?'':line.slice(colon+1);if(value.startsWith(' '))value=value.slice(1);if(key==='id'&&!value.includes('\0'))id=value;else if(key==='event')event=value;else if(key==='data')data.push(value);}
   if(data.length)events.push({id,event,data:data.join('\n')});
  }return events;
 }
}
export type ConnectionState='connecting'|'connected'|'reconnecting'|'stopped';
class AuthenticationError extends Error{}
export async function watchRun(runId:string,token:string,cursors:Map<string,string>,signal:AbortSignal,onState:()=>Promise<void>,onConnection:(state:ConnectionState)=>void=()=>{}){
 let failures=0;
 onConnection('connecting');
 while(!signal.aborted){
  try{
   const cursor=cursors.get(runId);
   const response=await fetch('/api/v1/agent/runs/'+runId+'/events',{headers:{Authorization:'Bearer '+token,...(cursor?{'Last-Event-ID':cursor}:{})},signal});
   if(response.status===401)throw new AuthenticationError('登录已失效，请重新登录');
   if(!response.ok||!response.body)throw new Error('进度连接失败');
   if(signal.aborted)return;
   onConnection('connected');
   const reader=response.body.getReader(),decoder=new TextDecoder(),parser=new SSEParser();let reconnect=true;
   try{for(;;){const part=await reader.read();if(part.done)break;for(const event of parser.feed(decoder.decode(part.value,{stream:true}))){
     if(signal.aborted)return;
     if(event.event==='auth_expired')throw new AuthenticationError('登录已失效，请重新登录');
     if(event.event==='stream_end')reconnect=JSON.parse(event.data).reconnect;
     if(event.event==='run_state'&&event.id){const previous=cursors.get(runId);if(previous&&Number(event.id.split(':')[1])<=Number(previous.split(':')[1]))continue;await onState();if(signal.aborted)return;cursors.set(runId,event.id);}
   }}}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
   failures=0;if(!reconnect)return;
  }catch(error){if(signal.aborted)return;if(error instanceof AuthenticationError||++failures>=4){onConnection('stopped');throw error;}}
  onConnection('reconnecting');
  if(signal.aborted)return;
  await new Promise<void>(resolve=>{const done=()=>{clearTimeout(timer);signal.removeEventListener('abort',done);resolve();};const timer=setTimeout(done,1000*Math.max(1,failures));signal.addEventListener('abort',done,{once:true});});
 }
}
