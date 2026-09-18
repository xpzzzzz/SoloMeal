import test from 'node:test';
import assert from 'node:assert/strict';
import {sessionJson,SessionChangedError} from '../.test-build/session.js';

function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}

test('late 401 from a logged out session cannot invalidate the next login',async()=>{
 const original=globalThis.fetch,old=deferred();let current='first',invalidations=0;
 globalThis.fetch=()=>old.promise;
 try{
  const request=sessionJson('/old',{},()=>current==='first').then(({response})=>{if(response.status===401)invalidations++;});
  current='second';
  old.resolve(new Response('{}',{status:401}));
  await assert.rejects(request,SessionChangedError);
  assert.equal(invalidations,0);
  globalThis.fetch=async()=>new Response('{"user":"second"}');
  assert.equal((await sessionJson('/new',{},()=>current==='second')).data.user,'second');
 }finally{globalThis.fetch=original;}
});

test('switching login while the response body loads discards old user data',async()=>{
 const original=globalThis.fetch,body=deferred();let current=true;
 globalThis.fetch=async()=>({status:200,json:()=>body.promise});
 try{
  const request=sessionJson('/inventory',{},()=>current);
  await Promise.resolve();current=false;body.resolve({privateInventory:'old user'});
  await assert.rejects(request,SessionChangedError);
 }finally{globalThis.fetch=original;}
});

test('an old continuation cannot dispatch another request after logout',async()=>{
 const original=globalThis.fetch;let calls=0;
 globalThis.fetch=async()=>{calls++;return new Response('{}');};
 try{await assert.rejects(sessionJson('/advance',{method:'POST'},()=>false),SessionChangedError);assert.equal(calls,0);}finally{globalThis.fetch=original;}
});

test('private image body finishing after logout cannot reach the next session',async()=>{
 const original=globalThis.fetch,body=deferred();let current=true;
 globalThis.fetch=async()=>({status:200,blob:()=>body.promise});
 try{
  const request=sessionJson('/receipts/file',{},()=>current,()=>true,response=>response.blob());
  await Promise.resolve();current=false;body.resolve(new Blob(['private receipt']));
  await assert.rejects(request,SessionChangedError);
 }finally{globalThis.fetch=original;}
});
