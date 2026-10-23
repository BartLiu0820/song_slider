let publicEnabled=false, connectionWarning=false;
const ipEntry=location.hostname==='47.116.108.184';
let csrf='', jobs=[], accounts=[], signature='', timer, refreshing=false, editing=false;
let currentId='', conversationSignature='', conversationBusy=false, conversationLoading=true, conversationError='', transcript=[], search='';
const drafts=new Map(), sending=new Set(), actionsPending=new Set();
let messageTimer, liveBuild=null, executionProgress=null, executionStatus='', execution=null, chatRequest=null;
let conversationCheckedAt=0, unreadMessages=false;
const logExpanded=new Map();
const $=s=>document.querySelector(s);
const labels={queued:'排队中',analyzing:'识别中',ready:'待部署',needs_configuration:'待配置',deploying:'部署中',deployed:'已部署',repairing:'AI 修复中',needs_attention:'待补充信息',failed:'未完成',cancelled:'已取消',deleting:'删除中',delete_failed:'删除未完成'};
async function api(path,body){
  const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),20000);
  try{
    const r=await fetch('/api'+path,{method:body===undefined?'GET':'POST',signal:controller.signal,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await r.json();if(!r.ok){const error=Error(data.error||'请求未完成');error.status=r.status;throw error;}return data;
  }catch(error){if(error.name==='AbortError')throw Error('请求超时，请检查网络后重试');throw error;}finally{clearTimeout(deadline);}
}
function bootState(title,detail,error=false){const panel=$('#boot-panel');panel.hidden=false;panel.dataset.state=error?'error':'loading';panel.setAttribute('aria-busy',String(!error));$('#boot-title').textContent=title;$('#boot-detail').textContent=detail;}
function hideBoot(){$('#boot-panel').hidden=true;$('#boot-panel').setAttribute('aria-busy','false');}

function el(tag,text,cls){const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;}
function link(text,href,cls){const a=el('a',text,cls);a.href=href;return a;}
function button(text,action,cls){const b=el('button',text,cls);b.type='button';b.onclick=action;return b;}
function message(text){clearTimeout(messageTimer);$('#message').textContent=text||'';$('#message').hidden=!text;if(text)messageTimer=setTimeout(()=>message(''),4500);}
function field(form,title,name,options={}){const l=el('label',title);const input=el('input');input.name=name;Object.assign(input,options);l.append(input);form.append(l);return input;}
function titleBlock(title,subtitle,action){const head=el('div',null,'page-head');const text=el('div');text.append(el('h1',title));if(subtitle)text.append(el('p',subtitle,'subtitle'));head.append(text);if(action)head.append(action);return head;}
function tag(job){return el('span',job.status==='failed'&&job.infrastructure_error?'部署环境未就绪':labels[job.status]||job.status,'tag '+job.status);}
function accessEditor(value={mode:'public',accounts:[]}){
  const wrap=el('section',null,'access-editor');const label=el('label','访问权限');const select=el('select');
  for(const [v,t] of [['public','公开'],['restricted','指定账号访问']]){const o=el('option',t);o.value=v;select.append(o);}select.value=value.mode;label.append(select);wrap.append(label);
  const choices=el('div',null,'account-choices');
  const redraw=()=>{choices.replaceChildren();choices.hidden=select.value==='public';if(!accounts.length)choices.append(el('p','还没有访问账号，请先创建。','hint'));for(const name of accounts){const l=el('label',null,'check');const c=el('input');c.type='checkbox';c.value=name;c.checked=value.accounts.includes(name);l.append(c,document.createTextNode(name));choices.append(l);}choices.append(button('管理访问账号',()=>openAccounts(), 'quiet'));};redraw();select.onchange=()=>{choices.hidden=select.value==='public';};wrap.append(choices,el('p','公开：无需登录。指定账号：打开项目时验证账号密码。','hint'));
  wrap.addEventListener('change',()=>{editing=true;});
  wrap.value=()=>({mode:select.value,accounts:[...choices.querySelectorAll('input:checked')].map(x=>x.value)});
  return wrap;
}
const busy=job=>['queued','analyzing','deploying','repairing','deleting'].includes(job.status);
const selectedJob=()=>jobs.find(j=>j.id===currentId);
function render(){
  const root=$('#workspace'), route=location.hash.slice(1)||'/';
  const selected=route.startsWith('/projects/')?jobs.find(j=>j.id===route.split('/')[2]):null;
  if(currentId!==(selected?.id||'')){currentId=selected?.id||'';execution=null;chatRequest=null;conversationCheckedAt=0;unreadMessages=false;conversationSignature='';transcript=[];conversationBusy=false;conversationLoading=true;conversationError='';liveBuild=null;executionProgress=null;executionStatus='';}
  const oldStream=$('.transcript');const scroll=oldStream?.scrollTop||0;const following=!oldStream||oldStream.scrollHeight-scroll-oldStream.clientHeight<100;
  root.replaceChildren();root.className='workbench';
  const sidebar=el('aside',null,'sidebar');
  const sideHead=el('div',null,'sidebar-head');sideHead.append(el('span','工作空间','eyebrow'),el('h1','我的部署'));
  sideHead.append(link('＋  新建部署','#/new','primary button full'));
  const searchBox=el('input');searchBox.type='search';searchBox.placeholder='搜索项目或仓库';searchBox.setAttribute('aria-label','搜索部署');searchBox.value=search;
  searchBox.oninput=()=>{search=searchBox.value;renderList();};sideHead.append(searchBox);
  const list=el('nav',null,'deployment-list');list.setAttribute('aria-label','部署列表');sidebar.append(sideHead,list);
  const footer=el('div',null,'sidebar-footer');footer.append(button('访问账号',()=>openAccounts(),'quiet'),el('span',publicEnabled?'● 公网 HTTPS 已启用':'● 本机通道预览','connection-label'));sidebar.append(footer);
  const content=el('section',null,'workspace-content');root.append(sidebar,content);renderList();
  if(route==='/new'){renderNew(content);return;}
  if(route==='/resources'){renderResources(content);return;}
  if(selected){renderChat(content,selected);$('.transcript').scrollTop=following?$('.transcript').scrollHeight:scroll;loadConversation().catch(showConversationError);return;}
  const welcome=el('div',null,'welcome');welcome.append(el('div','宋','welcome-mark'),el('span','YOUR DEPLOYMENT COMPANION','eyebrow'),el('h1','部署，从一句话开始。'),el('p',jobs.length?'选择左侧项目，继续与 AI 协作。\n检查更新、部署发布、排查问题，都在同一个对话里。':'连接一个 GitHub 仓库，设置好基础信息。\nAI 会接着识别项目，陪你完成第一次部署。'),link('＋ 创建新部署','#/new','primary button'));
  if(route.startsWith('/projects/'))welcome.prepend(el('p','这个项目已不存在，请选择其他项目。','warn'));
  const examples=el('div',null,'welcome-examples');for(const t of ['检查最新版本','查看部署进度','分析构建日志'])examples.append(el('span',t));welcome.append(examples);content.append(welcome);
}
function renderList(){
  const list=$('.deployment-list');if(!list)return;list.replaceChildren();
  const filtered=jobs.filter(j=>(j.slug+' '+j.repository).toLowerCase().includes(search.toLowerCase()));
  list.append(el('p',`项目  /  ${filtered.length}`,'list-caption'));
  for(const job of filtered){const row=link('','#/projects/'+job.id,'deployment-item'+(job.id===currentId?' selected':''));if(job.id===currentId)row.setAttribute('aria-current','page');
    const icon=el('span',job.slug.slice(0,2).toUpperCase(),'project-icon');const info=el('div',null,'project-info');const top=el('div',null,'project-title');top.append(el('strong',job.slug),el('span',null,'status-dot '+job.status));
    info.append(top,el('span',job.repository.replace('https://github.com/',''),'repo-name'),el('span',(labels[job.status]||job.status)+' · '+(job.access?.mode==='restricted'?'指定账号':'公开访问'),'project-meta'));row.append(icon,info);list.append(row);}
  if(!filtered.length)list.append(el('p',jobs.length?'没有匹配的项目':'还没有项目，先新建一个部署。','list-empty'));
}
function renderNew(root){
  const head=el('div',null,'workspace-head');head.append(titleBlock('新建部署','01 基础设置  /  02 与 AI 完成部署'));root.append(head);
  const body=el('div',null,'setup-body');const form=el('form',null,'setup-form');form.append(el('span','先连接你的项目','eyebrow'),el('h2','剩下的，交给对话。'));
  field(form,'GitHub 仓库地址','repository',{type:'url',required:true,placeholder:'https://github.com/owner/repository'});
  field(form,'项目名称','slug',{required:true,pattern:'[a-z][a-z0-9-]{1,38}[a-z0-9]',placeholder:'my-project'});
  const advanced=el('details');advanced.append(el('summary','分支与应用目录（可选）'));const fields=el('div',null,'fields');field(fields,'分支','branch',{placeholder:'自动识别默认分支'});field(fields,'应用目录','directory',{value:'/',placeholder:'/apps/web'});advanced.append(fields);form.append(advanced);
  const access=accessEditor();form.append(access,el('p','支持公开 GitHub 仓库。AI 会读取项目清单和选定配置文件，识别后直接部署，构建或启动出错时自动诊断、修复并重试。','hint'));
  const submit=el('button','创建并自动部署  →','primary');submit.type='submit';form.append(submit);
  form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;try{const data=Object.fromEntries(new FormData(form));data.access=access.value();const job=await api('/analyze',data);jobs.unshift({...job,access:data.access});editing=false;message('');location.hash='/projects/'+job.id;}catch(err){message(err.message);}finally{submit.disabled=false;}};body.append(form);root.append(body);
}
function renderChat(root,job){
  const head=el('div',null,'workspace-head');const heading=el('div',null,'chat-heading');const title=el('div',null,'section-head');title.append(el('h1',job.slug),tag(job));heading.append(title,el('p',job.repository.replace('https://github.com/','')+'  /  '+(job.branch||'默认分支'),'subtitle'));
  const actions=el('div',null,'header-actions');if(job.deployed_commit||job.status==='deployed'){const a=link(ipEntry?'SSH 预览 ↗':'打开项目 ↗',job.preview_url,'button');a.target='_blank';a.rel='noopener';actions.append(a);}actions.append(button('项目设置',()=>openSettings(job)));
  head.append(heading,actions);root.append(head);
  const status=el('section',null,'deployment-status');status.setAttribute('aria-label','当前部署状态');status.setAttribute('role','status');root.append(status);
  const notice=button('有新消息 · 查看最新回复 ↓',()=>{const stream=$('.transcript');stream.scrollTop=stream.scrollHeight;unreadMessages=false;notice.hidden=true;},'new-messages');notice.hidden=!unreadMessages;root.append(notice);
  const stream=el('div',null,'transcript');stream.setAttribute('role','log');stream.setAttribute('aria-label','项目对话');root.append(stream);stream.onscroll=()=>{if(stream.scrollHeight-stream.scrollTop-stream.clientHeight<80){unreadMessages=false;const n=$('.new-messages');if(n)n.hidden=true;}};
  const bottom=el('div',null,'chat-bottom');const shortcuts=el('div',null,'shortcuts');
  for(const [text,action] of [['部署当前版本','deploy'],['更新并部署','refresh'],['AI 修复','repair'],['暂停自动处理','pause']]){const b=button(text,()=>runAction(action,selectedJob()),'shortcut');b.dataset.action=action;b.disabled=!canAction(action,job);shortcuts.append(b);}bottom.append(shortcuts);
  const form=el('form',null,'composer');const textarea=el('textarea');textarea.name='message';textarea.rows=2;textarea.maxLength=4000;textarea.placeholder='告诉 AI 你想做什么，例如：检查最新代码，帮我更新部署…';textarea.setAttribute('aria-label','发送给 AI 的消息');textarea.value=drafts.get(job.id)||'';
  textarea.oninput=()=>{drafts.set(job.id,textarea.value);updateComposer();};textarea.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!form.querySelector('button').disabled)form.requestSubmit();}};
  const bar=el('div',null,'composer-bar');bar.append(el('span','✦ AI 部署助手','assistant-label'),el('span','Enter 发送 · Shift + Enter 换行','keyboard-hint'));const send=el('button','发送 ↑','primary');send.type='submit';bar.append(send);form.append(textarea,bar);
  form.onsubmit=async e=>{e.preventDefault();const text=textarea.value.trim();if(!text||sending.has(job.id))return;sending.add(job.id);updateComposer();try{await api('/jobs/'+job.id+'/chat',{message:text});drafts.delete(job.id);if(currentId===job.id){textarea.value='';conversationBusy=true;await loadConversation();const stream=$('.transcript');if(stream)stream.scrollTop=stream.scrollHeight;unreadMessages=false;const notice=$('.new-messages');if(notice)notice.hidden=true;}}catch(err){message(err.message);}finally{sending.delete(job.id);updateComposer();}};
  bottom.append(form,el('p','AI 自动部署并处理构建、启动问题。可直接说“更新部署”或“修复问题”；缺少授权、密钥或必要配置时会说明。请勿在对话中发送密钥。','composer-note'));root.append(bottom);renderMessages();updateComposer();
}
function updateComposer(){const form=$('.composer');if(!form)return;const job=selectedJob();form.querySelector('button').disabled=!job||conversationBusy||sending.has(currentId)||!form.querySelector('textarea').value.trim()||['deleting','delete_failed'].includes(job.status);}
function canAction(action,job){if(!job||actionsPending.has(job.id))return false;if(['deleting','delete_failed'].includes(job.status))return action==='delete'&&job.status==='delete_failed';if(action==='deploy')return ['ready','deployed','failed','cancelled'].includes(job.status)&&job.plan?.ready;if(action==='pause')return ['queued','analyzing','deploying','repairing'].includes(job.status);if(action==='refresh')return !busy(job);if(action==='repair')return ['failed','needs_attention','needs_configuration','cancelled'].includes(job.status);if(action==='delete')return !busy(job)&&!conversationBusy;if(action==='logs')return !!job.deployment_uuid;return true;}
function renderMessages(){
  const stream=$('.transcript');if(!stream)return;const priorLog=document.querySelector('.build-output');const logPosition=priorLog&&{top:priorLog.scrollTop,follow:priorLog.scrollHeight-priorLog.scrollTop-priorLog.clientHeight<40};const nearBottom=stream.scrollHeight-stream.scrollTop-stream.clientHeight<100;const old=stream.scrollTop;stream.replaceChildren();
  const intro=el('div',null,'conversation-intro');intro.append(el('span','✦','ai-mark'),el('span','AI 部署助手 · 项目专属对话'));stream.append(intro);
  if(conversationLoading&&!transcript.length)stream.append(el('p','正在读取项目对话…','chat-loading'));
  if(conversationError){const retry=el('div',null,'chat-loading');retry.append(el('span',conversationError),button('重新加载',()=>loadConversation().catch(showConversationError),'quiet'));stream.append(retry);}
  for(const m of transcript){const row=el('article',null,'chat-message '+m.role);const meta=el('div',null,'message-meta');meta.append(el('span',m.role==='user'?'你':m.role==='event'?'部署动态':'AI 助手'),el('time',new Date(m.created_at*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})));row.append(meta);
    if(m.content.startsWith('最近构建日志：')){const d=el('details',null,'log-block');d.append(el('summary','构建日志 · 点击展开'),el('pre',m.content.slice(7)));row.append(d);}else row.append(el('div',m.content,'message-content'));
    if(m.action&&m.action!=='none'){const names={deploy:'确认部署',refresh:'更新并部署',repair:'AI 修复',logs:'读取构建日志',access:'设置访问权限',delete:'删除项目…'};const b=button(names[m.action]||m.action,()=>runAction(m.action,selectedJob()),m.action==='delete'?'danger':'action-button');b.dataset.action=m.action;b.disabled=!canAction(m.action,selectedJob());row.append(b);}stream.append(row);
  }
  renderExecution(logPosition);
  renderStatus();
  if(conversationBusy)stream.append(el('div','✦  AI 正在回复，等待 '+duration(chatRequest?.started_at)+'…','thinking'));
  stream.scrollTop=nearBottom?stream.scrollHeight:old;updateComposer();
}
function duration(since,until=Date.now()/1000){if(!since)return '计时中';const seconds=Math.max(0,Math.floor(until-since));return seconds<60?seconds+' 秒':Math.floor(seconds/60)+' 分 '+seconds%60+' 秒';}
function renderStatus(){
  const box=$('.deployment-status');if(!box)return;box.replaceChildren();
  const job=selectedJob();if(!job)return;
  const status=executionStatus||job.status,active=['queued','analyzing','deploying','repairing'].includes(status);
  const heading=el('div',null,'status-heading');if(active)heading.append(el('span',null,'progress-spinner'));
  heading.append(el('strong',active?'本次部署尚未完成':status==='deployed'?'本次部署已完成':job.infrastructure_error?'部署环境未就绪':labels[status]||status));
  if(execution?.started_at)heading.append(el('span','耗时 '+duration(execution.started_at,execution.finished_at||Date.now()/1000),'status-time'));box.append(heading);
  const detail=active?(executionProgress?.text||'任务已提交，正在等待执行…'):status==='deployed'?(execution?.verification||job.verification||'最近一次部署检查通过。'):(execution?.error||job.error||'等待下一步操作。');
  box.append(el('p',detail,active?'execution-progress':'status-detail'));
  if(job.source_check?.same_as_deployed)box.append(el('p','本次检查未发现远端新提交；电脑里未推送的改动不会部署。','status-detail'));
  if(status==='deployed')box.append(el('p','成功提交 '+(job.deployed_commit||job.commit||'').slice(0,12)+' · 此处显示最近一次部署结果','status-detail'));
  if(active&&job.deployed_commit)box.append(el('p','现有版本仍可访问；新版本完成验证后才会标为成功。','status-detail'));
  const stale=conversationCheckedAt&&Date.now()-conversationCheckedAt>15000;
  if(conversationError||stale)box.append(el('p',conversationError||'连接暂时中断，当前显示上次状态，正在重新同步…','warn'));
  else if(conversationCheckedAt)box.append(el('p','状态同步于 '+new Date(conversationCheckedAt).toLocaleTimeString('zh-CN'),'status-detail'));
  if(active&&execution?.last_activity_at){const idle=Date.now()/1000-execution.last_activity_at;if(idle>=90)box.append(el('p','已 '+duration(execution.last_activity_at)+' 没有新进度。'+(execution.engine_checked_at&&Date.now()/1000-execution.engine_checked_at<15?'引擎仍报告执行中，继续等待。':'正在等待上游响应，尚不能确认结果。'),'warn'));}
  if(liveBuild?.error)box.append(el('p',liveBuild.error,'warn'));
}
function renderExecution(logPosition){
  let block=$('.live-build');const stream=$('.transcript');if(!stream)return;
  if(!liveBuild){block?.remove();return;}
  const active=['queued','analyzing','deploying','repairing'].includes(executionStatus);
  const key=currentId+':'+(liveBuild.deployment_uuid||'current')+':'+active;
  if(!block){block=el('details',null,'live-build');stream.before(block);}
  block.replaceChildren();block.open=logExpanded.get(key)??false;
  const head=el('summary',(active?'实时构建日志':'本次构建日志')+' · 点击'+(block.open?'收起':'展开'));block.append(head);
  block.ontoggle=()=>{logExpanded.set(key,block.open);head.textContent=(active?'实时构建日志':'本次构建日志')+' · 点击'+(block.open?'收起':'展开');};
  const logs=el('pre',liveBuild.logs||'构建任务已进入队列，等待引擎输出…','build-output');logs.tabIndex=0;block.append(logs);
  logs.scrollTop=logPosition&&!logPosition.follow?logPosition.top:logs.scrollHeight;
}
function updateActionButtons(){
  const job=selectedJob();document.querySelectorAll('[data-action]').forEach(b=>{b.disabled=!canAction(b.dataset.action,job);if(b.dataset.action==='repair')b.textContent=job?.infrastructure_error?'重试部署':'AI 修复';});
}
function showConversationError(err){conversationLoading=false;conversationError='对话暂时无法加载：'+err.message;renderMessages();}
async function loadConversation(){
  const id=currentId;if(!id)return;
  const data=await api('/jobs/'+id+'/conversation');if(currentId!==id)return;
  const lastId=transcript.at(-1)?.id;const stream=$('.transcript');const nearBottom=!stream||stream.scrollHeight-stream.scrollTop-stream.clientHeight<100;
  conversationCheckedAt=Date.now();conversationLoading=false;conversationError='';
  const value=JSON.stringify(data);if(value!==conversationSignature){conversationSignature=value;transcript=data.messages;conversationBusy=data.busy;liveBuild=data.live_build;executionProgress=data.progress;executionStatus=data.status;execution=data.execution;chatRequest=data.chat_request;
    if(lastId&&lastId!==transcript.at(-1)?.id&&!nearBottom){unreadMessages=true;const n=$('.new-messages');if(n)n.hidden=false;}
    renderMessages();updateActionButtons();
  }else renderStatus();
}
async function runAction(action,job){
  if(!job||!canAction(action,job))return;if(action==='access'){openSettings(job,'access');return;}if(action==='delete'){openDelete(job);return;}
  actionsPending.add(job.id);updateActionButtons();
  try{message('');const result=await api('/jobs/'+job.id+'/'+action,{});if(result.id){jobs=jobs.map(j=>j.id===job.id?{...j,...result}:j);renderList();}await refresh(true);await loadConversation();}catch(err){message(err.message);await refresh().catch(()=>{});}finally{actionsPending.delete(job.id);updateActionButtons();}
}
function technicalDetails(job){
  const details=el('details',null,'technical');details.append(el('summary','查看部署方案与构建参数'));
  details.append(el('p','分支：'+(job.branch||'自动识别')+' · 目录：'+job.directory,'meta'));if(job.commit)details.append(el('p','提交：'+job.commit,'meta'));
  if(job.plan){const p=job.plan;details.append(el('pre',`构建方式  ${p.build_pack}\n应用目录  ${p.base_directory}\n服务端口  ${p.port}\n发布目录  ${p.publish_directory}`+((p.is_static??(p.build_pack==='static'))?'\n首页入口  '+(p.static_entry||'index.html'):'')));for(const [name,content] of Object.entries(p.generated_files||{}))details.append(el('pre',name+'\n'+content));for(const k of ['install_command','build_command','start_command'])if(p[k])details.append(el('pre',k+'\n'+p[k]));for(const note of [...(p.missing_env||[]).map(x=>'待配置变量：'+x),...(p.databases||[]).map(x=>'数据库 / 持久化：'+x),...(p.notes||[])])details.append(el('p',note,'hint'));}
  for(const a of [...(job.repair_history||[]),...(job.repair_attempts||[])]){details.append(el('p',`自动修复 ${a.number}：${a.reason||a.repair_error||'诊断中'}`,'hint'));if(a.plan?.generated_files)for(const [name,content] of Object.entries(a.plan.generated_files))details.append(el('pre',name+'\n'+content));}
  if(job.deployed_commit)details.append(el('p','最近成功部署：'+job.deployed_commit.slice(0,12),'meta'));return details;
}
function modal(title){const d=el('dialog',null,'project-dialog');const head=el('div',null,'section-head');head.append(el('h2',title),button('关闭',()=>d.close(),'quiet'));d.append(head);d.addEventListener('close',()=>{editing=false;d.remove();});document.body.append(d);return d;}
function openSettings(job,focus){
  const d=modal('项目设置');d.append(el('p',job.slug+' · '+job.repository,'hint'));const form=el('form');const access=accessEditor(job.access);form.append(access);const save=el('button','保存访问权限','primary');save.type='submit';form.append(save);form.onsubmit=async e=>{e.preventDefault();save.disabled=true;try{job.access=await api('/jobs/'+job.id+'/access',access.value());editing=false;d.close();await refresh(true);message('访问权限已保存，立即生效。');}catch(err){message(err.message);}finally{save.disabled=false;}};d.append(form,technicalDetails(job));
  if(job.application_uuid)d.append(el('p','公网地址：https://'+job.slug+'.preview.greatsong.online','hint'));
  const danger=el('div',null,'danger-zone');danger.append(el('div','删除此部署','danger-title'),el('p','下线项目，移除工作台记录与应用配置。源仓库和持久化数据卷会保留。','hint'));const del=button('删除部署…',()=>{d.close();openDelete(job);},'danger');del.disabled=!canAction('delete',job);danger.append(del);if(del.disabled)danger.append(el('p','请等待当前任务或 AI 回复完成后再删除。','hint'));d.append(danger);d.showModal();if(focus==='access')d.querySelector('select').focus();
}
function openDelete(job){
  const d=modal('删除部署');d.append(el('p','删除后，'+job.slug+' 将无法访问。应用配置、工作台对话与源码缓存会被移除；GitHub 源仓库和持久化数据卷保留。','delete-copy'));
  const form=el('form');const input=field(form,'输入项目名称「'+job.slug+'」确认','confirm',{required:true,autocomplete:'off'});const error=el('p',null,'warn');error.setAttribute('role','alert');const submit=el('button','确认删除部署','danger solid');submit.type='submit';submit.disabled=true;input.oninput=()=>{submit.disabled=input.value!==job.slug;};form.append(error,submit);form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;input.disabled=true;try{const result=await api('/jobs/'+job.id+'/delete',{confirm:input.value});d.close();jobs=jobs.filter(j=>j.id!==job.id);location.hash=jobs.length?'/projects/'+jobs[0].id:'/';await refresh(true);message(result.message);}catch(err){error.textContent=err.message;submit.disabled=false;input.disabled=false;}};d.append(form);d.showModal();input.focus();
}
async function openAccounts(){await reloadAccounts();$('#account-dialog').showModal();}
async function reloadAccounts(){accounts=await api('/accounts');const list=$('#account-list');list.replaceChildren();for(const name of accounts){const row=el('div',null,'account-row');row.append(el('span',name),button('删除',async()=>{if(!confirm('删除账号 '+name+'？其项目访问权限也会撤销。'))return;try{await api('/accounts/'+encodeURIComponent(name)+'/delete',{});await reloadAccounts();}catch(e){$('#account-message').textContent=e.message;}},'quiet'));list.append(row);}}
$('#account-form').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{await api('/accounts',Object.fromEntries(new FormData(e.target)));e.target.reset();await reloadAccounts();$('#account-message').textContent='账号已创建。关闭后勾选账号并保存权限。';}catch(err){$('#account-message').textContent=err.message;}finally{b.disabled=false;}};
$('#close-accounts').onclick=()=>$('#account-dialog').close();
$('#account-dialog').addEventListener('close',()=>{for(const editor of document.querySelectorAll('.access-editor')){const replacement=accessEditor(editor.value());editor.replaceChildren(...replacement.childNodes);editor.value=replacement.value;}});

