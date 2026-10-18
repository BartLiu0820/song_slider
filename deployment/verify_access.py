"""Exercise actual proxy enforcement; remove temporary accounts and restore policy."""
import base64
import json
from pathlib import Path
import secrets
import http.client
import urllib.request
import urllib.error
import verify_agent as api

credential=json.loads((Path.home()/'.config/song-deploy/admin-credentials.json').read_text())
code,value=api.call('/login',credential);assert code==200
api.csrf=value['csrf']
code,jobs=api.call('/jobs');assert code==200
job=next(j for j in jobs if j['slug']=='ai-static-example')
old=job['access'];suffix=secrets.token_hex(3)
users=['test-allowed-'+suffix,'test-outside-'+suffix]
passwords={u:secrets.token_urlsafe(24) for u in users}
checks={}
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def preview(path='/',user=None,host=None,extra=None):
 headers={'Host':host or job['slug']+'.localhost','Connection':'close'}
 if user:headers['Authorization']='Basic '+base64.b64encode((user+':'+passwords[user]).encode()).decode()
 headers.update(extra or {})
 try:
  r=opener.open(urllib.request.Request('http://127.0.0.1:19180'+path,headers=headers),timeout=15)
  return r.status,r.read()
 except urllib.error.HTTPError as e:return e.code,e.read()
try:
 for u in users:assert api.call('/accounts',{'username':u,'password':passwords[u]})[0]==201
 checks['policy_requires_csrf']=api.call('/jobs/'+job['id']+'/access',{'mode':'restricted','accounts':users[:1]},False)[0]==403
 assert api.call('/jobs/'+job['id']+'/access',{'mode':'restricted','accounts':users[:1]})[0]==200
 checks['anonymous_blocked']=preview()[0]==401
 checks['asset_blocked']=preview('/images/firefox-icon.png')[0]==401
 checks['unlisted_account_blocked']=preview(user=users[1])[0]==401
 checks['listed_account_allowed']=preview(user=users[0])[0]==200
 checks['public_domain_alias_protected']=preview(host=job['slug']+'.preview.greatsong.online')[0]==401
 checks['forwarded_host_spoof_blocked']=preview(extra={'X-Forwarded-Host':'greatsong.online','X-Forwarded-Proto':'https'})[0]==401
 conn=http.client.HTTPConnection('127.0.0.1',19180,timeout=15)
 conn.request('GET','/',headers={'Host':'greatsong.online'})
 response=conn.getresponse()
 checks['root_showcase_unchanged']=response.status in [200,301,302,307,308] and response.getheader('Location','https://greatsong.online/').startswith('https://greatsong.online')
 response.read();conn.close()
 # Credentials with preview scope must not be usable to log into the admin app.
 checks['viewer_cannot_login_admin']=api.call('/login',{'email':users[0],'password':passwords[users[0]]})[0]==401
 assert api.call('/accounts/'+users[0]+'/delete',{})[0]==200
 checks['revoked_account_blocked']=preview(user=users[0])[0]==401
 checks['delete_last_user_not_public']=preview()[0]==401
 assert api.call('/jobs/'+job['id']+'/access',{'mode':'public','accounts':[]})[0]==200
 checks['switch_to_public']=preview()[0]==200
finally:
 assert api.call('/jobs/'+job['id']+'/access',old)[0]==200
 for u in users:api.call('/accounts/'+u+'/delete',{})
Path('deployment/access-acceptance.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(checks,indent=2))
assert all(checks.values())
