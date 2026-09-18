import test,{before,after} from 'node:test';
import assert from 'node:assert/strict';
import {desktopContext,launchBrowser,makeApi,openPage,signIn,startFixture,waitForRows,waitText,shot} from './support.mjs';

let server,browser;
before(async()=>{server=await startFixture(0);browser=await launchBrowser();});
after(async()=>{await browser?.close();await server?.stop();});

test('跨页库存完整显示，429 有等待提示且可手动恢复',async()=>{
 const api=makeApi(server.url),password='pagination-fixture-1';
 const token=await api.signIn('pagination_user',password);
 const item=await api.call(token,'/ingredients','POST',{name:'分页大米',unit:'g'});
 assert.equal(item.status,201);
 for(let n=0;n<205;n++){
  const result=await api.call(token,'/inventory','POST',{ingredient_id:item.data.id,quantity:'1',unit:'g'});
  assert.equal(result.status,201);
 }
 assert.equal((await api.call(token,'/inventory')).data.length,100);
 const context=await desktopContext(browser),page=await openPage(context,server.url);
 const pages=[];
 page.on('request',request=>{if(request.url().includes('/inventory?'))pages.push(request.url());});
 await signIn(page,'pagination_user',password);
 await waitForRows(page,205);
 assert.equal(await page.locator('table tbody tr').count(),205);
 assert.ok(pages.some(url=>url.includes('offset=200')));
 await page.route('**/api/v1/inventory?*',route=>route.fulfill({status:429,contentType:'application/json',headers:{'Retry-After':'60'},body:JSON.stringify({error:{code:'RATE_LIMITED'}})}));
 await page.getByRole('button',{name:'刷新库存',exact:true}).click();
 await waitText(page,/请求较频繁.*60.*秒/);
 await page.unroute('**/api/v1/inventory?*');
 await page.getByRole('button',{name:'刷新库存',exact:true}).click();
 await waitForRows(page,205);
 await shot(page,'pagination-205.png');
 assert.equal(page.problems.length,0);
 await context.close();
});