async function refresh(force=false){
  if(refreshing)return;refreshing=true;
  try{const next=await api('/jobs');if(connectionWarning){connectionWarning=false;message('');}const value=JSON.stringify(next);jobs=next;
    const focused=document.activeElement;const composing=focused?.matches('textarea');
    if(force||value!==signature){if((force||!editing)&&!document.querySelector('dialog[open]')&&location.hash!=='#/new'&&!focused?.matches('input,select')){signature=value;render();if(composing){const t=$('.composer textarea');t?.focus();t?.setSelectionRange(t.value.length,t.value.length);}}else renderList();}
    updateActionButtons();if(currentId)await loadConversation();
  }finally{refreshing=false;}
}
async function enter(){
  clearInterval(timer);$('#login-panel').hidden=true;$('#workspace').hidden=true;
  bootState('正在打开部署工作台','正在确认登录状态…');
  const me=await api('/me');csrf=me.csrf;publicEnabled=me.public_enabled;
  bootState('正在载入你的项目','正在读取部署列表与访问设置…');
  const [next,availableAccounts]=await Promise.all([api('/jobs'),api('/accounts')]);
  jobs=next;accounts=availableAccounts;signature=JSON.stringify(next);$('#identity').textContent=me.email;
  render();hideBoot();$('#workspace').hidden=false;$('#logout').hidden=false;$('#server-resources').hidden=false;
  timer=setInterval(()=>refresh().catch(()=>{connectionWarning=true;conversationError='连接暂时中断，显示上次状态，正在重试。';renderStatus();}),2000);
}
function entryFailure(error){
  if(error.status===401){hideBoot();$('#login-panel').hidden=false;$('#workspace').hidden=true;$('#logout').hidden=true;$('#server-resources').hidden=true;}
  else bootState('暂时无法载入工作台',error.message+'。请重新加载重试。',true);
}
$('#login-form').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;b.textContent='正在登录…';try{await api('/login',Object.fromEntries(new FormData(e.target)));e.target.reset();message('');await enter();}catch(err){if($('#boot-panel').hidden)message(err.message);else entryFailure(err);}finally{b.disabled=false;b.textContent='登录';}};
$('#logout').onclick=async()=>{await api('/logout',{});location.reload();};
window.addEventListener('hashchange',()=>{editing=false;message('');if(csrf)render();});
window.startWorkbench=()=>enter().catch(entryFailure);
window.addEventListener('online',()=>{if(csrf)refresh().catch(showConversationError);});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&csrf)refresh().catch(showConversationError);});
setInterval(()=>{renderStatus();const thinking=$('.thinking');if(thinking&&conversationBusy)thinking.textContent='✦ AI 正在回复，等待 '+duration(chatRequest?.started_at)+'…';},1000);

