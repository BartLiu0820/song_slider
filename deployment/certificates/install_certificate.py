"""Certbot deploy hook: install trusted certificates atomically for Traefik."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

lineage = Path(os.environ['RENEWED_LINEAGE'])
name = lineage.name
if name not in ['song-ip', 'song-domains']:
    raise SystemExit('Unexpected certificate name')
root = Path('/data/coolify/proxy/certificates')
root.mkdir(mode=0o700, exist_ok=True)
subprocess.run(['openssl','x509','-in',str(lineage/'fullchain.pem'),'-checkend','3600','-noout'],check=True)
serial = subprocess.check_output(['openssl','x509','-in',str(lineage/'fullchain.pem'),'-serial','-noout'],text=True).strip().split('=')[1]
for source, suffix in [('fullchain.pem','crt'),('privkey.pem','key')]:
    target = root / (name+'-'+serial+'.'+suffix)
    shutil.copyfile(lineage/source, target)
    target.chmod(0o600)
manifest = root/'manifest.json'
items = json.loads(manifest.read_text()) if manifest.exists() else {}
items[name] = {'certFile':'/traefik/certificates/'+name+'-'+serial+'.crt',
               'keyFile':'/traefik/certificates/'+name+'-'+serial+'.key'}
manifest.write_text(json.dumps(items,indent=2)+'\n')
tls = {'certificates':list(items.values())}
if 'song-ip' in items:
    tls['stores'] = {'default':{'defaultCertificate':items['song-ip']}}
output = Path('/data/coolify/proxy/dynamic/song-certificates.yaml')
temp = output.with_suffix('.tmp')
temp.write_text(json.dumps({'tls':tls},indent=2)+'\n')
temp.replace(output)
if name == 'song-domains':
    state_path = Path('/var/lib/song-deploy/system/publication.json')
    state = json.loads(state_path.read_text())
    state['dns_certificate'] = True
    temp = state_path.with_suffix('.tmp')
    temp.write_text(json.dumps(state,indent=2)+'\n');temp.chmod(0o644);temp.replace(state_path)
    subprocess.run(['python3','/opt/song-deploy/admin/publication_admin.py','stage-tls'],check=True,stdout=subprocess.DEVNULL)
print('Installed trusted certificate:', name)
