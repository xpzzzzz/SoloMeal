import test from 'node:test';
import assert from 'node:assert/strict';
import {pagedList,sessionJson,SessionChangedError} from '../.test-build/session.js';

test('reads every page, preserves filters and handles exact page boundaries',async()=>{
 const calls=[];
 const result=await pagedList('/inventory?include_archived=true',async path=>{
  const url=new URL(path,'http://local');calls.push(url);
  return Number(url.searchParams.get('offset'))===0?Array.from({length:200},(_,id)=>({id})):[];
 });
 assert.equal(result.length,200);assert.equal(calls.length,2);
 assert.equal(calls[1].searchParams.get('offset'),'200');
 assert.equal(calls[1].searchParams.get('include_archived'),'true');
});

test('detail and explicit page requests are not expanded',async()=>{
 for(const path of ['/receipts/capabilities','/agent/runs/id','/inventory?limit=5']){
  const calls=[];assert.equal(await pagedList(path,async p=>{calls.push(p);return 'single';}),'single');
  assert.deepEqual(calls,[path]);
 }
});

test('a later page failure never returns partial inventory or retries writes',async()=>{
 let calls=0;
 await assert.rejects(pagedList('/ingredients',async()=>{if(calls++)throw new Error('429');return Array(200).fill({});}),/429/);
 assert.equal(calls,2);
});

test('logout between pages stops reads before the next dispatch',async()=>{
 const original=globalThis.fetch;let current=true,calls=0;
 globalThis.fetch=async()=>{calls++;return new Response(JSON.stringify(Array(200).fill({})));};
 try{
  await assert.rejects(pagedList('/recipes',async path=>{
   const {data}=await sessionJson(path,{},()=>current,()=>true);current=false;return data;
  }),SessionChangedError);
  assert.equal(calls,1);
 }finally{globalThis.fetch=original;}
});

test('large lists fail explicitly instead of silently truncating',async()=>{
 let calls=0;
 await assert.rejects(pagedList('/cooking',async()=>{calls++;return Array(200).fill({});}),/上限/);
 assert.equal(calls,51);
});
