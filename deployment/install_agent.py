"""Install the loopback-only assistant; transfer secrets over SSH stdin."""
import hashlib
import json
from pathlib import Path
import secrets
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
private=Path.home()/'.config/song-deploy'
credentials=json.loads((private/'admin-credentials.json').read_text())
salt=secrets.token_bytes(16)
config={'email':credentials['email'],'password_salt':salt.hex(),
    'password_hash':hashlib.pbkdf2_hmac('sha256',credentials['password'].encode(),salt,600000).hex(),
    'session_secret':secrets.token_urlsafe(48),'model':'deepseek-flash',
    'coolify_token':(private/'coolify-api-token').read_text().strip(),
    'project_uuid':json.loads((HERE/'agent-project.json').read_text())['uuid'],
    'server_uuid':json.loads((HERE/'instance.json').read_text())['server_uuid']}
files={p.name:p.read_text() for p in (HERE/'agent').iterdir() if p.is_file()}
remote=r'''
import json,sys,subprocess,pwd,os
from pathlib import Path
p=json.load(sys.stdin)
try: user=pwd.getpwnam('song-deploy')
except KeyError:
 subprocess.run(['useradd','--system','--home','/var/lib/song-deploy','--shell','/usr/sbin/nologin','song-deploy'],check=True)
 user=pwd.getpwnam('song-deploy')
root=Path('/opt/song-deploy');code=root/'agent';code.mkdir(parents=True,exist_ok=True)
state=Path('/var/lib/song-deploy');state.mkdir(exist_ok=True);os.chown(state,user.pw_uid,user.pw_gid);state.chmod(0o700)
repos=state/'repos';repos.mkdir(exist_ok=True);os.chown(repos,user.pw_uid,user.pw_gid);repos.chmod(0o700)
for name,content in p['files'].items():
 if '/' in name:raise ValueError('Invalid file name')
 (code/name).write_text(content)
cfg=Path('/etc/song-deploy');cfg.mkdir(exist_ok=True);os.chown(cfg,0,user.pw_gid);cfg.chmod(0o750)
f=cfg/'agent.json'
if f.exists():
 old=json.loads(f.read_text());p['config']['session_secret']=old['session_secret']
f.write_text(json.dumps(p['config']));os.chown(f,0,user.pw_gid);f.chmod(0o640)
key=cfg/'deepseek-key';os.chown(key,0,user.pw_gid);key.chmod(0o640)
if not (root/'venv/bin/pip').exists():subprocess.run(['python3','-m','venv',str(root/'venv')],check=True)
subprocess.run([str(root/'venv/bin/pip'),'install','--disable-pip-version-check','-r',str(code/'requirements.txt')],check=True)
Path('/etc/systemd/system/song-deploy-agent.service').write_text((code/'song-deploy-agent.service').read_text())
Path('/etc/systemd/system/song-deploy-git.service').write_text((code/'song-deploy-git.service').read_text())
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now','song-deploy-git'],check=True)
subprocess.run(['systemctl','restart','song-deploy-git'],check=True)
subprocess.run(['systemctl','enable','--now','song-deploy-agent'],check=True)
subprocess.run(['systemctl','restart','song-deploy-agent'],check=True)
print('Agent installed on 127.0.0.1:9100; secrets not printed')
'''
subprocess.run(['ssh','-o','BatchMode=yes','songhuang-server','sudo -n python3 -c '+shlex.quote(remote)],
               input=json.dumps({'files':files,'config':config}),text=True,check=True)
