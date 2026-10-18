"""Exercise live login, CSRF/URL guards, and one real DeepSeek analysis."""
import http.cookiejar
import json
from pathlib import Path
import urllib.request
import urllib.error

BASE='http://127.0.0.1:19100'
jar=http.cookiejar.CookieJar()
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.ProxyHandler({}))
csrf=''

def call(path,body=None,token=True):
    req=urllib.request.Request(BASE+'/api'+path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json','X-CSRF-Token':csrf if token else ''})
    try:
        with client.open(req,timeout=20) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:return e.code,json.load(e)

if __name__=='__main__':
    checks={}
    checks['unauthenticated_blocked']=call('/jobs')[0]==401
    cred=json.loads((Path.home()/'.config/song-deploy/admin-credentials.json').read_text())
    status,data=call('/login',{'email':cred['email'],'password':cred['password']})
    assert status==200;csrf=data['csrf'];checks['login']=True
    checks['csrf_blocked']=call('/analyze',{},False)[0]==403
    checks['internal_url_blocked']=call('/analyze',{'repository':'http://127.0.0.1/','slug':'bad-url'})[0]==400
    status,data=call('/analyze',{'repository':'https://github.com/docker/awesome-compose',
        'branch':'master','directory':'/flask/app','slug':'ai-flask-example'})
    assert status==202,(status,data)
    checks['real_analysis_job']=data['id']
    Path('deployment/agent-checks.json').write_text(json.dumps(checks,indent=2))
    print(json.dumps(checks))
