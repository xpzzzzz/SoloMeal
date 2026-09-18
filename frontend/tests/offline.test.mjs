import test from 'node:test';
import assert from 'node:assert/strict';
import {NetworkError,browserOnline,sessionJson,watchBrowserOnline} from '../.test-build/session.js';

// Node has a global navigator without onLine, so the property is replaced for these cases.
function withNavigator(onLine,run){
 const original=Object.getOwnPropertyDescriptor(globalThis,'navigator');
 try{
  Object.defineProperty(globalThis,'navigator',{value:{onLine},configurable:true,writable:true});
  return run();
 }finally{
  if(original)Object.defineProperty(globalThis,'navigator',original);else delete globalThis.navigator;
 }
}

async function messageFrom(online,fetchImpl){
 const original=globalThis.fetch;
 globalThis.fetch=fetchImpl;
 try{
  return await withNavigator(online,async()=>{
   try{await sessionJson('/inventory',{},()=>true,()=>online);return '';}
   catch(error){return error instanceof Error?error.message:'';}
  });
 }finally{globalThis.fetch=original;}
}

test('an offline browser explains itself without sending the request',async()=>{
 let calls=0;
 const message=await messageFrom(false,async()=>{calls++;return new Response('{}');});
 assert.equal(calls,0);
 assert.match(message,/浏览器已离线/);
});

test('a connection failure while online is not blamed on the browser',async()=>{
 const message=await messageFrom(true,async()=>{throw new TypeError('Failed to fetch');});
 assert.match(message,/无法连接服务器/);
});

test('a non-network error keeps its own type',async()=>{
 const original=globalThis.fetch;
 globalThis.fetch=async()=>{throw new RangeError('too big');};
 try{await assert.rejects(sessionJson('/inventory',{},()=>true,()=>true),RangeError);}finally{globalThis.fetch=original;}
});

test('the watcher reports both directions and cleans up',()=>{
 const original=globalThis.window,seen=[];
 globalThis.window={addEventListener:(name,handler)=>seen.push(['add',name,handler]),removeEventListener:name=>seen.push(['remove',name])};
 try{
  const changes=[];
  const stop=watchBrowserOnline(value=>changes.push(value));
  assert.deepEqual(seen.filter(s=>s[0]==='add').map(s=>s[1]),['online','offline']);
  seen.find(s=>s[1]==='offline')[2]();
  seen.find(s=>s[1]==='online')[2]();
  assert.deepEqual(changes,[false,true]);
  stop();
  assert.deepEqual(seen.filter(s=>s[0]==='remove').map(s=>s[1]),['online','offline']);
 }finally{delete globalThis.window;}
});
