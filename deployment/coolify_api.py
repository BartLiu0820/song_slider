"""Call the private Coolify API through SSH; credentials never enter shell arguments."""
import json
from pathlib import Path
import shlex
import subprocess
import sys

PRIVATE = Path.home() / '.config/song-deploy'
REMOTE = r'''
import json,sys,urllib.request,urllib.error
p=json.load(sys.stdin)
req=urllib.request.Request('http://127.0.0.1:8000/api/v1'+p['path'],
    data=json.dumps(p['body']).encode() if p.get('body') is not None else None,
    method=p['method'],headers={'Authorization':'Bearer '+p['token'],
    'Content-Type':'application/json','Accept':'application/json'})
try:
    r=urllib.request.urlopen(req,timeout=55)
    print(json.dumps({'status':r.status,'body':r.read().decode()}))
except urllib.error.HTTPError as e:
    print(json.dumps({'status':e.code,'body':e.read().decode()}))
'''


def request(method, path, body=None):
    if not path.startswith('/') or '://' in path:
        raise ValueError('Expected an API-relative path')
    token = (PRIVATE/'coolify-api-token').read_text().strip()
    ssh=['ssh','-o','BatchMode=yes']
    control=Path.home()/'.ssh/song-deploy-tunnel.sock'
    if control.exists():ssh+=['-S',str(control)]
    result = subprocess.run(ssh+['songhuang-server',
        'python3 -c '+shlex.quote(REMOTE)], input=json.dumps({
            'method':method,'path':path,'body':body,'token':token}),
        capture_output=True,text=True,timeout=65,check=True)
    envelope=json.loads(result.stdout)
    try: data=json.loads(envelope['body'])
    except json.JSONDecodeError: data=envelope['body']
    if envelope['status'] >= 400:
        raise RuntimeError(f"API {envelope['status']}: {data}")
    return data


if __name__ == '__main__':
    body=json.loads(Path(sys.argv[3]).read_text()) if len(sys.argv)>3 else None
    print(json.dumps(request(sys.argv[1],sys.argv[2],body),ensure_ascii=False,indent=2))
