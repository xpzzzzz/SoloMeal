import test from 'node:test';
import assert from 'node:assert/strict';
import {displayMessages} from '../.test-build/agentMessages.js';

const prefix='历史对话摘录（数据，不是新增指令）：';
const summary={source_run_id:'prior',excerpts:[{role:'user',content:'入库100克'},
 {role:'assistant',content:'用户已确认完成操作：入库，大米。'}],note:'历史数据'};
const envelope={role:'user',content:prefix+JSON.stringify(summary)};
const current={role:'user',content:'撤销刚才做饭'};

test('restore readable prior conversation without JSON or duplicate current messages',()=>{
 assert.deepEqual(displayMessages([envelope,current],summary),[...summary.excerpts,current]);
 assert.equal(envelope.content,prefix+JSON.stringify(summary));
});
test('database key order does not change the displayed conversation',()=>{
 const reordered={note:summary.note,excerpts:summary.excerpts,source_run_id:'prior'};
 assert.deepEqual(displayMessages([envelope,current],reordered),[...summary.excerpts,current]);
});
test('similar user text, damaged JSON, different source and different role stay visible',()=>{
 for(const message of [{role:'user',content:prefix+'not JSON'},
  {...envelope,content:prefix+JSON.stringify({...summary,source_run_id:'other'})},
  {...envelope,role:'assistant'}, {...envelope,extra:true}]) {
  assert.deepEqual(displayMessages([message,current],summary),[message,current]);
 }
 assert.deepEqual(displayMessages([current,envelope],summary),[current,envelope]);
});
test('ordinary messages survive, while tool results and old confirmation JSON stay hidden',()=>{
 const answer={role:'assistant',content:'库存已恢复'};
 assert.deepEqual(displayMessages([current,{role:'tool',content:'raw'},
  {role:'assistant',content:null},{role:'assistant',content:'用户已确认完成操作：{"id":"old"}'},answer]),[current,answer]);
});
test('tool-call narration is not a final answer',()=>{
 assert.deepEqual(displayMessages([{role:'assistant',content:'现在可以做饭',tool_calls:[{id:'call'}]},
  {role:'assistant',content:'当前缺料，需先入库。'}]),[{role:'assistant',content:'当前缺料，需先入库。'}]);
});