function bytes(value){if(value===null||value===undefined)return '暂不可用';const unit=value>=1024**3?'GiB':'MiB';return (value/(unit==='GiB'?1024**3:1024**2)).toFixed(2)+' '+unit;}
function resourceTable(headers,rows){const wrap=el('div',null,'resource-table-wrap'),table=el('table',null,'resource-table'),head=el('tr');for(const h of headers)head.append(el('th',h));const thead=el('thead');thead.append(head);table.append(thead);const body=el('tbody');for(const values of rows){const row=el('tr');for(const value of values)row.append(el('td',String(value)));body.append(row);}table.append(body);wrap.append(table);return wrap;}
async function renderResources(root){
  const head=el('div',null,'workspace-head');const refreshButton=button('刷新用量',()=>renderResources(root));const actions=el('div',null,'header-actions');actions.append(button('清理空间',openCleanup),refreshButton);head.append(titleBlock('服务器空间与分配','磁盘共享使用 · 每分钟采集一次'),actions);root.replaceChildren(head);
  const body=el('div',null,'resources-body');body.append(el('p','正在读取服务器用量…'));root.append(body);
  try{
    refreshButton.disabled=true;const data=await api('/resources');if(!root.isConnected)return;body.replaceChildren();
    const sampled=new Date(data.sampled_at*1000).toLocaleString('zh-CN');body.append(el('p','采集时间：'+sampled+(data.stale?' · 数据已过期，等待采集恢复':' · 刷新读取最近一次采集结果'),data.stale?'warn':'hint'));
    const cards=el('div',null,'resource-cards');
    for(const [title,value,note] of [['磁盘已用',bytes(data.disk.used),((data.disk.used/data.disk.total)*100).toFixed(1)+'% / 总计 '+bytes(data.disk.total)],['磁盘可用',bytes(data.disk.available),'文件系统保留 '+bytes(data.disk.reserved)],['内存使用',bytes(data.memory.used),'可用 '+bytes(data.memory.available)+' / 总计 '+bytes(data.memory.total)]]){const c=el('article',null,'resource-card');c.append(el('span',title),el('strong',value),el('p',note));cards.append(c);}body.append(cards);
    const meter=el('progress');meter.max=data.disk.total;meter.value=data.disk.used;meter.setAttribute('aria-label','磁盘使用比例');body.append(meter);
    if(data.disk.available/data.disk.total<.1)body.append(el('p','可用磁盘不足 10%，后续构建可能因空间不足失败。','warn'));
    body.append(el('h2','磁盘占用分布'),resourceTable(['分类','实际占用'],data.categories.map(c=>[c.name+(c.on_root===false?'（独立文件系统）':''),bytes(c.bytes)])));
    body.append(el('p','按文件占用块统计，容器镜像层包含共享数据，不能按项目重复相加。系统与其他文件为估算余量；统计期间有写入时会有小幅差异。','hint'));
    body.append(el('h2','项目使用与额度'),el('p',data.disk_quota,'hint'));
    body.append(resourceTable(['项目','源码缓存','容器当前内存','容器内存上限','容器可写层'],data.projects.map(p=>{
      const running=p.containers.filter(c=>c.running), limits=running.map(c=>c.memory_limit?bytes(c.memory_limit):'未限制');
      return [p.name,bytes(p.source_bytes),running.length?running.map(c=>c.memory_usage||'暂不可用').join(' + '):'没有运行容器',limits.join(' + ')||'尚无运行容器',p.containers.length?bytes(p.containers.reduce((n,c)=>n+(c.size_rw||0),0)):'—'];
    })));
    body.append(el('p','源码缓存已包含在“部署源码与记录”中。容器可写层不含镜像与持久卷；持久卷包含在 Docker 数据中。所有项目共用可用磁盘，当前未划分固定磁盘额度。','hint'));
    body.append(el('h2','全部容器资源'),resourceTable(['容器','状态','内存使用','内存上限','CPU'],data.containers.map(c=>[c.name.replace(/^\//,''),c.running?'运行中':'已停止',c.memory_usage||'—',c.memory_limit?bytes(c.memory_limit):'未限制',c.cpu_percent||'—'])));
    for(const error of data.errors||[])body.append(el('p',error,'warn'));
  }catch(error){body.replaceChildren(el('p',error.message,'warn'),button('重新读取',()=>renderResources(root)));}finally{refreshButton.disabled=false;}
}

async function openCleanup(){
  const d=modal('清理服务器空间');d.classList.add('cleanup-dialog');
  const intro=el('p','先扫描、勾选并确认，再清理。运行中或已停止容器引用的镜像、基础镜像、共享层会保留；有部署进行时不执行清理。','hint');
  const scope=el('p','只清理无引用且超过 24 小时的项目镜像，以及闲置超过 1 小时的独占构建缓存。容器、数据卷、源码和备份保留。清理缓存后，下次构建可能需要重新下载依赖。','hint');
  const body=el('div');d.append(intro,scope,body);d.showModal();
  let pollTimer,view='',chosen=new Set(),snapshot=null;
  d.addEventListener('close',()=>clearTimeout(pollTimer));
  function fail(error){body.replaceChildren(el('p',error.message,'warn'),button('重新读取',poll));}
  async function scan(){clearTimeout(pollTimer);body.replaceChildren(el('p','正在扫描可清理资源…','hint'));view='';chosen.clear();try{draw(await api('/cleanup/scan',{}));schedule();}catch(error){fail(error);}}
  function schedule(){if(d.open)pollTimer=setTimeout(poll,1500);}
  async function poll(){try{const data=await api('/cleanup');if(!d.open)return;draw(data);if(['scanning','cleaning','busy'].includes(data.status))schedule();}catch(error){fail(error);}}
  function draw(data){
    snapshot=data;
    if(data.status==='preview'&&view==='preview'&&data.token===body.dataset.token)return;
    view=data.status;body.replaceChildren();
    if(data.status==='idle'){body.append(button('扫描可清理资源',scan,'primary'));return;}
    if(['scanning','cleaning','busy'].includes(data.status)){body.append(el('p',data.message||'正在处理…','execution-progress'));if(data.status==='cleaning')body.append(el('p','任务由服务器执行，关闭窗口后仍会继续；重新打开可查看结果。','hint'));return;}
    if(data.status==='complete'||data.status==='failed'){
      body.append(el('h3',data.status==='complete'?'清理已结束':'清理未全部完成'),el('p',data.message,data.status==='failed'?'warn':'hint'));
      if(data.available_delta_bytes!==null&&data.available_delta_bytes!==undefined)body.append(el('p','本次磁盘可用空间变化：'+(data.available_delta_bytes<0?'-':'+')+bytes(Math.abs(data.available_delta_bytes))+'。此数值受同时发生的系统写入影响。','hint'));
      if(data.report?.length)body.append(resourceTable(['资源','处理结果'],data.report.map(r=>[r.key,({removed:'已清理',retained:'引擎保留',already_absent:'已不存在'})[r.result]||r.result])));
      body.append(button('重新扫描',scan),button('返回空间用量',()=>{d.close();const root=$('.workspace-content');if(location.hash==='#/resources')renderResources(root);}));return;
    }
    body.dataset.token=data.token;
    const available=data.entries.filter(e=>e.eligible),protectedItems=data.entries.filter(e=>!e.eligible);
    body.append(el('p','扫描于 '+new Date(data.sampled_at*1000).toLocaleTimeString('zh-CN')+' · 预览 10 分钟内有效，执行前会重新核验。','hint'));
    const total=el('p',null,'cleanup-total');body.append(total);
    const options=el('div',null,'cleanup-options');const confirmation=el('label',null,'check');const confirm=el('input');confirm.type='checkbox';confirmation.append(confirm,document.createTextNode('我已核对选中清单，确认清理这些可重建资源。'));
    const submit=button('确认清理选中资源',async()=>{
      if(!confirm.checked||!chosen.size)return;
      submit.disabled=true;
      try{const result=await api('/cleanup/confirm',{token:data.token,selected:[...chosen],confirm:'清理选中资源'});draw(result);schedule();}catch(error){errorText.textContent=error.message;submit.disabled=false;}
    },'danger solid');const errorText=el('p',null,'warn');
    function update(){const selected=available.filter(e=>chosen.has(e.key));total.textContent='已选 '+selected.length+' 项 · 预计可释放约 '+bytes(selected.reduce((sum,e)=>sum+e.estimated_bytes,0));submit.disabled=!selected.length||!confirm.checked||Date.now()/1000>data.expires_at;}
    for(const entry of available){const row=el('label',null,'cleanup-option');const checkbox=el('input');checkbox.type='checkbox';checkbox.onchange=()=>{if(checkbox.checked)chosen.add(entry.key);else chosen.delete(entry.key);confirm.checked=false;update();};const copy=el('span');copy.append(el('strong',(entry.kind==='image'?'镜像 · ':'构建缓存 · ')+entry.name),el('span',entry.reason+' · 预计 '+bytes(entry.estimated_bytes),'hint'));row.append(checkbox,copy);options.append(row);}
    if(!available.length)options.append(el('p','当前没有符合条件的资源；近期或正在引用的资源已保留。','hint'));
    else body.append(button('选择全部可清理项',()=>{chosen=new Set(available.map(e=>e.key));options.querySelectorAll('input').forEach(i=>i.checked=true);confirm.checked=false;update();},'quiet'));
    confirm.onchange=update;body.append(options,el('p','估算使用镜像独占空间和独占缓存大小；共享层不重复相加，实际释放可能不同。','hint'),confirmation,errorText,submit,button('重新扫描',scan));update();
    if(protectedItems.length){const details=el('details',null,'technical');details.append(el('summary','已保护 '+protectedItems.length+' 项 · 查看保留原因'),resourceTable(['资源','保留原因'],protectedItems.map(e=>[e.name,e.reason])));body.append(details);}
  }
  await poll();
}
