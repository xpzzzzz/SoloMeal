import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {access, mkdir, mkdtemp, rm} from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const here = path.dirname(fileURLToPath(import.meta.url));
export const FRONTEND = path.resolve(here, '..');
export const ROOT = path.resolve(FRONTEND, '..');
export const SHOTS = path.join(FRONTEND, '.tmp-e2e');
const venvPython = path.join(ROOT, 'backend', '.venv', ...(process.platform === 'win32'
 ? ['Scripts', 'python.exe'] : ['bin', 'python']));
const PYTHON = process.env.SOLOMEAL_PYTHON || (existsSync(venvPython) ? venvPython : 'python');
const FIXTURE = path.join(ROOT, 'backend', 'scripts', 'browser_fixture.py');

export function testDate(days = 0){
 const date = new Date();
 date.setDate(date.getDate() + days);
 return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}

function freePort(){
 return new Promise((resolve,reject)=>{
  const server=net.createServer();
  server.on('error',reject);
  server.listen(0,'127.0.0.1',()=>{const port=server.address().port;server.close(()=>resolve(port));});
 });
}

// The scripted fixture is the only service these tests talk to: temporary SQLite, never a real model.
export async function startFixture(modelDelay,{receiptParser=false,recipeDiscovery=false}={}){
 await assert.doesNotReject(access(path.join(FRONTEND,'dist','index.html')),'frontend/dist is missing; run npm run build first');
 const port=await freePort();
 const url=`http://127.0.0.1:${port}`;
 await mkdir(SHOTS,{recursive:true});
 const dataDir=await mkdtemp(path.join(SHOTS,'db-'));
 const child=spawn(PYTHON,[FIXTURE,'--port',String(port),'--model-delay',String(modelDelay),'--data-dir',dataDir,...(receiptParser?['--receipt-parser']:[]),...(recipeDiscovery?['--recipe-discovery']:[])],
  {cwd:path.join(ROOT,'backend'),stdio:['ignore','pipe','pipe'],windowsHide:true});
 let log='',spawnError,closed=false;
 const done=new Promise(resolve=>child.once('close',()=>{closed=true;resolve();}));
 child.on('error',error=>{spawnError=error;});
 const append=chunk=>{log=(log+chunk).slice(-32_000);};
 child.stdout.on('data',append);
 child.stderr.on('data',append);
 const stop=async()=>{
  if(!closed){
   child.kill();
   const force=setTimeout(()=>child.kill('SIGKILL'),5000);
   try{await done;}finally{clearTimeout(force);}
  }
  // Only remove the unique directory this runner created inside its artifact directory.
  assert.equal(path.dirname(path.resolve(dataDir)),path.resolve(SHOTS));
  await rm(dataDir,{recursive:true,force:true,maxRetries:3});
 };
 try{
  const deadline=Date.now()+120_000;
  for(;;){
   if(spawnError)throw new Error(`无法启动测试 Python (${PYTHON}): ${spawnError.message}`);
   if(closed||child.exitCode!==null)assert.fail(`夹具服务提前退出 (${child.exitCode}):\n${log}`);
   try{if((await fetch(url+'/health/live',{signal:AbortSignal.timeout(2000)})).ok)break;}catch{/* still starting */}
   assert.ok(Date.now()<deadline,`夹具服务 120 秒内没有就绪:\n${log}`);
   await new Promise(r=>setTimeout(r,250));
  }
  return {url,port,dataDir,log:()=>log,stop};
 }catch(error){
  await stop();
  throw error;
 }
}

export async function launchBrowser(){
 try{return await chromium.launch({headless:true,channel:'chromium'});}
 catch{return await chromium.launch({headless:true});}
}

export function desktopContext(browser){
 return browser.newContext({viewport:{width:1280,height:900},locale:'zh-CN'});
}

// Real touch and viewport metrics, so narrow-screen CSS loads the way a phone renders it.
export function mobileContext(browser){
 return browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:3,
  userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
  locale:'zh-CN'});
}

export async function openPage(context,url){
 const page=await context.newPage();
 page.problems=[];
 page.on('pageerror',error=>page.problems.push(error.message));
 page.on('dialog',dialog=>dialog.accept().catch(()=>{}));
 await page.goto(url,{waitUntil:'domcontentloaded'});
 await page.waitForSelector('nav, .login-card');
 return page;
}

export async function signUp(page,username,password){
 await page.getByRole('button',{name:'第一次使用？创建账号'}).click();
 await page.getByLabel('用户名').fill(username);
 await page.getByLabel('密码').fill(password);
 await page.getByRole('button',{name:'创建账号',exact:true}).click();
 await page.waitForSelector('nav[aria-label="主导航"]');
}

