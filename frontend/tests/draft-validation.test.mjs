import test from 'node:test';
import assert from 'node:assert/strict';
import {fieldText,issueText,groupByField,newIngredientHints} from '../.test-build/draftValidation.js';
import {pagedList} from '../.test-build/session.js';

test('server field paths become Chinese labels and never render the raw path',()=>{
 assert.equal(fieldText('name'),'菜谱名称');
 assert.equal(fieldText('ingredients[2].unit'),'第 2 项食材的单位');
 assert.equal(fieldText('ingredients[3]'),'第 3 项食材');
 assert.equal(fieldText('steps[4]'),'第 4 步');
 assert.equal(fieldText('servings'),'人数');
 // An address the page has never seen still reads as a section, not as "ingredients[9].x".
 assert.equal(fieldText('ingredients[9].future_field'),'填写内容');
 assert.equal(fieldText('future_section'),'填写内容');
});

test('an unusable quantity names the line and the value instead of guessing a conversion',()=>{
 assert.match(issueText({field:'ingredients[1].quantity',code:'quantity_invalid',value:'适量'}),
  /第 1 项食材的数量.*适量/);
 assert.match(issueText({field:'ingredients[2].unit',code:'unit_invalid',value:'碗'}),
  /只能填 克 \/ 千克 \/ 毫升 \/ 升 \/ 个/);
 assert.match(issueText({field:'ingredients[1].quantity',code:'quantity_not_whole',value:'1.5'}),/整数/);
 assert.match(issueText({field:'ingredients[1].unit',code:'unit_missing'}),/还缺单位/);
});

test('unit conflicts tell the user the stored unit and forbid rewriting it',()=>{
 const text=issueText({field:'ingredients[1].unit',code:'unit_dimension_conflict',value:'g',expected:'ml'});
 assert.match(text,/按毫升记录/);assert.match(text,/不会被改动/);
});

test('every constraint mismatch detail explains what stayed fixed',()=>{
 assert.match(issueText({field:'minutes',code:'constraint_mismatch',detail:'time_limit',maximum:30}),/最多用时 30 分钟/);
 assert.match(issueText({field:'servings',code:'constraint_mismatch',detail:'servings_mismatch',expected:2}),/本次人数为 2 人/);
 assert.match(issueText({field:'equipment',code:'constraint_mismatch',detail:'missing_equipment',values:['烤箱','空气炸锅']}),
  /烤箱、空气炸锅/);
 assert.match(issueText({field:'ingredients[2].name',code:'constraint_mismatch',detail:'excluded_ingredient'}),/忌口/);
});

test('duplicate lines point at the other line and say whether the flags disagree',()=>{
 assert.match(issueText({field:'ingredients[5].name',code:'duplicate_ingredient',other_line:4,detail:'same_ingredient'}),
  /第 4 项.*合并/s);
 assert.match(issueText({field:'ingredients[5].name',code:'duplicate_ingredient',other_line:4,detail:'optional_conflict'}),
  /必需／可选标记不一致/);
});

test('warnings ask for a human check and a name clash stays a warning',()=>{
 assert.match(issueText({field:'ingredients',code:'step_ingredient_unlisted',value:'番茄'}),/食材清单没有列出/);
 assert.match(issueText({field:'equipment',code:'step_equipment_unlisted',value:'烤箱'}),/厨具清单没有列出/);
 assert.match(issueText({field:'name',code:'duplicate_recipe_name'}),/同名菜谱/);
});

test('an unknown code becomes Chinese guidance, never provider text',()=>{
 assert.equal(issueText({field:'minutes',code:'SOMETHING_NEW'}),'用时需要检查。');
 assert.equal(issueText({code:'SOMETHING_NEW'}),'填写内容需要检查。');
});

test('issues are addressed per field so one error cannot hide another',()=>{
 const grouped=groupByField([{field:'ingredients[1].name',code:'value_missing'},
  {field:'ingredients[1].quantity',code:'quantity_invalid'},{field:'ingredients[1].name',code:'duplicate_ingredient'}]);
 assert.deepEqual(Object.keys(grouped).sort(),['ingredients[1].name','ingredients[1].quantity']);
 assert.equal(grouped['ingredients[1].name'].length,2);
});

test('new-ingredient hints follow the typed name and its base unit',()=>{
 const items=[{id:'a',name:'鸡蛋',unit:'piece'},{id:'b',name:'番茄',unit:'g'}];
 assert.deepEqual(newIngredientHints([{name:' 鸡蛋 ',quantity:'2',unit:'piece',optional:false},
  {name:'面条',quantity:'150',unit:'g',optional:false}],items),[{name:'面条',unit:'克'}]);
 // kg and g share a base unit; two different bases for one name must not pick silently.
 assert.deepEqual(newIngredientHints([{name:'牛奶',quantity:'1',unit:'kg'},
  {name:'牛奶',quantity:'2',unit:'ml'}],items),[{name:'牛奶',unit:'互相冲突'}]);
 assert.deepEqual(newIngredientHints([{name:'香菜',quantity:'2',unit:''}],items),[{name:'香菜',unit:'待填写'}]);
 assert.deepEqual(newIngredientHints([{name:'香菜',quantity:'2',unit:'把'}],items),[{name:'香菜',unit:'待填写'}]);
 assert.deepEqual(newIngredientHints([{name:'番茄',quantity:'1',unit:'g'}],items),[]);
});

test('a tag outside the vocabulary is named so a person can replace it',()=>{
 assert.equal(fieldText('cooking_methods'),'烹饪方式标签');
 assert.match(issueText({field:'cooking_methods',code:'cooking_method_invalid',value:'deep_fry'}),
  /烹饪方式标签里的“deep_fry”不是可选的烹饪方式/);
 assert.match(issueText({field:'cooking_methods',code:'cooking_method_duplicate',value:'boil'}),
  /烹饪方式标签“boil”重复选择/);
 // The count rule already carries its own bounds, so it must not be reworded into a guess.
 assert.match(issueText({field:'cooking_methods',code:'count_out_of_range',minimum:0,maximum:3,value:'4'}),
  /烹饪方式标签需要 0～3 项.*目前有 4 项/);
});

test('the new draft and batch lists are read page by page with their filters',async()=>{
 for(const [path,status] of [['/recipe-drafts?status=draft','draft'],['/recipe-discoveries',null]]){
  const calls=[];
  await pagedList(path,async p=>{
   const url=new URL(p,'http://local');calls.push(url);
   return Number(url.searchParams.get('offset'))===0?Array.from({length:200},(_,id)=>({id})):[];
  });
  assert.equal(calls.length,2,`${path} should keep paging`);
  assert.equal(calls[1].searchParams.get('status'),status);
  assert.equal(calls[1].searchParams.get('limit'),'200');
 }
});
