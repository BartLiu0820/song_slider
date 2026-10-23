// Keep the loading shell visible even while the main stylesheet or script is slow.
(()=>{
  const shell=document.querySelector('#boot-panel'),title=document.querySelector('#boot-title'),detail=document.querySelector('#boot-detail');
  const slow=setTimeout(()=>{detail.textContent='连接比平时慢，仍在加载。你可以稍候，或重新加载页面。';},8000);
  function fail(){clearTimeout(slow);shell.dataset.state='error';title.textContent='加载暂时未完成';detail.textContent='网络连接超时或文件加载失败，请重新加载。';}
  function resource(tag,attributes){return new Promise((resolve,reject)=>{const node=Object.assign(document.createElement(tag),attributes);node.onload=resolve;node.onerror=reject;document.head.append(node);});}
  const deadline=setTimeout(fail,25000);
  Promise.all([resource('link',{rel:'stylesheet',href:'/assets/style.css?v=20261022-cleanup-chat'}),resource('script',{src:'/assets/app.js?v=20261022-cleanup-chat'})]).then(()=>{clearTimeout(slow);clearTimeout(deadline);window.startWorkbench();}).catch(()=>{clearTimeout(deadline);fail();});
})();
