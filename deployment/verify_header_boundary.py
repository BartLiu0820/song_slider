"""Temporary echo endpoint verifies preview credentials are removed by Traefik."""
import json
from pathlib import Path
import secrets
import shlex
import subprocess
import base64
import urllib.request
import verify_agent as api
ssh=['ssh','-S',str(Path.home()/'.ssh/song-deploy-tunnel.sock'),'songhuang-server']
route=Path('/data/coolify/proxy/dynamic/access-header-test.yaml')
probe='/__access_header_test_6abc'
job_id='3e05c69cc9bd17f2f180217d'
host='ai-static-example.localhost'
remote=r'''
import json,sys,subprocess
from pathlib import Path
p=json.load(sys.stdin)
Path('/tmp/song-access-echo.py').write_text(p['code'])
subprocess.run(['systemd-run','--unit=song-access-echo','--property=RuntimeMaxSec=120','--uid=nobody','/usr/bin/python3','/tmp/song-access-echo.py'],check=True)
Path('/data/coolify/proxy/dynamic/access-header-test.yaml').write_text(json.dumps(p['routing']))
'''
code='''from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(b'present' if self.headers.get('Authorization') else b'absent')
 def log_message(self,*args):pass
HTTPServer(('172.21.0.1',19109),Handler).serve_forever()
'''
routing={'http':{'routers':{'access-header-test':{'rule':f'Host(`{host}`) && Path(`{probe}`)','entryPoints':['http'],'priority':10000,'service':'access-header-test'}},'services':{'access-header-test':{'loadBalancer':{'servers':[{'url':'http://172.21.0.1:19109'}]}}}}}
credential=json.loads((Path.home()/'.config/song-deploy/admin-credentials.json').read_text());status,res=api.call('/login',credential);assert status==200;api.csrf=res['csrf']
status,jobs=api.call('/jobs');old=next(j for j in jobs if j['id']==job_id)['access']
name='header-test-'+secrets.token_hex(3);password=secrets.token_urlsafe(24)
try:
 subprocess.run(ssh+['sudo python3 -c '+shlex.quote(remote)],input=json.dumps({'code':code,'routing':routing}),text=True,check=True)
 assert api.call('/accounts',{'username':name,'password':password})[0]==201
 assert api.call('/jobs/'+job_id+'/access',{'mode':'restricted','accounts':[name]})[0]==200
 auth='Basic '+base64.b64encode((name+':'+password).encode()).decode()
 client=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 def get(auth):
  with client.open(urllib.request.Request('http://127.0.0.1:19180'+probe,headers={'Host':host,'Authorization':auth}),timeout=10) as r:return r.read()
 # File-provider throttle is two seconds; retry only while the temporary route is not yet loaded.
 import time
 result=None
 for attempt in range(5):
  try:
   result=get(auth)
   if result in [b'present',b'absent']:break
  except urllib.error.HTTPError:pass
  time.sleep(1)
 assert result==b'absent','Preview password reached upstream'
 assert api.call('/jobs/'+job_id+'/access',{'mode':'public','accounts':[]})[0]==200
 assert get('Bearer application-token')==b'present','Public application auth was stripped'
 print('PASS: private preview credentials stripped; public application authorization preserved')
finally:
 api.call('/jobs/'+job_id+'/access',old);api.call('/accounts/'+name+'/delete',{})
 subprocess.run(ssh+['sudo rm -f /data/coolify/proxy/dynamic/access-header-test.yaml /tmp/song-access-echo.py; sudo systemctl stop song-access-echo'],check=True)
