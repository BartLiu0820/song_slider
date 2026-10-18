"""Upgrade the UI and install a mandatory proxy access gate. No secret output."""
import base64
import json
from pathlib import Path
import shlex
import subprocess
from coolify_api import request
HERE=Path(__file__).resolve().parent
files={p.name:p.read_text() for p in (HERE/'agent').iterdir() if p.is_file()}
remote=r'''
import json,sys,subprocess,datetime,shutil
from pathlib import Path
p=json.load(sys.stdin)
backup=Path('/var/backups/song-deploy')/('ui-access-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(mode=0o700,parents=True)
for source,name in [('/opt/song-deploy/agent','agent'),('/var/lib/song-deploy/security','security'),('/data/coolify/proxy/docker-compose.yml','proxy.json')]:
 src=Path(source)
 if src.is_dir():shutil.copytree(src,backup/name)
 elif src.exists():shutil.copy2(src,backup/name)
code=Path('/opt/song-deploy/agent')
for name,content in p['files'].items():(code/name).write_text(content)
Path('/etc/systemd/system/song-deploy-access.service').write_text(p['files']['song-deploy-access.service'])
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','restart','song-deploy-agent'],check=True)
subprocess.run(['systemctl','enable','--now','song-deploy-access'],check=True)
subprocess.run(['systemctl','restart','song-deploy-access'],check=True)
Path('/data/coolify/proxy/dynamic/song-access.yaml').write_text(p['routing'])
Path('/data/coolify/proxy/docker-compose.yml').write_text(p['proxy'])
print('Code installed; rollback backup:',backup)
'''
ssh=['ssh','-S',str(Path.home()/'.ssh/song-deploy-tunnel.sock'),'songhuang-server']
proxy=(HERE/'proxy-public.json').read_text()
subprocess.run(ssh+['sudo -n python3 -c '+shlex.quote(remote)],input=json.dumps({'files':files,'routing':(HERE/'access-routing.json').read_text(),'proxy':proxy}),text=True,check=True)
server=json.loads((HERE/'instance.json').read_text())['server_uuid']
request('PUT','/servers/'+server+'/proxy/configuration',{'configuration':base64.b64encode(proxy.encode()).decode()})
subprocess.run(ssh+['sudo docker compose -f /data/coolify/proxy/docker-compose.yml up -d'],check=True)
print('UI and access gate installed; proxy configuration persisted.')
