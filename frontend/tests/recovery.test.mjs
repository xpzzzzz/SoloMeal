import test from 'node:test';
import assert from 'node:assert/strict';
import {watchRun} from '../.test-build/sse.js';

test('aborting during state read does not acknowledge an unapplied event',async()=>{
 const original=globalThis.fetch,controller=new AbortController(),cursors=new Map();
 globalThis.fetch=async()=>new Response('id: run:1\nevent: run_state\ndata: {}\n\n');
 try{await watchRun('run','test',cursors,controller.signal,async()=>controller.abort());assert.equal(cursors.has('run'),false);}finally{globalThis.fetch=original;}
});

test('four consecutive failures stop and a manual restart can recover',async()=>{
 const original=globalThis.fetch;let calls=0;const cursors=new Map(),states=[];
 globalThis.fetch=async()=>{calls++;throw new TypeError('offline');};
 try{
  await assert.rejects(watchRun('run','test',cursors,new AbortController().signal,async()=>{},s=>states.push(s)),/offline/);
  assert.equal(calls,4);assert.equal(states.at(-1),'stopped');
  globalThis.fetch=async()=>new Response('id: run:1\nevent: run_state\ndata: {}\n\nevent: stream_end\ndata: {"reconnect":false}\n\n');
  let updates=0;await watchRun('run','test',cursors,new AbortController().signal,async()=>{updates++;});assert.equal(updates,1);assert.equal(cursors.get('run'),'run:1');
 }finally{globalThis.fetch=original;}
});

test('broken stream and failed state read preserve only applied cursor',async()=>{
 const original=globalThis.fetch,cursors=new Map();let calls=0,updates=0;const states=[];
 globalThis.fetch=async(url,options)=>{
  calls++;
  if(calls===1)return new Response(new ReadableStream({start(c){c.error(new TypeError('network lost'));}}));
  assert.equal(options.headers['Last-Event-ID'],calls===2?undefined:'run:1');
  return new Response('id: run:1\nevent: run_state\ndata: {}\n\nid: run:2\nevent: run_state\ndata: {}\n\nevent: stream_end\ndata: {"reconnect":false}\n\n');
 };
 try{
  await watchRun('run','test',cursors,new AbortController().signal,async()=>{updates++;if(updates===2)throw new TypeError('state fetch lost');},s=>states.push(s));
  assert.equal(calls,3);assert.equal(updates,3);assert.equal(cursors.get('run'),'run:2');assert.ok(states.includes('reconnecting'));
 }finally{globalThis.fetch=original;}
});

test('expired authentication stops without repeating requests',async()=>{
 const original=globalThis.fetch;let calls=0;
 try{for(const response of [new Response('',{status:401}),new Response('event: auth_expired\ndata: {}\n\n')]){
  globalThis.fetch=async()=>{calls++;return response;};const states=[];
  await assert.rejects(watchRun('run','test',new Map(),new AbortController().signal,async()=>assert.fail('no update'),s=>states.push(s)),/登录已失效/);
  assert.equal(states.at(-1),'stopped');
 }assert.equal(calls,2);}finally{globalThis.fetch=original;}
});

test('aborting reconnect stops further reads and callbacks',async()=>{
 const original=globalThis.fetch,controller=new AbortController();let calls=0;
 globalThis.fetch=async()=>{calls++;throw new TypeError('offline');};
 try{await watchRun('run','test',new Map(),controller.signal,async()=>assert.fail('no update'),state=>{if(state==='reconnecting')controller.abort();});assert.equal(calls,1);}finally{globalThis.fetch=original;}
});
