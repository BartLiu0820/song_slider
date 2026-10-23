// Run with Playwright available on NODE_PATH. No production mutations.
const {chromium}=require('playwright');
const fs=require('fs');const assert=require('node:assert/strict');const path=require('path');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:900}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let posts=0, polls=0, deploy=false;
  const job={id:'a'.repeat(24),slug:'sample',repository:'https://github.com/test/sample',branch:'main',directory:'/',status:'ready',plan:{ready:true},access:{mode:'public',accounts:[]}};
  await page.route('http://localhost/**',async route=>{
   const url=new URL(route.request().url());let data;
   if(url.pathname==='/api/me')data={csrf:'test',email:'test',public_enabled:true};
   else if(url.pathname==='/api/accounts')data=[];
   else if(url.pathname==='/api/jobs')data=[{...job,status:deploy?'deploying':'ready'}];
   else if(url.pathname.endsWith('/conversation')){polls++;data={messages:[{role:'event',content:'方案已准备好',action:'deploy',created_at:1}],busy:false,status:deploy?'deploying':'ready',progress:deploy?{text:'正在构建真实应用…'}:null,live_build:deploy?{logs:'Build step '+polls,updated_at:polls,status:'in_progress'}:null};}
   else if(url.pathname.endsWith('/deploy')){posts++;await new Promise(r=>setTimeout(r,300));deploy=true;data={...job,status:'deploying'};}
   else if(url.pathname.endsWith('/refresh'))return route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'测试提示会自动消失'})});
   else {const filename=url.pathname==='/'?'index.html':url.pathname.replace('/assets/','');return route.fulfill({contentType:filename.endsWith('js')?'text/javascript':filename.endsWith('css')?'text/css':'text/html',body:fs.readFileSync(path.join(__dirname,filename),'utf8')});}
   await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  });
  await page.goto('http://localhost/#/projects/'+job.id);await page.locator('.shortcuts button').first().waitFor();
  assert.deepEqual(await page.locator('.shortcuts button').allTextContents(),['部署当前版本','更新并部署','AI 修复','暂停自动处理']);
  await page.getByRole('button',{name:'更新并部署',exact:true}).click();await page.locator('#message:not([hidden])').waitFor();await page.locator('#message').waitFor({state:'hidden',timeout:7000});
  await page.getByRole('button',{name:'项目设置',exact:true}).click();await page.locator('dialog[open] select').waitFor();await page.locator('dialog[open]').getByRole('button',{name:'关闭',exact:true}).click();
  await page.getByRole('button',{name:'部署当前版本',exact:true}).evaluate(b=>{b.click();b.click();});
  await page.locator('.execution-progress').waitFor();assert.equal(await page.locator('.live-build').getAttribute('open'),null);await page.locator('.live-build summary').click();await page.locator('.build-output').waitFor();
  assert.match(await page.locator('.deployment-status').textContent(),/本次部署尚未完成/);assert.equal(await page.locator('.transcript .live-build').count(),0);
  assert.equal(posts,1);assert.equal(await page.getByRole('button',{name:'部署当前版本',exact:true}).isDisabled(),true);
  const first=await page.locator('.build-output').textContent();await page.waitForFunction(first=>document.querySelector('.build-output').textContent!==first,first,{timeout:6000});
  await page.locator('.composer textarea').fill('保留草稿');await page.waitForTimeout(2400);assert.equal(await page.locator('.composer textarea').inputValue(),'保留草稿');
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);console.log(JSON.stringify({shortcuts:true,toast_dismissed:true,access_in_settings:true,duplicate_prevented:true,automatic_log_updates:true,draft_preserved:true,mobile_width:true,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
