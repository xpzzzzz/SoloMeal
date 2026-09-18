import test from 'node:test';
import assert from 'node:assert/strict';
import {SSEParser,watchRun} from '../.test-build/sse.js';
test('split UTF-8 and CRLF frames preserve cursor and data',()=>{
 const parser=new SSEParser(),decoder=new TextDecoder();
 const bytes=new TextEncoder().encode(': heartbeat\r\n\r\nid: run:2\r\nevent: run_state\r\ndata: {"文本":"完成"}\r\n\r\n');
 const received=[];for(const byte of bytes)received.push(...parser.feed(decoder.decode(new Uint8Array([byte]),{stream:true})));
 assert.deepEqual(received,[{id:'run:2',event:'run_state',data:'{"文本":"完成"}'}]);
});
test('multiple frames, multiline data and partial trailing frame',()=>{
 const parser=new SSEParser();
 assert.deepEqual(parser.feed('data: first\ndata: second\n\nevent: stream_end\ndata: {"reconnect":false}\n\nid: pending'),[{id:undefined,event:'message',data:'first\nsecond'},{id:undefined,event:'stream_end',data:'{"reconnect":false}'}]);
 assert.deepEqual(parser.feed('\ndata: last\n\n'),[{id:'pending',event:'message',data:'last'}]);
});

test('reconnect sends cursor and ignores repeated events',async()=>{
 const original=globalThis.fetch;const cursors=new Map();let calls=0,updates=0;
 globalThis.fetch=async(url,options)=>{
  assert.equal(url,'/api/v1/agent/runs/run/events');
  assert.equal(options.headers.Authorization,'Bearer local-test-token');
  calls++;
  if(calls===1){assert.equal(options.headers['Last-Event-ID'],undefined);return new Response('id: run:1\nevent: run_state\ndata: {}\n\n');}
  assert.equal(options.headers['Last-Event-ID'],'run:1');
  return new Response('id: run:1\nevent: run_state\ndata: {}\n\nid: run:2\nevent: run_state\ndata: {}\n\nevent: stream_end\ndata: {"reconnect":false}\n\n');
 };
 try{await watchRun('run','local-test-token',cursors,new AbortController().signal,async()=>{updates++;});assert.equal(calls,2);assert.equal(updates,2);assert.equal(cursors.get('run'),'run:2');}finally{globalThis.fetch=original;}
});
