import test from 'node:test';
import assert from 'node:assert/strict';
import {elapsed,pause,resume,defaultMinutes,scaledQuantity} from '../.test-build/cookingTimer.js';
test('running 2 minutes + paused 5 + running 3 = 5 minutes; reload retains timestamps',()=>{
 let t={accumulated_ms:0,running_since_ms:1000,state:'running'};
 t=pause(t,121000);assert.equal(elapsed(t,421000),120000);
 t=resume(t,421000);t=JSON.parse(JSON.stringify(t));
 assert.equal(elapsed(t,601000),300000);assert.equal(defaultMinutes(elapsed(t,601000)),5);
});
test('round up default minutes without clipping out-of-range duration',()=>{
 assert.equal(defaultMinutes(0),1);assert.equal(defaultMinutes(60001),2);
 assert.equal(defaultMinutes(481*60000),481);
 assert.equal(elapsed({accumulated_ms:5,running_since_ms:200,state:'running'},100),5);
});

test('display quantities use decimal ceiling and whole pieces',()=>{
 assert.equal(scaledQuantity('1',1,2,'piece'),'1');
 assert.equal(scaledQuantity('0.021',1,1,'g'),'0.021');
 assert.equal(scaledQuantity('80',1,3,'g'),'26.667');
});
