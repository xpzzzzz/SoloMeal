export type Api=(path:string,method?:string,body?:unknown,key?:string)=>Promise<any>;
export type Action={type:'open_plan_flow';recipe_id:string;prefill:{servings:number}}
 |{type:'open_shopping';shopping_id:string}|{type:'open_inventory';batch_id:string};
export type Item={id:string;kind:string;title:string;body:string;why:string;suppress_hint:string;
 action:Action;status:'pending'|'accepted';version:number;priority:number};
export type Inbox={items:Item[];meta:{demo_mode:boolean;pending_total:number;suppressed_kinds:string[];suppression_until:Record<string,string>}};
export const getInbox=(api:Api):Promise<Inbox>=>api('/proactivity/inbox');
export const dismiss=(api:Api,id:string,reason:string,key:string)=>api(`/proactivity/items/${id}/dismiss`,'POST',{reason},key);
export const accept=(api:Api,id:string,version:number,key:string)=>api(`/proactivity/items/${id}/accept`,'POST',{expected_version:version},key);
export const complete=(api:Api,id:string,key:string)=>api(`/proactivity/items/${id}/complete`,'POST',{},key);
export const abandon=(api:Api,id:string,key:string)=>api(`/proactivity/items/${id}/abandon`,'POST',{},key);
export const patchSettings=(api:Api,body:unknown,key:string)=>api('/proactivity/settings','PATCH',body,key);
export const simulate=(api:Api,key:string)=>api('/proactivity/simulate','POST',{days:1},key);
