"""Switch the public listener with automatic legacy-site rollback on failure."""
import base64
import json
from pathlib import Path
import shlex
import subprocess
from coolify_api import request

HERE = Path(__file__).resolve().parent
server = json.loads((HERE/'instance.json').read_text())['server_uuid']
old = subprocess.check_output(['ssh','-o','BatchMode=yes','songhuang-server',
    'sudo -n cat /data/coolify/proxy/docker-compose.yml'],text=True)
proxy = json.loads(old)
if proxy['services']['traefik']['ports'] != ['127.0.0.1:18080:80','127.0.0.1:18443:443']:
    raise SystemExit('Unexpected proxy ports; refusing to repeat the transition')
new = json.loads(old)
new['services']['traefik']['ports'] = ['80:80','443:443']
newtext = json.dumps(new,indent=2)+'\n'
(HERE/'proxy-public.json').write_text(newtext)
remote = r'''
import json,sys,subprocess,shutil,os,time
from pathlib import Path
p=json.load(sys.stdin)
site=Path('/home/admin/song_slider/output/song-six-stages-v4')
compose=site/'docker-compose.yml'
backup=site/'docker-compose.before-deploy-20261018.yml'
if backup.exists():raise SystemExit('Backup already exists; inspect state before retrying')
shutil.copy2(compose,backup)
proxy=Path('/data/coolify/proxy/docker-compose.yml')
original=proxy.read_text()
Path('/data/coolify/proxy/docker-compose.before-public-20261018.yml').write_text(original)
base=['docker','compose','-f',str(compose)]
pc=['docker','compose','-f',str(proxy)]
newsite={'services':{'web':{'image':'caddy:2-alpine','container_name':'song-slider',
  'restart':'unless-stopped','networks':['coolify'],'volumes':[
  './Caddyfile:/etc/caddy/Caddyfile:ro','./:/srv:ro','caddy_data:/data','caddy_config:/config']}},
  'volumes':{'caddy_data':None,'caddy_config':None},'networks':{'coolify':{'external':True}}}
try:
 compose.write_text(json.dumps(newsite,indent=2)+'\n')
 subprocess.run(base+['config','--quiet'],check=True)
 subprocess.run(base+['up','-d','--pull','never'],check=True)
 proxy.write_text(p['proxy']);os.chown(proxy,9999,0)
 subprocess.run(pc+['up','-d','--pull','never'],check=True)
 # Verify existing TLS certificate and content before accepting the switch.
 for _ in range(15):
  r=subprocess.run(['curl','--fail','--silent','--show-error','--max-time','5',
      '--resolve','greatsong.online:443:127.0.0.1','https://greatsong.online/'],capture_output=True)
  if r.returncode==0 and b'<html' in r.stdout:break
  time.sleep(1)
 else:raise RuntimeError('Existing showcase failed HTTPS smoke test')
 print('Public proxy switched; original showcase HTTPS verified')
except Exception:
 subprocess.run(pc+['stop'],check=False)
 proxy.write_text(original)
 shutil.copy2(backup,compose)
 subprocess.run(base+['up','-d','--pull','never'],check=False)
 subprocess.run(pc+['up','-d','--pull','never'],check=False)
 raise
'''
subprocess.run(['ssh','-o','BatchMode=yes','songhuang-server',
    'sudo -n python3 -c '+shlex.quote(remote)],input=json.dumps({'proxy':newtext}),text=True,check=True)
print(request('PUT','/servers/'+server+'/proxy/configuration',
    {'configuration':base64.b64encode(newtext.encode()).decode()}))
