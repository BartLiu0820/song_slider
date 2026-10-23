"""Apply the platform static cache defaults to an existing app, retaining a backup.

Usage: python3 deployment/apply_preview_cache.py APPLICATION_UUID
Custom configurations are never overwritten. Coolify retains the configuration for
future builds; the current container is validated and gracefully reloaded now.
"""
import base64
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
from coolify_api import request

application=sys.argv[1]
if not re.fullmatch('[a-z0-9]{20,40}',application):raise SystemExit('Invalid application UUID')
configuration=(Path(__file__).parent/'agent/static-nginx.conf').read_text()
current=request('GET','/applications/'+application)
old=current.get('custom_nginx_configuration')
if old and old!=configuration:raise SystemExit('Existing custom nginx configuration requires review; unchanged')
request('PATCH','/applications/'+application,{'custom_nginx_configuration':base64.b64encode(configuration.encode()).decode()})
remote=r'''
import json,sys,subprocess,time
from pathlib import Path
p=json.load(sys.stdin)
names=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines()
names=[name for name in names if name.startswith(p['application']+'-')]
if len(names)!=1:raise RuntimeError('Expected one running application container')
container=names[0];destination='/etc/nginx/conf.d/default.conf'
backup=Path('/var/backups/song-deploy')/('preview-cache-'+time.strftime('%Y%m%d-%H%M%S'))
backup.mkdir(mode=0o700,parents=True)
old=subprocess.check_output(['docker','exec',container,'cat',destination])
(backup/'nginx.conf.before').write_bytes(old)
(backup/'application-custom-nginx.json').write_text(json.dumps(p['old']))
next_config=backup/'nginx.conf.next';next_config.write_text(p['configuration'])
try:
 subprocess.run(['docker','cp',str(next_config),container+':'+destination],check=True)
 subprocess.run(['docker','exec',container,'nginx','-t'],check=True)
 subprocess.run(['docker','exec',container,'nginx','-s','reload'],check=True)
except Exception:
 subprocess.run(['docker','cp',str(backup/'nginx.conf.before'),container+':'+destination],check=True)
 subprocess.run(['docker','exec',container,'nginx','-s','reload'],check=True)
 raise
print('Applied and backed up at '+str(backup))
'''
try:
 subprocess.run(['ssh','-o','BatchMode=yes','songhuang-server','sudo -n python3 -c '+shlex.quote(remote)],input=json.dumps({'application':application,'configuration':configuration,'old':old}),text=True,check=True)
except Exception:
 request('PATCH','/applications/'+application,{'custom_nginx_configuration':base64.b64encode(old.encode()).decode() if old else None})
 raise
