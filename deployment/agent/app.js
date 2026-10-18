let csrf='', jobs=[], accounts=[], signature='', timer, refreshing=false, editing=false;
const $=s=>document.querySelector(s);
const labels={queued:'排队中',analyzing:'识别中',ready:'待部署',needs_configuration:'待配置',deploying:'部署中',deployed:'运行中',failed:'未完成',cancelled:'已取消'};
async function api(path,body){
  const r=await fetch('/api'+path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await r.json();if(!r.ok)throw Error(data.error||'请求未完成');return data;
}
function el(tag,text,cls){const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;}
function link(text,href,cls){const a=el('a',text,cls);a.href=href;return a;}
function button(text,action,cls){const b=el('button',text,cls);b.type='button';b.onclick=action;return b;}
function message(text){$('#message').textContent=text||'';$('#message').hidden=!text;}
function field(form,title,name,options={}){const l=el('label',title);const input=el('input');input.name=name;Object.assign(input,options);l.append(input);form.append(l);return input;}
function titleBlock(title,subtitle,action){const head=el('div',null,'page-head');const text=el('div');text.append(el('h1',title));if(subtitle)text.append(el('p',subtitle,'subtitle'));head.append(text);if(action)head.append(action);return head;}
function tag(job){return el('span',labels[job.status]||job.status,'tag '+job.status);}
function accessEditor(value={mode:'public',accounts:[]}){
  const wrap=el('section',null,'access-editor');const label=el('label','访问权限');const select=el('select');
  for(const [v,t] of [['public','公开'],['restricted','指定账号访问']]){const o=el('option',t);o.value=v;select.append(o);}select.value=value.mode;label.append(select);wrap.append(label);
  const choices=el('div',null,'account-choices');
  const redraw=()=>{choices.replaceChildren();choices.hidden=select.value==='public';if(!accounts.length)choices.append(el('p','还没有访问账号，请先创建。','hint'));for(const name of accounts){const l=el('label',null,'check');const c=el('input');c.type='checkbox';c.value=name;c.checked=value.accounts.includes(name);l.append(c,document.createTextNode(name));choices.append(l);}choices.append(button('管理访问账号',()=>openAccounts(), 'quiet'));};redraw();select.onchange=()=>{choices.hidden=select.value==='public';};wrap.append(choices,el('p','公开：无需登录。指定账号：打开项目时验证账号密码。','hint'));
  wrap.addEventListener('change',()=>{editing=true;});
  wrap.value=()=>({mode:select.value,accounts:[...choices.querySelectorAll('input:checked')].map(x=>x.value)});
  return wrap;
}
function render(){
  const root=$('#workspace');root.replaceChildren();const route=location.hash.slice(1)||'/';
  if(route==='/new'){renderNew(root);return;}
  if(route.startsWith('/projects/')){const job=jobs.find(j=>j.id===route.split('/')[2]);if(job){renderDetail(root,job);return;}root.append(link('← 返回项目','#/'),el('p','项目不存在'));return;}
  root.append(titleBlock('我的部署',`${jobs.length} 个项目`,link('＋ 添加新部署','#/new','primary button')));
  const grid=el('div',null,'project-grid');
  for(const job of jobs){const card=link('', '#/projects/'+job.id,'project-card');const top=el('div',null,'section-head');top.append(el('span',job.slug.slice(0,2).toUpperCase(),'project-icon'),tag(job));const repo=job.repository.replace('https://github.com/','');card.append(top,el('h2',job.slug),el('p',repo,'repo'));const bottom=el('div',null,'card-bottom');bottom.append(el('span',job.access?.mode==='restricted'?'指定账号 · '+job.access.accounts.length+' 人':'公开'),el('span','查看详情 →'));card.append(bottom);grid.append(card);}
  if(!jobs.length)grid.append(el('div','还没有部署。添加一个 Git 仓库，开始第一个项目。','empty'));
  root.append(grid,el('p','当前通过本机 SSH 通道预览 · 公网访问待域名备案','footnote'));
}
function renderNew(root){
  root.append(link('← 我的部署','#/','back'),titleBlock('添加新部署','填写仓库地址，让 AI 识别部署方式。'));
  const form=el('form',null,'panel form-page');
  field(form,'GitHub 仓库地址','repository',{type:'url',required:true,placeholder:'https://github.com/owner/repository'});
  field(form,'项目名称','slug',{required:true,pattern:'[a-z][a-z0-9-]{1,38}[a-z0-9]',placeholder:'my-project'});
  const advanced=el('details');advanced.append(el('summary','分支与应用目录（可选）'));const fields=el('div',null,'fields');field(fields,'分支','branch',{placeholder:'自动识别默认分支'});field(fields,'应用目录','directory',{value:'/',placeholder:'/apps/web'});advanced.append(fields);form.append(advanced);
  const access=accessEditor();form.append(access,el('p','首版支持公开 GitHub 仓库。项目清单和选定配置文件会发送给 DeepSeek；识别完成后可查看方案再部署。','hint'));
  const submit=el('button','识别并创建','primary');submit.type='submit';form.append(submit);
  form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;try{const data=Object.fromEntries(new FormData(form));data.access=access.value();const job=await api('/analyze',data);jobs.unshift({...job,access:data.access});message('');location.hash='/projects/'+job.id;}catch(err){message(err.message);}finally{submit.disabled=false;}};root.append(form);
}
function renderDetail(root,job){
  root.append(link('← 我的部署','#/','back'),titleBlock(job.slug,job.repository));
  const overview=el('section',null,'panel');const row=el('div',null,'section-head');row.append(el('h2','部署状态'),tag(job));overview.append(row);
  if(job.error)overview.append(el('p',job.error,'warn'));
  if(job.plan?.summary)overview.append(el('p',job.plan.summary));
  const actions=el('div',null,'actions');
  if(job.status==='deployed'){const a=link('打开项目 ↗','http://'+job.slug+'.localhost:19180','primary button');a.target='_blank';a.rel='noopener';actions.append(a);}
  if(['ready','failed','cancelled'].includes(job.status)&&job.plan?.ready){actions.append(button(job.application_uuid?'重新部署':'开始部署',async e=>{e.target.disabled=true;try{await api('/jobs/'+job.id+'/deploy',{});await refresh(true);message('');}catch(err){message(err.message);e.target.disabled=false;}},'primary'));}
  overview.append(actions);if(job.application_uuid)overview.append(el('p','公网地址：'+job.slug+'.preview.greatsong.online（待备案）','hint address'));root.append(overview);
  const accessPanel=el('form',null,'panel');accessPanel.append(el('h2','访问权限'));const editor=accessEditor(job.access);accessPanel.append(editor);const save=el('button','保存权限','primary');save.type='submit';accessPanel.append(save);accessPanel.onsubmit=async e=>{e.preventDefault();save.disabled=true;try{job.access=await api('/jobs/'+job.id+'/access',editor.value());signature='';editing=false;message('访问权限已保存，立即生效。');}catch(err){message(err.message);}finally{save.disabled=false;}};root.append(accessPanel);
  const details=el('details',null,'panel technical');details.append(el('summary','部署详情'));
  details.append(el('p','分支：'+(job.branch||'自动识别')+' · 目录：'+job.directory,'meta'));if(job.commit)details.append(el('p','提交：'+job.commit,'meta'));
  if(job.plan){const p=job.plan;details.append(el('pre',`构建方式  ${p.build_pack}\n应用目录  ${p.base_directory}\n服务端口  ${p.port}\n发布目录  ${p.publish_directory}`));for(const k of ['install_command','build_command','start_command'])if(p[k])details.append(el('pre',k+'\n'+p[k]));for(const note of [...(p.missing_env||[]).map(x=>'待配置变量：'+x),...(p.databases||[]).map(x=>'数据库 / 持久化：'+x),...(p.notes||[])])details.append(el('p',note,'hint'));}
  if(job.application_uuid){const a=link('在部署引擎查看日志 ↗','http://127.0.0.1:18000');a.target='_blank';a.rel='noopener';details.append(a);}root.append(details);
}
async function openAccounts(){await reloadAccounts();$('#account-dialog').showModal();}
async function reloadAccounts(){accounts=await api('/accounts');const list=$('#account-list');list.replaceChildren();for(const name of accounts){const row=el('div',null,'account-row');row.append(el('span',name),button('删除',async()=>{if(!confirm('删除账号 '+name+'？其项目访问权限也会撤销。'))return;try{await api('/accounts/'+encodeURIComponent(name)+'/delete',{});await reloadAccounts();}catch(e){$('#account-message').textContent=e.message;}},'quiet'));list.append(row);}}
$('#account-form').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{await api('/accounts',Object.fromEntries(new FormData(e.target)));e.target.reset();await reloadAccounts();$('#account-message').textContent='账号已创建。关闭后勾选账号并保存权限。';}catch(err){$('#account-message').textContent=err.message;}finally{b.disabled=false;}};
$('#close-accounts').onclick=()=>$('#account-dialog').close();
$('#account-dialog').addEventListener('close',()=>{for(const editor of document.querySelectorAll('.access-editor')){const replacement=accessEditor(editor.value());editor.replaceChildren(...replacement.childNodes);editor.value=replacement.value;}});
async function refresh(force=false){if(refreshing)return;refreshing=true;try{const next=await api('/jobs');const value=JSON.stringify(next);jobs=next;if(force||value!==signature){if(force||(!editing&&!document.activeElement?.matches('input,select')&&!$('#account-dialog').open&&(location.hash!=='#/new'))){signature=value;render();}}}finally{refreshing=false;}}
async function enter(){const me=await api('/me');csrf=me.csrf;accounts=await api('/accounts');$('#login-panel').hidden=true;$('#workspace').hidden=false;$('#logout').hidden=false;$('#identity').textContent=me.email;await refresh(true);clearInterval(timer);timer=setInterval(()=>refresh().catch(e=>message(e.message)),6000);}
$('#login-form').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{await api('/login',Object.fromEntries(new FormData(e.target)));e.target.reset();message('');await enter();}catch(err){message(err.message);}finally{b.disabled=false;}};
$('#logout').onclick=async()=>{await api('/logout',{});location.reload();};
window.addEventListener('hashchange',()=>{editing=false;message('');if(csrf)render();});
enter().catch(()=>{$('#login-panel').hidden=false;});
