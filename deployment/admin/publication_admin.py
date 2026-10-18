"""Root-only publication configuration; invoked explicitly over SSH."""
import argparse
import json
from pathlib import Path
import re
import secrets
import sys
import time

ROOT=Path('/var/lib/song-deploy')
STATE=ROOT/'system/publication.json'
ROUTES=Path('/data/coolify/proxy/dynamic/song-workbench.yaml')
SITE=Path('/home/admin/song_slider/output/song-six-stages-v4/index.html')
HOST='deploy.greatsong.online'
READY='/_song/ready'


def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,indent=2)+'\n')
    temp.chmod(0o644)
    temp.replace(path)


def read_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {
        'enabled':False,'tls_prepared':False,'proof':secrets.token_hex(24)}


def applications():
    result=[]
    for path in ROOT.glob('*.json'):
        job=json.loads(path.read_text())
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,38}[a-z0-9]',job.get('slug','')):continue
        if (job.get('status')=='deployed' or job.get('deployed_commit')) and job.get('application_uuid') and re.fullmatch(r'[a-z0-9]{20,32}',job['application_uuid']):
            result.append(job)
    return result


def routes(tls, jobs):
    routers={'song-workbench-http':{'rule':f'Host(`{HOST}`)','entryPoints':['http'],
             'priority':50000,'service':'song-workbench'}}
    routers['song-preview-probe']={'rule':r'HostRegexp(`^[a-z0-9-]+\.preview\.greatsong\.online$`) && Path(`'+READY+'`)','entryPoints':['http'],'priority':60000,'service':'song-workbench'}
    services={'song-workbench':{'loadBalancer':{'servers':[{'url':'http://172.21.0.1:9100'}]}}}
    if tls:
        routers['song-preview-probe-tls']={**routers['song-preview-probe'],'entryPoints':['https'],'tls':{}}
        routers['song-workbench-https']={**routers['song-workbench-http'],'entryPoints':['https'],
                                       'tls':{'certResolver':'letsencrypt'}}
    for job in jobs:
        host=job['slug']+'.preview.greatsong.online';key='song-'+job['id']
        probe={'rule':f'Host(`{host}`) && Path(`{READY}`)','entryPoints':['http'],
               'priority':60000,'service':'song-workbench'}
        routers[key+'-probe']=probe
        if tls:
            routers[key+'-probe-tls']={**probe,'entryPoints':['https'],'tls':{'certResolver':'letsencrypt'}}
            # Coolify's second domain is the persistent local-preview service. Its
            # name remains stable when the first domain switches from HTTP to HTTPS.
            routers[key+'-tls']={'rule':f'Host(`{host}`)','entryPoints':['https'],
                'priority':50000,'service':'http-1-'+job['application_uuid']+'@docker',
                'tls':{'certResolver':'letsencrypt'}}
    return {'http':{'routers':routers,'services':services}}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','stage-tls','enable','rollback','status'])
    args=parser.parse_args();state=read_state();jobs=applications()
    if args.action=='prepare':
        if not STATE.exists():atomic(STATE,state)
        atomic(ROUTES,routes(state['tls_prepared'],jobs))
    elif args.action=='stage-tls':
        state['tls_prepared']=True;atomic(STATE,state);atomic(ROUTES,routes(True,jobs))
    elif args.action=='enable':
        if not state['tls_prepared']:raise SystemExit('Stage and verify trusted TLS certificates first')
        state.update(enabled=True,enabled_at=int(time.time()));atomic(STATE,state)
        content=SITE.read_text().replace('href="http://127.0.0.1:19100" aria-label="登录本机部署工作台"',
            'href="https://deploy.greatsong.online" aria-label="登录部署工作台"')
        SITE.write_text(content)
    elif args.action=='rollback':
        state.update(enabled=False,tls_prepared=False);atomic(STATE,state);atomic(ROUTES,routes(False,jobs))
        SITE.write_text(SITE.read_text().replace('href="https://deploy.greatsong.online" aria-label="登录部署工作台"',
            'href="http://127.0.0.1:19100" aria-label="登录本机部署工作台"'))
    print(json.dumps({**state,'hosts':[HOST]+[j['slug']+'.preview.greatsong.online' for j in jobs]},ensure_ascii=False))

if __name__=='__main__':main()
