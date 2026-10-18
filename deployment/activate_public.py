"""One-shot public activation. Stops before changes if the provider still blocks HTTP.

Normal: python3 deployment/activate_public.py
Read only: python3 deployment/activate_public.py --check
Rollback: python3 deployment/activate_public.py --rollback
"""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
import urllib.error

SSH=['ssh','-o','BatchMode=yes','-S',str(Path.home()/'.ssh/song-deploy-tunnel.sock'),'songhuang-server']
ADMIN='sudo -n python3 /opt/song-deploy/admin/publication_admin.py '
HTTP=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def command(action):
    return json.loads(subprocess.check_output(SSH+[ADMIN+action],text=True,timeout=30))


def probe(host,scheme,proof):
    try:
        with HTTP.open(scheme+'://'+host+'/_song/ready',timeout=8) as response:
            result=json.load(response)
            return result.get('service')=='song-deploy' and result.get('proof')==proof,'来源校验'
    except urllib.error.HTTPError as e:return False,'HTTP '+str(e.code)+'（可能仍有备案拦截）'
    except (OSError,ValueError) as e:return False,type(e).__name__+'（连接或可信证书未就绪）'


def sync_local_link(public):
    site=Path(__file__).resolve().parents[1]/'output/song-six-stages-v4/index.html'
    old='href="http://127.0.0.1:19100" aria-label="登录本机部署工作台"'
    new='href="https://deploy.greatsong.online" aria-label="登录部署工作台"'
    if site.exists():site.write_text(site.read_text().replace(old if public else new,new if public else old))


def main():
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group()
    group.add_argument('--check',action='store_true');group.add_argument('--rollback',action='store_true')
    args=parser.parse_args()
    if args.rollback:
        command('rollback');sync_local_link(False);print('已关闭公网发布，保留本机 SSH 访问。');return
    state=command('status');errors=[]
    for host in state['hosts']:
        ok,reason=probe(host,'http',state['proof'])
        print(host+': '+('HTTP 来源校验通过' if ok else reason),flush=True)
        if not ok:errors.append(host)
    if errors:raise SystemExit('尚未解除公网阻塞；没有启用发布，也没有发起新的证书申请。')
    if args.check:
        print('HTTP 已可达，可以执行不带 --check 的命令启用 HTTPS 并完成验收。');return
    state=command('stage-tls')
    print('已配置证书申请，等待受信任的 HTTPS；工作台尚未向公网开放登录。',flush=True)
    pending=set(state['hosts']);deadline=time.monotonic()+180
    while pending and time.monotonic()<deadline:
        for host in list(pending):
            ok,_=probe(host,'https',state['proof'])
            if ok:pending.remove(host);print(host+': 可信 HTTPS 已通过',flush=True)
        if pending:
            print('等待证书：'+', '.join(sorted(pending)),flush=True);time.sleep(8)
    if pending:raise SystemExit('证书尚未全部就绪。公网登录仍关闭，稍后重新执行即可。')
    command('enable')
    # Validate authenticated web session on the real HTTPS hostname; credentials
    # never enter CLI arguments, output, application logs or browser screenshots.
    import http.cookiejar
    jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
    credential=json.loads((Path.home()/'.config/song-deploy/admin-credentials.json').read_text())
    try:
        req=urllib.request.Request('https://deploy.greatsong.online/api/login',data=json.dumps(credential).encode(),headers={'Content-Type':'application/json'})
        with client.open(req,timeout=15) as response:login=json.load(response)
        assert any(c.secure and c.name=='song_deploy_session' for c in jar),'Secure Cookie missing'
        with client.open('https://deploy.greatsong.online/api/jobs',timeout=15) as response:jobs=json.load(response)
        for job in jobs:
            if job['status']!='deployed':continue
            url='https://'+job['slug']+'.preview.greatsong.online'
            try:
                with HTTP.open(url,timeout=15) as response:status=response.status
            except urllib.error.HTTPError as e:status=e.code
            expected=200 if job['access']['mode']=='public' else 401
            assert status==expected,job['slug']+' access check failed'
        req=urllib.request.Request('https://deploy.greatsong.online/api/logout',data=b'{}',headers={'Content-Type':'application/json','X-CSRF-Token':login['csrf']})
        client.open(req,timeout=15).close()
    except Exception:
        command('rollback');raise SystemExit('公网验收未通过，已恢复本机模式。请查看服务器状态后重试。')
    sync_local_link(True)
    print('公网工作台、Secure Cookie 和项目访问权限验收通过。入口：https://deploy.greatsong.online')

if __name__=='__main__':main()
