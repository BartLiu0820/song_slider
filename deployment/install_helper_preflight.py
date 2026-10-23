"""Install automatic helper preparation without changing application plans or credentials."""
import json
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
files={
    **{'admin/'+name:(HERE/'admin'/name).read_text() for name in
       ['helper_manager.py','helper_registry.py','song-deploy-helper.service']},
    **{'agent/'+name:(HERE/'agent'/name).read_text() for name in ['app.py','app.js','helper_client.py']},
    **{'helper-build/'+name:(HERE/name).read_text() for name in
       ['Helper.Dockerfile','git-wrapper','docker-wrapper']},
}
REMOTE=r'''
import datetime,fcntl,json,os,shutil,subprocess,sys,time
from pathlib import Path
files=json.load(sys.stdin)
root=Path('/opt/song-deploy')
sys.path.insert(0,str(root/'admin'))
import cleanup
with cleanup.maintenance():
 cleanup.assert_idle()
 for path in Path('/var/lib/song-deploy/conversations').glob('*.json'):
  if json.loads(path.read_text()).get('chat_request',{}).get('status')=='pending':
   raise RuntimeError('A chat is active; wait before installing')
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 backup=Path('/var/backups/song-deploy')/('helper-preflight-'+stamp)
 backup.mkdir(mode=0o700)
 config_path=Path('/etc/song-deploy/agent.json')
 shutil.copy2(config_path,backup/'agent-config.json')
 unit=Path('/etc/systemd/system/song-deploy-helper.service')
 if unit.exists():shutil.copy2(unit,backup/'helper.service')
 dropin=Path('/etc/systemd/system/song-deploy-agent.service.d/helper.conf')
 if dropin.exists():shutil.copy2(dropin,backup/'helper.conf')
 existed=[]
 for name in files:
  target=root/name
  if target.exists():
   dest=backup/name;dest.parent.mkdir(parents=True,exist_ok=True)
   shutil.copy2(target,dest);existed.append(name)
 try:
  for name,content in files.items():
   target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
   target.parent.chmod(0o755)
   tmp=target.with_suffix(target.suffix+'.new');tmp.write_text(content);tmp.chmod(0o644)
   os.chown(tmp,0,0);tmp.replace(target)
  shutil.copy2(root/'admin/song-deploy-helper.service',unit)
  dropin.parent.mkdir(parents=True,exist_ok=True)
  dropin.write_text('[Unit]\nWants=song-deploy-helper.service\nAfter=song-deploy-helper.service\n')
  subprocess.run(['systemctl','daemon-reload'],check=True)
  subprocess.run(['systemctl','enable','song-deploy-helper'],check=True)
  subprocess.run(['systemctl','restart','song-deploy-helper'],check=True)
  for _ in range(50):
   if Path('/run/song-deploy-helper/control.sock').exists():break
   time.sleep(.1)
  else:raise RuntimeError('Helper preparation socket did not start')
  config=json.loads(config_path.read_text());config['helper_preflight_enabled']=True
  config_path.write_text(json.dumps(config))
  subprocess.run(['systemctl','restart','song-deploy-agent'],check=True)
  subprocess.run(['systemctl','is-active','--quiet','song-deploy-agent','song-deploy-helper'],check=True)
 except Exception:
  shutil.copy2(backup/'agent-config.json',config_path)
  for name in files:
   if name in existed:shutil.copy2(backup/name,root/name)
   else:(root/name).unlink(missing_ok=True)
  if (backup/'helper.service').exists():shutil.copy2(backup/'helper.service',unit)
  else:
   subprocess.run(['systemctl','disable','--now','song-deploy-helper'],check=False)
   unit.unlink(missing_ok=True)
  if (backup/'helper.conf').exists():shutil.copy2(backup/'helper.conf',dropin)
  else:dropin.unlink(missing_ok=True)
  subprocess.run(['systemctl','daemon-reload'],check=True)
  if (backup/'helper.service').exists():subprocess.run(['systemctl','restart','song-deploy-helper'],check=False)
  subprocess.run(['systemctl','restart','song-deploy-agent'],check=True)
  raise
 print(json.dumps({'backup':str(backup),'helper_preflight_enabled':True,'installed_at':stamp}))
'''

if __name__=='__main__':
    subprocess.run(['ssh','-o','BatchMode=yes','songhuang-server','sudo -n python3 -c '+shlex.quote(REMOTE)],
                   input=json.dumps(files),text=True,check=True)
