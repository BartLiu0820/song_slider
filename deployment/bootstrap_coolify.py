"""One-time installation preparation. Does not execute upstream installer.

Secrets live outside the Git workspace. Existing installations are never overwritten.
The managed proxy starts on loopback ports, preserving the existing public Caddy.
"""
import json
from pathlib import Path
import secrets
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
PRIVATE = Path.home() / '.config/song-deploy'
PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
PRIVATE.chmod(0o700)
credentials_path = PRIVATE / 'admin-credentials.json'
if not credentials_path.exists():
    credentials_path.write_text(json.dumps({
        'url': 'https://deploy.greatsong.online',
        'name': 'Song Deploy Admin',
        'email': 'admin@greatsong.online',
        'password': 'Aa9!' + secrets.token_urlsafe(28),
    }, indent=2))
credentials_path.chmod(0o600)
credentials = json.loads(credentials_path.read_text())

proxy = {
    'networks': {'coolify': {'external': True}},
    'services': {'traefik': {
        'image': 'public.ecr.aws/docker/library/traefik:v3.7',
        'container_name': 'coolify-proxy', 'restart': 'unless-stopped',
        'networks': ['coolify'],
        'ports': ['127.0.0.1:18080:80', '127.0.0.1:18443:443'],
        'extra_hosts': ['host.docker.internal:host-gateway'],
        'volumes': ['/var/run/docker.sock:/var/run/docker.sock:ro', '/data/coolify/proxy:/traefik'],
        'command': ['--ping=true', '--ping.entrypoint=traefik', '--entrypoints.traefik.address=:8080',
                    '--entrypoints.http.address=:80', '--entrypoints.https.address=:443',
                    '--providers.docker=true', '--providers.docker.exposedbydefault=false',
                    '--providers.docker.network=coolify', '--providers.file.directory=/traefik/dynamic',
                    '--providers.file.watch=true', '--api.dashboard=false',
                    '--certificatesresolvers.letsencrypt.acme.httpchallenge=true',
                    '--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=http',
                    '--certificatesresolvers.letsencrypt.acme.storage=/traefik/acme.json'],
        'healthcheck': {'test': ['CMD', 'traefik', 'healthcheck', '--ping'],
                        'interval': '10s', 'timeout': '3s', 'retries': 5},
        'labels': {'coolify.managed': 'true', 'coolify.proxy': 'true'},
        'mem_limit': '512m', 'cpus': 0.5,
    }},
}
payload = {'credentials': credentials, 'proxy': proxy, 'files': {
    'docker-compose.yml': (HERE/'vendor/docker-compose.yml').read_text(),
    'docker-compose.prod.yml': (HERE/'vendor/docker-compose.prod.yml').read_text(),
    'docker-compose.custom.yml': (HERE/'docker-compose.custom.yml').read_text(),
}}

remote = r'''
import base64,json,os,secrets,subprocess,sys
from pathlib import Path
p=json.load(sys.stdin)
root=Path('/data/coolify')
if (root/'source/.env').exists():
    raise SystemExit('Existing installation detected; no files or secrets overwritten')
for sub in ['', 'source','ssh','ssh/keys','ssh/mux','applications','databases','services',
            'backups','images','proxy','proxy/dynamic','sentinel']:
    d=root/sub
    d.mkdir(parents=True,exist_ok=True)
    os.chown(d,9999,0)
    d.chmod(0o700)
for name,content in p['files'].items():
    f=root/'source'/name
    f.write_text(content)
    os.chown(f,9999,0)
    f.chmod(0o600)
cred=p['credentials']
env={
    'APP_ID':secrets.token_hex(16),'APP_NAME':'Song Deploy','APP_ENV':'production',
    'APP_KEY':'base64:'+base64.b64encode(secrets.token_bytes(32)).decode(),
    'APP_URL':'http://localhost:8000','DB_USERNAME':'coolify','DB_DATABASE':'coolify',
    'DB_PASSWORD':secrets.token_urlsafe(32),'REDIS_PASSWORD':secrets.token_urlsafe(32),
    'PUSHER_APP_ID':secrets.token_hex(32),'PUSHER_APP_KEY':secrets.token_hex(32),
    'PUSHER_APP_SECRET':secrets.token_hex(32),'PUSHER_BACKEND_PORT':'6001',
    'ROOT_USERNAME':cred['name'],'ROOT_USER_EMAIL':cred['email'],'ROOT_USER_PASSWORD':cred['password'],
    'REGISTRY_URL':'ghcr.io','LATEST_IMAGE':'4.4.7','AUTOUPDATE':'false',
    'PHP_FPM_PM_MAX_CHILDREN':'5','PHP_FPM_PM_MAX_SPARE_SERVERS':'2',
}
f=root/'source/.env'
f.write_text(chr(10).join(k+'="'+v+'"' for k,v in env.items())+chr(10))
os.chown(f,9999,0);f.chmod(0o600)
key=root/'ssh/keys/id.root@host.docker.internal'
subprocess.run(['ssh-keygen','-t','ed25519','-f',str(key),'-N','','-C','coolify-song-deploy'],check=True,capture_output=True)
auth=Path('/root/.ssh/authorized_keys')
auth.parent.mkdir(exist_ok=True,mode=0o700)
old=auth.read_text() if auth.exists() else ''
pub=Path(str(key)+'.pub')
with auth.open('a') as out:
    if old and not old.endswith(chr(10)):out.write(chr(10))
    out.write('from="172.16.0.0/12,127.0.0.1,::1" '+pub.read_text())
auth.chmod(0o600);pub.unlink()
os.chown(key,9999,0);key.chmod(0o600)
f=root/'proxy/docker-compose.yml'
f.write_text(json.dumps(p['proxy'],indent=2));os.chown(f,9999,0);f.chmod(0o600)
network=subprocess.run(['docker','network','inspect','coolify'],capture_output=True)
if network.returncode:
    subprocess.run(['docker','network','create','--attachable','coolify'],check=True,capture_output=True)
print('Prepared Coolify 4.4.7. Ports are loopback-only. Credentials not printed.')
'''
result = subprocess.run(['ssh', '-o', 'BatchMode=yes', 'songhuang-server',
    'sudo -n python3 -c ' + shlex.quote(remote)], input=json.dumps(payload),
    text=True, capture_output=True, timeout=45)
print(result.stdout)
if result.returncode:
    print(result.stderr)
    raise SystemExit(result.returncode)
print('Local credentials:', credentials_path)
