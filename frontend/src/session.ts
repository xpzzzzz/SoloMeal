export class SessionChangedError extends Error {
 constructor(){super('登录会话已切换');}
}

// A failed fetch is not a business error: the browser says "Failed to fetch" in English,
// so the request boundary translates it into something the user can act on.
export class NetworkError extends Error {
 constructor(offline:boolean){super(offline?'浏览器已离线，恢复网络后可重试':'无法连接服务器，请检查网络后重试');}
}

export const browserOnline=()=>typeof navigator==='undefined'||navigator.onLine!==false;

const lists=new Set(['/ingredients','/inventory','/inventory/events','/recipes','/cooking','/plans','/quotes','/shopping','/receipts','/agent/runs','/agent/sessions','/recipe-drafts','/recipe-discoveries']);

// Existing panels need complete lists for selectors and totals. Read bounded pages,
// and fail visibly instead of silently presenting a truncated list as complete.
export async function pagedList(path:string,read:(path:string)=>Promise<any>){
 const url=new URL(path,'http://local');
 if((!lists.has(url.pathname)&&!/^\/plans\/[^/]+\/revisions$/.test(url.pathname))||url.searchParams.has('limit')||url.searchParams.has('offset'))return read(path);
 const rows:any[]=[];
 for(let offset=0;offset<=10000;offset+=200){
  url.searchParams.set('limit','200');url.searchParams.set('offset',String(offset));
  const page=await read(url.pathname+url.search);
  if(!Array.isArray(page))throw new Error('列表响应异常，请刷新重试');
  rows.push(...page);
  if(rows.length>10000)throw new Error('记录超过当前页面加载上限，请缩小数据范围后重试');
  if(page.length<200)return rows;
 }
 throw new Error('记录超过当前页面加载上限');
}

// The listeners are separate from the online state so a page can show a banner without touching fetch.
export function watchBrowserOnline(onChange:(online:boolean)=>void){
 if(typeof window==='undefined')return()=>{};
 const online=()=>onChange(true),offline=()=>onChange(false);
 window.addEventListener('online',online);
 window.addEventListener('offline',offline);
 return()=>{window.removeEventListener('online',online);window.removeEventListener('offline',offline);};
}

// The body can finish after logout or a later login, even when fetch already resolved.
export async function sessionJson(url:string,init:RequestInit,isCurrent:()=>boolean,isOnline=browserOnline,readBody?:(response:Response)=>Promise<any>){
 if(!isCurrent())throw new SessionChangedError();
 if(!isOnline())throw new NetworkError(true);
 try{
  const response=await fetch(url,init);
  const data=response.status===204?null:await (readBody?readBody(response):response.json());
  if(!isCurrent())throw new SessionChangedError();
  return {response,data};
 }catch(error){
  if(!isCurrent())throw new SessionChangedError();
  if(error instanceof TypeError)throw new NetworkError(!isOnline());
  throw error;
 }
}
