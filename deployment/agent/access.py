"""Account allowlists, enforced by the proxy before any application request."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from flask import Flask, request
import publication

ROOT = Path(os.environ.get('SONG_STATE', '/var/lib/song-deploy'))
DIRECTORY = ROOT / 'security'
LOCK = threading.RLock()
auth_app = Flask('preview_access')
failures = {}
verified = {}


def read_security():
    path = DIRECTORY / 'access.json'
    return json.loads(path.read_text()) if path.exists() else {'accounts': {}, 'policies': {}}


def write_security(data):
    DIRECTORY.mkdir(mode=0o700, exist_ok=True)
    path = DIRECTORY / 'access.json'
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    temp.chmod(0o600)
    temp.replace(path)


def policy(job_id):
    return read_security()['policies'].get(job_id, {'mode': 'public', 'accounts': []})


def set_policy(job_id, value):
    if not isinstance(value, dict) or value.get('mode') not in ['public', 'restricted']:
        raise ValueError('请选择公开或指定账号访问')
    accounts = value.get('accounts', [])
    if not isinstance(accounts, list) or any(not isinstance(a, str) for a in accounts):
        raise ValueError('账号列表不合法')
    with LOCK:
        data = read_security()
        if any(a not in data['accounts'] for a in accounts):
            raise ValueError('请先创建访问账号')
        if value['mode'] == 'restricted' and not accounts:
            raise ValueError('请至少指定一个访问账号')
        result = {'mode': value['mode'], 'accounts': sorted(set(accounts)) if value['mode'] == 'restricted' else []}
        data['policies'][job_id] = result
        write_security(data)
    return result


def create_account(username, password):
    if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9@._-]{2,79}', username):
        raise ValueError('账号需为 3–80 位字母、数字或 @ . _ -')
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError('密码长度需为 12–128 位')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    with LOCK:
        data = read_security()
        if username in data['accounts']:
            raise ValueError('账号已存在')
        data['accounts'][username] = {'salt': salt, 'hash': digest}
        write_security(data)
    return username


def delete_account(username):
    with LOCK:
        data = read_security()
        if username not in data['accounts']: raise ValueError('账号不存在')
        del data['accounts'][username]
        # An emptied restricted policy stays restricted: deleting the last user never makes it public.
        for value in data['policies'].values():
            value['accounts'] = [a for a in value['accounts'] if a != username]
        write_security(data)


@auth_app.get('/check')
def check():
    host = request.headers.get('X-Forwarded-Host', '').lower().split(':')[0].rstrip('.')
    original_auth = request.headers.get('Authorization', '')
    uri=request.headers.get('X-Forwarded-Uri','/').split('?')[0]
    peer=request.headers.get('X-Forwarded-For','').split(',')[0].strip()
    if request.headers.get('X-Forwarded-Proto') == 'http' and publication.acme_request(host, uri):
        return '',200,{'Authorization':''}
    if host == publication.TEMP_IP:
        if not publication.ip_enabled():return 'Temporary IP access is not enabled yet.',503
        if request.headers.get('X-Forwarded-Proto') != 'https':
            # Do not preserve a caller-supplied host or port in the redirect.
            return '',308,{'Location':'https://'+publication.TEMP_IP+'/', 'Cache-Control':'no-store'}
        return '',200,{'Authorization':'', 'Cache-Control':'no-store'}
    if host.endswith('.localhost') and peer not in ['127.0.0.1','::1','172.21.0.1']:
        return 'Local preview requires an SSH tunnel',403
    if host == publication.PUBLIC_HOST or host.endswith(publication.PREVIEW_SUFFIX):
        if uri == publication.READY_PATH:return '',200,{'Authorization':''}
        if not publication.enabled():return 'Public publishing is not enabled yet.',503
        if request.headers.get('X-Forwarded-Proto') != 'https':
            # Redirect before requesting credentials; never challenge over public HTTP.
            return '',308,{'Location':'https://'+host+(request.headers.get('X-Forwarded-Uri','/') if request.headers.get('X-Forwarded-Uri','/').startswith('/') else '/'), 'Cache-Control':'no-store'}

    def allow(public=False):
        # ForwardAuth replaces the original Authorization header. Preserve app tokens
        # on public routes, but never send a private preview password to the app.
        return '', 200, {'Authorization': original_auth if public else '', 'Cache-Control': 'no-store'}
    if host in ['greatsong.online', 'www.greatsong.online', 'deploy.greatsong.online']:
        return allow(True)
    job = None
    for path in ROOT.glob('*.json'):
        item = json.loads(path.read_text())
        if host in [item.get('slug', '') + '.localhost', item.get('slug', '') + '.preview.greatsong.online']:
            job = item
            break
    if not job: return 'Unknown deployment', 403
    if job.get('status') in ['deleting','delete_failed']:return 'Deployment removed or pending removal',403
    data = read_security()
    access = data['policies'].get(job['id'], {'mode': 'public', 'accounts': []})
    if access['mode'] == 'public': return allow(True)
    denied = ('This deployment requires an authorized account.', 401,
              {'WWW-Authenticate': 'Basic realm="Deployment preview", charset="UTF-8"', 'Cache-Control': 'no-store'})
    if not original_auth.startswith('Basic '): return denied
    try:
        username, password = base64.b64decode(original_auth[6:], validate=True).decode().split(':', 1)
    except (ValueError, UnicodeError): return denied
    now = time.time()
    # Proxy-supplied client IP only; spoofed client forwarding headers are discarded by Traefik.
    address = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
    with LOCK:
        recent = [t for t in failures.get(address, []) if now - t < 300]
        if len(recent) >= 12: return 'Too many attempts. Retry in five minutes.', 429
    account = data['accounts'].get(username)
    valid = False
    if account and username in access['accounts'] and len(password) <= 128:
        cache_key = hashlib.sha256((original_auth + account['hash']).encode()).hexdigest()
        valid = verified.get(cache_key, 0) > now
        if not valid:
            digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(account['salt']), 600000).hex()
            valid = hmac.compare_digest(digest, account['hash'])
            if valid:
                with LOCK:
                    if len(verified) > 1000: verified.clear()
                    verified[cache_key] = now + 60
    if not valid:
        with LOCK:
            if len(failures) > 2000: failures.clear()
            failures[address] = recent + [now]
        return denied
    return allow()
