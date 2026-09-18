import test from 'node:test';
import assert from 'node:assert/strict';
import {errorText} from '../.test-build/errorText.js';

test('a 409 RUN_NOT_READY is shown in Chinese without the server English text',()=>{
 const text=errorText({code:'RUN_NOT_READY',message:'Run is not ready to advance'});
 assert.match(text,/当前运行状态无法继续/);
 assert.ok(!text.includes('Run is not ready'));
});

test('run-level failures render by code even when the server sends no message',()=>{
 for(const code of ['STEP_LIMIT','MODEL_UNAVAILABLE','MODEL_PROTOCOL_ERROR','CONTEXT_LIMIT'])
  assert.ok(errorText({code}).length>0&&/[一-鿿]/.test(errorText({code})),code);
 assert.match(errorText({code:'MODEL_NOT_CONFIGURED'}),/尚未配置模型/);
});

// Retry sets the run back to ready without resetting steps, so recovering a STEP_LIMIT
// run fails again immediately; the copy must not recommend a dead-end action.
test('STEP_LIMIT recommends a new conversation instead of continuing or retrying',()=>{
 const text=errorText({code:'STEP_LIMIT'});
 assert.match(text,/开始新对话/);
 assert.ok(!text.includes('继续执行')&&!text.includes('恢复执行'),text);
});

test('line-numbered receipt messages keep their row number while localizing',()=>{
 assert.equal(errorText({code:'RECEIPT_REVIEW_REQUIRED',message:'Review receipt line 3 before confirming'}),'请先核对第 3 项小票内容，再确认入库');
 assert.equal(errorText({code:'RECEIPT_DATE_REQUIRED',message:'Check date and source on receipt line 12'}),'请核对第 12 项小票的日期与日期来源');
});

test('an unmapped code never echoes the raw server message',()=>{
 const text=errorText({code:'SOMETHING_NEW',message:'Some future English detail'});
 assert.equal(text,'操作未完成，请重试或刷新页面');
});

test('known codes and the generic conflict code use their table text',()=>{
 assert.equal(errorText({code:'VERSION_CONFLICT',message:'Inventory changed; refresh before adjusting'}),'记录已变化，请刷新后重试');
 assert.equal(errorText({code:'CONFLICT',message:'Conflicting operation'}),'操作发生冲突，请刷新后重试');
});

test('a payload with no code keeps only a neutral fallback',()=>{
 assert.equal(errorText(undefined),'操作未完成，请重试');
 assert.equal(errorText({}),'操作未完成，请重试');
 assert.equal(errorText({message:'Some detail'}),'Some detail');
});
