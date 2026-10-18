"""Read-only acceptance checks against the live SSH-accessible deployment."""
import json
from pathlib import Path
import urllib.request
import verify_agent as client
from coolify_api import request as engine

credentials=json.loads((Path.home()/'.config/song-deploy/admin-credentials.json').read_text())
status,data=client.call('/login',{'email':credentials['email'],'password':credentials['password']})
assert status==200
client.csrf=data['csrf']
status,jobs=client.call('/jobs');assert status==200
checks={'assistant_login':True}
http=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def get(slug,path='/'):
    req=urllib.request.Request('http://127.0.0.1:19180'+path,headers={'Host':slug+'.localhost'})
    with http.open(req,timeout=10) as r:return r.status,r.read()

assert get('ai-flask-example')==(200,b'Hello World!')
checks['backend_http_200']=True
status,body=get('ai-static-example');assert status==200 and b'Mozilla is cool' in body
checks['static_http_200']=True
assert get('ai-static-example','/styles/style.css')[0]==200
assert get('ai-static-example','/images/firefox-icon.png')[1].startswith(b'\x89PNG')
checks['static_css_and_image']=True
database=next(j for j in jobs if j['slug']=='ai-flaskr-database')
assert database['status']=='needs_configuration'
assert client.call('/jobs/'+database['id']+'/deploy',{})[0]==400
checks['database_configuration_gate']=True
deployed=[j for j in jobs if j['status']=='deployed']
assert len(deployed)==2
deployments=[]
for job in deployed:
    d=engine('GET','/deployments/'+job['deployment_uuid'])
    assert d['status']=='finished'
    a=engine('GET','/applications/'+job['application_uuid'])
    assert a['status']=='running:healthy',a['status']
    deployments.append({k:d[k] for k in ['deployment_uuid','status','created_at','updated_at',
        'deployment_started_at','deployment_finished_at'] if k in d})
checks['both_engine_deployments_finished_and_healthy']=True
result={'checks':checks,'jobs':jobs,'deployments':deployments}
Path('deployment/acceptance-20261018.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(checks))
