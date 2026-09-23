import test from 'node:test';
import assert from 'node:assert/strict';
import {
 COOKING_METHODS,MAX_METHODS,isCookingMethod,methodName,methodText,methodsFromStored,toggleMethod,
} from '../.test-build/cookingMethods.js';

test('every stored value reads as a Chinese label and nothing is invented',()=>{
 assert.deepEqual([...COOKING_METHODS].map(methodName),
  ['炒','蒸','煮','炖','烤','煎','凉拌','其他']);
 assert.equal(COOKING_METHODS.length,8);
 // An unknown value keeps its own text rather than becoming a plausible label.
 assert.equal(methodName('mystery'),'mystery');
 assert.equal(isCookingMethod('steam'),true);
 assert.equal(isCookingMethod('STEAM'),false);
 assert.equal(isCookingMethod(null),false);
});

test('stored tags survive as written so a bad one stays fixable',()=>{
 assert.deepEqual(methodsFromStored(undefined),[]);
 assert.deepEqual(methodsFromStored(null),[]);
 assert.deepEqual(methodsFromStored('steam'),[]);
 assert.deepEqual(methodsFromStored(['boil','steam',null,7,'  ']),['boil','steam','7']);
 assert.deepEqual(methodsFromStored([1]),['1']);
 assert.equal(methodText(['stir_fry','boil']),'炒 / 煮');
 assert.equal(methodText([]),'');
});

test('tapping a tag adds or removes it and the cap replaces nothing',()=>{
 assert.deepEqual(toggleMethod([], 'boil'),['boil']);
 assert.deepEqual(toggleMethod(['boil','steam'],'boil'),['steam']);
 const full=['boil','steam','fry'];
 assert.deepEqual(toggleMethod(full,'bake'),full);
 assert.deepEqual(toggleMethod(full,'steam'),['boil','fry']);
 assert.equal(MAX_METHODS,3);
 // Removing is always possible, so a draft at the cap can still be corrected.
 assert.deepEqual(toggleMethod(['a','b','c'],'a'),['b','c']);
});
