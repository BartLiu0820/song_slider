"""Run as root on the server. Add the verified mirror without restarting Docker."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

mirror='https://docker.m.daocloud.io'
path=Path('/etc/docker/daemon.json')
original=path.read_text() if path.exists() else '{}\n'
data=json.loads(original)
mirrors=data.get('registry-mirrors',[])
data['registry-mirrors']=[mirror]+[value for value in mirrors if value!=mirror]
backup=path.with_name('daemon.song-deploy-backup-20261018.json')
if not backup.exists():
    backup.write_text(original)
    backup.chmod(0o600)
candidate=path.with_name('daemon.song-deploy-candidate.json')
candidate.write_text(json.dumps(data,indent=2)+'\n')
candidate.chmod(0o600)
subprocess.run(['dockerd','--validate','--config-file',str(candidate)],check=True)
candidate.replace(path)
pid=int(subprocess.check_output(['systemctl','show','-p','MainPID','--value','docker.service'],text=True).strip())
if pid<=1:
    raise RuntimeError('Cannot identify Docker daemon')
os.kill(pid,signal.SIGHUP)
for _ in range(10):
    out=subprocess.check_output(['docker','info','--format','{{json .RegistryConfig.Mirrors}}'],text=True)
    if mirror+'/' in json.loads(out) or mirror in json.loads(out):
        print('Mirror enabled by daemon reload; existing containers were not restarted.')
        break
    time.sleep(1)
else:
    raise RuntimeError('Mirror reload was not confirmed')
