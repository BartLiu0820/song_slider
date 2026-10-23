"""Install status UI, resource metrics and confirmation-only cleanup with backup.

Does not rotate credentials or redeploy applications. Refuses to interrupt busy jobs.
"""
import json
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
files={}
for folder,names in [('agent',['app.py','app.js','index.html','style.css','boot.js','helper_client.py']),
                     ('admin',['resources.py','song-deploy-resources.service','song-deploy-resources.timer','cleanup.py','song-deploy-cleanup.service'])]:
    for name in names:files[folder+'/'+name]=(HERE/folder/name).read_text()
remote=r'''
import json,sys,subprocess,shutil,datetime
from pathlib import Path
files=json.load(sys.stdin)
root=Path('/opt/song-deploy');state=Path('/var/lib/song-deploy')
for path in state.glob('*.json'):
 job=json.loads(path.read_text())
 if job['status'] in ['queued','analyzing','deploying','repairing','deleting']:
  raise RuntimeError('A job is active; retry installation after it completes')
 conv=state/'conversations'/path.name
 if conv.exists() and json.loads(conv.read_text()).get('chat_request',{}).get('status')=='pending':
  raise RuntimeError('A chat is active; retry installation after it completes')
backup=Path('/var/backups/song-deploy')/('cleanup-chat-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(mode=0o700,parents=True)
for folder in ['agent','admin']:shutil.copytree(root/folder,backup/folder,dirs_exist_ok=True)
for path in state.glob('*.json'):shutil.copy2(path,backup/path.name)
shutil.copytree(state/'conversations',backup/'conversations',dirs_exist_ok=True)
for name,text in files.items():
 target=root/name;temp=target.with_suffix(target.suffix+'.new');temp.write_text(text);temp.chmod(0o644);temp.replace(target)
for unit in ['song-deploy-resources.service','song-deploy-resources.timer','song-deploy-cleanup.service']:
 shutil.copy2(root/'admin'/unit,Path('/etc/systemd/system')/unit)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','start','song-deploy-resources.service'],check=True)
metrics=json.loads(Path('/run/song-deploy-metrics/resources.json').read_text())
if metrics['errors']:raise RuntimeError('Resource collection incomplete: '+str(metrics['errors']))
subprocess.run(['systemctl','enable','--now','song-deploy-resources.timer'],check=True)
subprocess.run(['systemctl','enable','--now','song-deploy-cleanup.service'],check=True)
subprocess.run(['systemctl','restart','song-deploy-cleanup.service'],check=True)
import time
for _ in range(50):
 if Path('/run/song-deploy-cleanup/control.sock').exists():break
 time.sleep(.1)
else:raise RuntimeError('Cleanup socket did not start')
config_path=Path('/etc/song-deploy/agent.json')
shutil.copy2(config_path,backup/'agent-config.json')
config=json.loads(config_path.read_text());config['cleanup_enabled']=True
config_path.write_text(json.dumps(config))
# Recheck before restarting, since the resource scan takes several seconds.
for path in state.glob('*.json'):
 if json.loads(path.read_text())['status'] in ['queued','analyzing','deploying','repairing','deleting']:
  raise RuntimeError('A job started during installation; wait before restarting the agent')
subprocess.run(['systemctl','restart','song-deploy-agent'],check=True)
print(json.dumps({'backup':str(backup),'disk':metrics['disk'],'projects':len(metrics['projects']),'containers':len(metrics['containers'])}))
'''
subprocess.run(['ssh','-o','BatchMode=yes','songhuang-server','sudo -n python3 -c '+shlex.quote(remote)],input=json.dumps(files),text=True,check=True)