export async function signIn(page,username,password){
 await page.getByLabel('用户名').fill(username);
 await page.getByLabel('密码').fill(password);
 await page.getByRole('button',{name:'登录',exact:true}).click();
 await page.waitForSelector('nav[aria-label="主导航"]');
}

export async function signOut(page){
 await page.getByRole('button',{name:'退出登录'}).click();
 await page.waitForSelector('.login-card');
}

export async function useTab(page,name){
 await page.getByRole('navigation',{name:'主导航'}).getByRole('button',{name,exact:true}).click();
}

// The panel re-reads preferences on every mount and the field is controlled, so a
// response that lands after the caller typed silently reverts what was typed.
export async function openPreferences(page){
 const loaded=page.waitForResponse(r=>r.url().endsWith('/me/preferences')&&r.request().method()==='GET',{timeout:30_000});
 await useTab(page,'厨房偏好');
 await loaded;
}

const UNIT_TEXT = {g: '克', kg: '千克', ml: '毫升', l: '升', piece: '个'};

// The inventory form is a real <select>, so a new option is attached long before it is visible.
export async function addKind(page, {name, unit = 'piece'}) {
 await useTab(page, '食材库存');
 await page.locator('input[name="name"]').fill(name);
 await page.locator('select[name="unit"]').selectOption(unit);
 await page.getByRole('button', {name: '添加种类'}).click();
 const label = `${name}（${UNIT_TEXT[unit]}）`;
 await page.locator('select[name="ingredient"] option', {hasText: label}).first().waitFor({state: 'attached'});
 return label;
}

export async function addKindAndBatch(page, {name, unit = 'piece', quantity, location}) {
 const label = await addKind(page, {name, unit});
 await page.locator('select[name="ingredient"]').selectOption({label});
 await page.locator('input[name="quantity"]').fill(quantity);
 await page.locator('select[name="location"]').selectOption(location);
 await page.getByRole('button', {name: '确认入库'}).click();
 await page.locator('table tbody tr', {hasText: name}).first().waitFor();
}

export async function waitText(page,pattern,timeout=30_000){
 const {source,flags}=pattern;
 try{
  await page.waitForFunction(({source,flags})=>new RegExp(source,flags).test(document.body.innerText),
   {source,flags:flags.replace('g','')},{timeout});
 }catch{
  const seen=await page.evaluate(()=>document.body.innerText);
  assert.fail(`等待文本 /${source}/ 超时（${timeout}ms）。页面当前内容：\n${seen.slice(0,2000)}`);
 }
}

export async function bodyText(page){
 return page.evaluate(()=>document.body.innerText);
}

export async function horizontalOverflow(page){
 return page.evaluate(()=>Math.max(document.documentElement.scrollWidth,document.body.scrollWidth)-window.innerWidth);
}

export async function visibleButtons(page){
 return page.evaluate(()=>[...document.querySelectorAll('button')]
  .filter(b=>b.offsetParent!==null&&b.getBoundingClientRect().height>0)
  .map(b=>({text:b.innerText.trim().slice(0,12),height:Math.round(b.getBoundingClientRect().height)})));
}

// Cross-check what the page shows against what the service actually stored.
export function makeApi(url){
 return {
  async signIn(username,password){
   await fetch(url+'/api/v1/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username,password})});
   const response=await fetch(url+'/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({username,password})});
   assert.equal(response.status,200,'验证用 API 登录应当成功');
   return (await response.json()).access_token;
  },
  // The page reuses one key per logical retry; here the caller decides. Omit key and each call gets a fresh one.
  async call(token,pathname,method='GET',body,key,timeoutMs=25_000){
   const response=await fetch(url+'/api/v1'+pathname,{method,signal:AbortSignal.timeout(timeoutMs),
    headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),
     ...(method==='GET'?{}:{'Idempotency-Key':key??crypto.randomUUID()})},
    body:body===undefined?undefined:JSON.stringify(body)});
   return {status:response.status,data:response.status===204?null:await response.json()};
  },
 };
}

// A row list that already has one entry is not a signal that the second one arrived.
export async function waitForRows(page, count, timeout = 20_000) {
 await page.waitForFunction(n => document.querySelectorAll('table tbody tr').length >= n, count, {timeout});
}

export async function shot(page,name){
 await page.screenshot({path:path.join(SHOTS,name),fullPage:true});
}
