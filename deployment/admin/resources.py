"""Read-only host metrics collector. Publishes no credentials or container env.

Runs separately from the web service; the web worker never gets Docker/root access.
Directory sizes are allocated blocks on each filesystem, excluding mounted children.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

STATE = Path('/var/lib/song-deploy')
OUTPUT = Path('/run/song-deploy-metrics/resources.json')


def command(args, timeout=20):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True).stdout


def usage(path):
    if not Path(path).exists():return 0
    return int(command(['du','-skx',str(path)],timeout=25).split()[0])*1024


def memory():
    values={k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
    return {'total':values['MemTotal'],'available':values['MemAvailable'],
            'used':values['MemTotal']-values['MemAvailable']}


def collect():
    result={'sampled_at':int(time.time()),'errors':[],'projects':[],'categories':[], 'containers':[]}
    fs=os.statvfs('/')
    result['disk']={'total':fs.f_blocks*fs.f_frsize,'used':(fs.f_blocks-fs.f_bfree)*fs.f_frsize,
                    'available':fs.f_bavail*fs.f_frsize,'reserved':(fs.f_bfree-fs.f_bavail)*fs.f_frsize}
    result['memory']=memory()
    jobs=[]
    for path in STATE.glob('*.json'):
        try:
            job=json.loads(path.read_text())
            if re.fullmatch('[a-f0-9]{24}',str(job.get('id',''))):jobs.append(job)
        except (OSError,ValueError):result['errors'].append('有项目状态暂时无法读取')
    try:
        docker_root=command(['docker','info','--format','{{.DockerRootDir}}']).strip()
        if not docker_root.startswith('/'):raise ValueError('Invalid root')
    except Exception:
        docker_root='/var/lib/docker';result['errors'].append('Docker 存储位置暂时无法确认，使用默认路径')
    paths=[('容器与镜像数据',docker_root),('Containerd 镜像层','/var/lib/containerd'),
           ('平台备份','/var/backups/song-deploy'),('部署源码与记录',str(STATE)),('部署引擎数据','/data/coolify')]
    # Do not double-count directories nested under a previously measured category.
    measured=[];root_device=os.stat('/').st_dev
    for name,path in paths:
        actual=Path(path).resolve()
        if any(actual==p or p in actual.parents for p in measured):continue
        measured.append(actual)
        try:
            size=usage(actual)
            on_root=not actual.exists() or actual.stat().st_dev==root_device
            result['categories'].append({'name':name,'bytes':size,'on_root':on_root})
        except Exception:result['categories'].append({'name':name,'bytes':None,'on_root':True});result['errors'].append(name+' 暂时无法统计')
    known=sum(c['bytes'] or 0 for c in result['categories'] if c['on_root'])
    if all(c['bytes'] is not None for c in result['categories']):
        result['categories'].append({'name':'系统与其他文件','bytes':max(0,result['disk']['used']-known),'on_root':True})
    containers=[];stats={}
    try:
        ids=command(['docker','ps','-aq']).split()
        # Limit output to required fields rather than dumping secret-bearing inspect data.
        template='{"id":{{json .Id}},"name":{{json .Name}},"running":{{json .State.Running}},"memory_limit":{{json .HostConfig.Memory}},"size_rw":{{json .SizeRw}},"app":{{json (index .Config.Labels "coolify.applicationId")}},"resource":{{json (index .Config.Labels "coolify.resourceName")}}}'
        if ids:containers=[json.loads(s) for s in command(['docker','inspect','--size','--format',template,*ids],timeout=30).splitlines()]
        stats={s['ID']:s for s in [json.loads(line) for line in command(['docker','stats','--no-stream','--format','{{json .}}']).splitlines()]}
        for c in containers:
            sample=stats.get(c['id'][:12],{})
            c['memory_usage']=sample.get('MemUsage','').split(' / ')[0] or None
            c['cpu_percent']=sample.get('CPUPerc')
        result['containers']=[{k:c[k] for k in ['name','running','memory_limit','size_rw','memory_usage','cpu_percent']} for c in containers]
    except Exception:result['errors'].append('容器用量暂时无法统计，不能按零占用理解')
    for job in jobs:
        matches=[c for c in containers if job.get('application_uuid') and c['name'].lstrip('/').startswith(job['application_uuid']+'-')]
        try:source=sum(usage(p) for p in (STATE/'repos').glob(job['id']+'*.git'))
        except Exception:source=None;result['errors'].append(job['slug']+' 源码缓存暂时无法统计')
        result['projects'].append({'id':job['id'],'name':job['slug'],'source_bytes':source,
            'containers':[{k:c[k] for k in ['name','running','memory_limit','size_rw','memory_usage','cpu_percent']} for c in matches],
            'planned_memory_mb':job.get('plan',{}).get('memory_mb',512)})
    result['collected_at']=int(time.time())
    return result


def main():
    result=collect()
    OUTPUT.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    # Parent is root-owned and read-only to the agent. Atomic publication keeps reads fast.
    temp=OUTPUT.with_suffix('.tmp')
    temp.write_text(json.dumps(result,ensure_ascii=False));temp.chmod(0o644);temp.replace(OUTPUT)


if __name__=='__main__':main()
