"""Allowlisted cleanup broker: preview -> explicit confirmation -> exact IDs.

The web service gets a narrow local socket, never Docker or sudo access. No
container, volume, network, source or backup deletion operation exists here.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import socket
import socketserver
import struct
import subprocess
import threading
import time
import urllib.parse
import urllib.request

STATE=Path('/var/lib/song-deploy')
RUNTIME=Path('/run/song-deploy-cleanup')
AUDIT=Path('/var/lib/song-deploy-cleanup')
LOCK=threading.RLock()
CURRENT={'status':'idle'}
OWNER=None
IMAGE_AGE=86400
CACHE_AGE=3600
TTL=600

class Rejected(ValueError):pass


def docker(method,path):
    class LocalDocker(http.client.HTTPConnection):
        def connect(self):
            self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            self.sock.settimeout(30);self.sock.connect('/var/run/docker.sock')
    connection=LocalDocker('localhost',timeout=30)
    try:
        connection.request(method,path);response=connection.getresponse();payload=response.read()
        if response.status>=400:raise Rejected('Docker 拒绝操作（HTTP '+str(response.status)+'），资源可能正在使用，已保留。')
        return json.loads(payload) if payload else {}
    finally:connection.close()


def timestamp(value):
    if isinstance(value,(int,float)):return value
    try:return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
    except (ValueError,TypeError,AttributeError):return None


def jobs():return [json.loads(p.read_text()) for p in STATE.glob('*.json')]


def assert_idle():
    if any(j.get('status') in ['queued','analyzing','deploying','repairing','deleting'] for j in jobs()):
        raise Rejected('有部署任务正在进行，请完成后再清理。')
    config=json.loads(Path('/etc/song-deploy/agent.json').read_text())
    req=urllib.request.Request('http://127.0.0.1:8000/api/v1/deployments',headers={'Authorization':'Bearer '+config['coolify_token']})
    try:
        with urllib.request.urlopen(req,timeout=10) as response:pending=json.load(response)
    except Exception:raise Rejected('无法确认构建引擎是否空闲，已停止清理。') from None
    if not isinstance(pending,list) or pending:raise Rejected('构建引擎有排队或执行中的任务，请稍后清理。')
    running=docker('GET','/containers/json')
    # Coolify creates helper containers with the deployment UUID as their name.
    for c in running:
        image=c.get('Image','').lower()
        if 'coolify-helper' in image or 'buildkit' in image:
            raise Rejected('检测到构建容器，已停止清理。')


def inventory(data, projects, now=None):
    now=time.time() if now is None else now
    apps={j.get('application_uuid'):j.get('slug','项目') for j in projects if j.get('application_uuid')}
    referenced={c.get('ImageID') for c in data.get('Containers',[])}
    entries=[]
    for image in data.get('Images',[]):
        identity=image.get('Id','');tags=[t for t in image.get('RepoTags',[]) or [] if t!='<none>:<none>']
        if not re.fullmatch('sha256:[a-f0-9]{64}',identity):continue
        created=timestamp(image.get('Created'));reason=None
        owned=bool(tags) and all(t.split(':',1)[0] in apps for t in tags)
        if image.get('Containers',-1)!=0 or identity in referenced:reason='被运行中或已停止的容器引用'
        elif tags and not owned:reason='保留基础镜像和平台镜像'
        elif created is None or now-created<IMAGE_AGE:reason='创建不足 24 小时，保留近期镜像'
        elif image.get('SharedSize',-1)<0:reason='无法可靠估算独占空间'
        size=max(0,image.get('Size',0)-max(0,image.get('SharedSize',0)))
        entries.append({'key':'image:'+identity,'kind':'image','id':identity,'name':', '.join(tags) or '未标记镜像 '+identity[7:19],
            'estimated_bytes':size,'size_bytes':image.get('Size',0),'eligible':reason is None,'reason':reason or '无容器引用，创建超过 24 小时',
            'last_used_at':created,'fingerprint':hashlib.sha256(json.dumps(sorted(tags)).encode()).hexdigest()})
    for cache in data.get('BuildCache',[]):
        identity=cache.get('ID','')
        if not re.fullmatch('[a-zA-Z0-9_-]{8,80}',identity):continue
        used=timestamp(cache.get('LastUsedAt') or cache.get('CreatedAt'));reason=None
        if cache.get('InUse',True):reason='构建引擎仍在引用'
        elif cache.get('Shared',True):reason='与镜像共享，保留共享层'
        elif used is None or now-used<CACHE_AGE:reason='最近 1 小时使用过，保留近期缓存'
        elif cache.get('Type') in ['internal','frontend']:reason='保留构建工具基础缓存'
        # Descriptions can contain build commands/secrets; expose only type and ID.
        entries.append({'key':'cache:'+identity,'kind':'cache','id':identity,'name':cache.get('Type','cache')+' · '+identity,
            'estimated_bytes':max(0,cache.get('Size',0)),'size_bytes':max(0,cache.get('Size',0)),
            'eligible':reason is None,'reason':reason or '闲置超过 1 小时，无引用且不与镜像共享',
            'last_used_at':used,'fingerprint':str(used)})
    return entries


def snapshot():return inventory(docker('GET','/system/df'),jobs())


@contextmanager
def maintenance():
    with (RUNTIME/'maintenance.lock').open('rb') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Rejected('部署操作正在使用资源，请稍后重试。') from None
        try:yield
        finally:fcntl.flock(handle,fcntl.LOCK_UN)


def publish(**changes):
    with LOCK:
        CURRENT.update(changes)
        if CURRENT.get('status') in ['complete','failed'] and CURRENT.get('selected'):persist()


def persist():
    AUDIT.mkdir(mode=0o700,parents=True,exist_ok=True)
    target=AUDIT/'latest.json';temporary=target.with_suffix('.tmp')
    temporary.write_text(json.dumps({'owner':OWNER,'state':CURRENT},ensure_ascii=False));temporary.chmod(0o600);temporary.replace(target)


def scan():
    try:
        entries=snapshot()
        publish(status='preview',entries=entries,token=secrets.token_hex(24),expires_at=int(time.time())+TTL,
                sampled_at=int(time.time()),message='请勾选待清理项，确认后才会删除。')
    except Exception:
        publish(status='failed',message='读取可清理资源失败，请稍后重新扫描。')


def delete_one(entry):
    if entry['kind']=='image':
        # force=false preserves referenced images, including a newly created container.
        # noprune=true prevents cascading removal of unselected parent images.
        docker('DELETE','/images/'+urllib.parse.quote(entry['id'],safe='')+'?force=false&noprune=true')
    else:
        # Buildx treats id as a regexp, so anchor it. BuildKit boolean fields are
        # presence flags with an empty value (private=""), not the string true.
        # BuildKit itself refuses in-use records; snapshot() also checks InUse.
        result=subprocess.run(['docker','buildx','prune','--builder','default','--force',
            '--filter','id=^'+entry['id']+'$','--filter','until=1h','--filter','private=""'],
            capture_output=True,text=True,timeout=90)
        if result.returncode:raise Rejected('构建引擎未能清理选中的缓存，已停止。')


def execute(entries,token):
    report=[];before=None;after=None
    try:
        with maintenance():
            assert_idle()
            fresh={e['key']:e for e in snapshot()}
            for old in entries:
                current=fresh.get(old['key'])
                if not current or not current['eligible'] or current['fingerprint']!=old['fingerprint']:
                    raise Rejected('资源状态已变化，未执行清理。请重新扫描并确认。')
            before=os.statvfs('/').f_bavail*os.statvfs('/').f_frsize
            for index,entry in enumerate(entries):
                assert_idle()
                # Recheck image/container references and cache usage just before every deletion.
                current=next((e for e in snapshot() if e['key']==entry['key']),None)
                if not current:
                    report.append({'key':entry['key'],'result':'already_absent'});continue
                if not current['eligible'] or current['fingerprint']!=entry['fingerprint']:
                    raise Rejected('资源开始被使用或状态变化，后续清理已停止。')
                publish(message='正在清理 '+str(index+1)+' / '+str(len(entries)),completed=index)
                delete_one(current)
                remaining={e['key'] for e in snapshot()}
                report.append({'key':entry['key'],'result':'removed' if entry['key'] not in remaining else 'retained'})
            after=os.statvfs('/').f_bavail*os.statvfs('/').f_frsize
        retained=any(r['result']=='retained' for r in report)
        publish(status='complete',message='清理已结束。'+('部分资源仍被引擎保留，请查看结果。' if retained else ''),
                report=report,available_delta_bytes=after-before,finished_at=int(time.time()))
    except Exception as error:
        if before is not None:after=os.statvfs('/').f_bavail*os.statvfs('/').f_frsize
        publish(status='failed',message=str(error) if isinstance(error,Rejected) else '清理异常中止，请重新扫描。',report=report,
                available_delta_bytes=after-before if after is not None else None,finished_at=int(time.time()))
    finally:
        # Persistent, credential-free audit. A restart never replays a deletion.
        with LOCK:
            audit={k:v for k,v in CURRENT.items() if k not in ['entries','token']}
        audit['selected_keys']=[e['key'] for e in entries]
        AUDIT.mkdir(mode=0o700,parents=True,exist_ok=True)
        (AUDIT/(token+'.json')).write_text(json.dumps(audit,ensure_ascii=False))


def dispatch(message):
    global OWNER,CURRENT
    owner=message.get('owner','');action=message.get('action')
    if not re.fullmatch('[a-f0-9]{64}',owner):raise Rejected('无效会话')
    with LOCK:
        if action=='status':
            if OWNER not in [None,owner]:return {'status':'busy' if CURRENT['status'] in ['scanning','cleaning'] else 'idle','message':'其他管理会话正在处理' if CURRENT['status'] in ['scanning','cleaning'] else ''}
            return dict(CURRENT)
        if action=='scan':
            if CURRENT['status'] in ['scanning','cleaning']:raise Rejected('资源扫描或清理正在执行，请稍候。')
            OWNER=owner;CURRENT={'status':'scanning','message':'正在扫描镜像和构建缓存…'}
            threading.Thread(target=scan,daemon=True).start();return dict(CURRENT)
        if action!='confirm':raise Rejected('不支持的操作')
        if OWNER!=owner or not secrets.compare_digest(str(message.get('token','')),str(CURRENT.get('token','!'))):raise Rejected('清理预览不属于当前会话，请重新扫描。')
        if CURRENT['status'] in ['cleaning','complete','failed']:return dict(CURRENT)
        if CURRENT['status']!='preview' or time.time()>CURRENT.get('expires_at',0):raise Rejected('清理预览已过期，请重新扫描。')
        selected=message.get('selected')
        if message.get('confirm')!='清理选中资源' or not isinstance(selected,list) or not 1<=len(selected)<=100 or any(not isinstance(x,str) for x in selected) or len(set(selected))!=len(selected):raise Rejected('请选择资源并明确确认清理。')
        allow={e['key']:e for e in CURRENT['entries'] if e['eligible']}
        if any(key not in allow for key in selected):raise Rejected('选项不在本次可清理清单中，请重新扫描。')
        entries=[allow[key] for key in selected];token=CURRENT['token']
        CURRENT.update(status='cleaning',message='正在重新核验资源引用…',selected=selected)
        persist()
        threading.Thread(target=execute,args=(entries,token),daemon=True).start();return dict(CURRENT)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        try:
            _,uid,_=struct.unpack('3i',self.connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if uid not in [0,pwd.getpwnam('song-deploy').pw_uid]:raise Rejected('拒绝访问')
            line=self.rfile.readline(32769)
            if len(line)>32768:raise Rejected('请求过大')
            payload=json.loads(line)
            if not isinstance(payload,dict):raise Rejected('请求格式不正确')
            result=dispatch(payload)
        except (Rejected,ValueError) as error:result={'error':str(error)}
        except Exception:result={'error':'清理服务暂时无法处理请求'}
        self.wfile.write(json.dumps(result,ensure_ascii=False).encode()+b'\n')


def main():
    global OWNER,CURRENT
    RUNTIME.mkdir(mode=0o750,parents=True,exist_ok=True)
    group=pwd.getpwnam('song-deploy').pw_gid
    os.chown(RUNTIME,0,group);(RUNTIME/'maintenance.lock').touch();(RUNTIME/'maintenance.lock').chmod(0o644)
    if (AUDIT/'latest.json').exists():
        previous=json.loads((AUDIT/'latest.json').read_text());OWNER=previous['owner'];CURRENT=previous['state']
        if CURRENT.get('status')=='cleaning':
            CURRENT.update(status='failed',message='服务重启中断了清理，未自动重试。部分选中资源可能已删除，请重新扫描确认。');persist()
    path=RUNTIME/'control.sock';path.unlink(missing_ok=True)
    server=socketserver.ThreadingUnixStreamServer(str(path),Handler)
    path.chmod(0o660);os.chown(path,0,group)
    server.serve_forever()


if __name__=='__main__':main()
