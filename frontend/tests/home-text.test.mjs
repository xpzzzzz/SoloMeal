import test from 'node:test';
import assert from 'node:assert/strict';
import {attentionSummary, attentionText, dayText, emptyText, expiryTag, minutesText, recentSummary,
 recentText, READ_ONLY_SECTIONS, sectionTitle, shoppingSummary, shoppingText} from '../.test-build/homeText.js';

test('expiry day text names the boundary days instead of a bare number',()=>{
 assert.equal(dayText(-2),'已过期 2 天');
 assert.equal(dayText(0),'今天到期');
 assert.equal(dayText(1),'明天到期');
 assert.equal(dayText(3),'3 天后到期');
 assert.equal(dayText(null),'到期日期未知');
 assert.equal(dayText('abc'),'到期日期未知');
});

test('an expired batch is labelled as needing a check, not as merely soon',()=>{
 assert.equal(expiryTag('expired'),'已过期，需检查');
 assert.equal(expiryTag('expiring_soon'),'三天内到期');
});

test('attention rows keep the date and the relative day together',()=>{
 assert.equal(attentionText({name:'米饭',quantity:'80',unit:'g',expires_on:'2026-09-21',days_left:-2}),'米饭 · 80 克 · 2026-09-21 已过期 2 天');
 assert.equal(attentionText({name:'鸡蛋',quantity:null,unit:'piece',expires_on:null}),'鸡蛋 · — 个 · 未填写 到期日期未知');
});

// The four shown rows are a truncation of a larger queue, so the copy has to say so.
test('attention summary reports the whole queue and the truncated display',()=>{
 const data={items:new Array(5).fill({}),total_count:9,expired_count:4,expiring_count:5};
 assert.equal(attentionSummary(data),'共 9 项需要处理：已过期 4 项，三天内到期 5 项；此处按日期只列最近 5 项。');
 assert.equal(attentionSummary({items:[1,2],total_count:2,expired_count:0,expiring_count:2}),'共 2 项需要处理：已过期 0 项，三天内到期 2 项。');
 assert.equal(attentionSummary({items:[],total_count:0}),'');
});

test('a missing duration never reads as zero minutes',()=>{
 for(const value of [null,undefined,0,-3,12.5,'12',NaN])
  assert.equal(minutesText(value),'未记录用时',JSON.stringify(value));
 assert.equal(minutesText(25),'25 分钟');
});

test('shopping rows separate what is still to buy from a fully checked list',()=>{
 assert.equal(shoppingText({recipe_name:'番茄炒蛋',pending_count:3,items_count:4}),'番茄炒蛋 · 待买 3 项 · 共 4 项');
 assert.equal(shoppingText({recipe_name:'番茄炒蛋',pending_count:0,items_count:4}),'番茄炒蛋 · 已勾选，待入库 · 共 4 项');
});

test('shopping summary counts every list, not only the printed ones',()=>{
 assert.equal(shoppingSummary({items:[1,2,3],list_count:7,pending_total:12}),'7 张清单未处理，共 12 项待买，此处只显示最近 3 张。');
 assert.equal(shoppingSummary({items:[1],list_count:1,pending_total:2}),'1 张清单未处理，共 2 项待买。');
});

test('recent rows name the meal, its date, servings and recorded duration',()=>{
 assert.equal(recentText({recipe_name:'白米饭',cooked_on:'2026-09-23',servings:2,actual_minutes:18}),'白米饭 · 2026-09-23 · 2 人份 · 18 分钟');
 assert.equal(recentText({recipe_name:'白米饭',cooked_on:'2026-09-23',servings:1,actual_minutes:null}),'白米饭 · 2026-09-23 · 1 人份 · 未记录用时');
 assert.equal(recentSummary({items:[1,2],completed_count:11}),'累计完成 11 餐，此处只显示最近 2 餐。');
});

test('titles and empty states are Chinese for all four blocks',()=>{
 assert.deepEqual([...READ_ONLY_SECTIONS],['attention','shopping','recent']);
 assert.deepEqual([...'attention recommendations shopping recent'.split(' ').map(sectionTitle)],
  ['优先处理','今天推荐','待采购','最近做过']);
 for(const name of ['attention','recommendations','shopping','recent'])
  assert.match(emptyText(name),/[一-鿿]/);
 assert.equal(sectionTitle('invented'),'这一栏');
 assert.match(emptyText('invented'),/暂时没有内容/);
});
