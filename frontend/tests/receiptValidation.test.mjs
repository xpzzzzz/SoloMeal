import test from 'node:test';
import assert from 'node:assert/strict';
import {receiptUnitProblem} from '../.test-build/receiptValidation.js';
const items=[{id:'rice',unit:'g'},{id:'egg',unit:'piece'},{id:'milk',unit:'ml'}];
const line={ingredient_id:'rice',quantity:'7',unit:'piece',excluded:false};
test('receipt rejects count/mass and mass/volume without guessing conversion',()=>{
 assert.match(receiptUnitProblem(line,items),/不能直接换算/);
 assert.match(receiptUnitProblem({...line,ingredient_id:'milk',unit:'g'},items),/不能直接换算/);
 assert.equal(line.quantity,'7');
});
test('receipt accepts same-dimension quantities and excludes ignored rows',()=>{
 assert.equal(receiptUnitProblem({...line,unit:'kg',quantity:'0.5'},items),null);
 assert.equal(receiptUnitProblem({...line,ingredient_id:'milk',unit:'l'},items),null);
 assert.equal(receiptUnitProblem({...line,excluded:true},items),null);
});
test('receipt requires whole positive counts',()=>{
 for(const quantity of ['0','-1','NaN','0.5'])assert.ok(receiptUnitProblem({...line,ingredient_id:'egg',quantity},items));
 assert.equal(receiptUnitProblem({...line,ingredient_id:'egg'},items),null);
});
