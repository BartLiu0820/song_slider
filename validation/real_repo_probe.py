"""Validate two upstream repositories already cloned under deploy-validation.

Run with SSH stdin. Upstream source is copied unchanged; deployment adapters
are kept separately. Only loopback HTTP is published. Fixtures are removed.
"""
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
import urllib.parse
import urllib.request

RUN = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
ROOT = Path.home() / 'deploy-validation' / ('real-' + RUN)
ROOT.mkdir(parents=True, exist_ok=False)
ROOT.chmod(0o700)
REPOS = Path.home() / 'deploy-validation/real-repositories'
PROJECT = 'songreal-' + RUN
DOCKER = ['sudo', '-n', 'docker']
RESULT = {'run': RUN, 'directory': str(ROOT), 'checks': [], 'repositories': {}, 'timings': {}}
START = time.monotonic()


def run(args, timeout=90, check=True):
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    with (ROOT / 'commands.log').open('a') as f:
        f.write('\n$ ' + ' '.join(args) + '\n' + p.stdout + p.stderr)
    if check and p.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(args[:7]) + '\n' + p.stderr[-1800:])
    return p


def compose(*args, timeout=120, check=True):
    return run(DOCKER + ['compose', '-p', PROJECT, '-f', str(ROOT / 'compose.json'), *args], timeout, check)


def mark(name, detail):
    value = {'name': name, 'passed': True, 'detail': detail}
    RESULT['checks'].append(value)
    print(json.dumps(value, ensure_ascii=False), flush=True)


opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(host, path='/', form=None):
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request('http://127.0.0.1:18080' + path, data=data, headers={'Host': host})
    with opener.open(req, timeout=5) as response:
        return response.status, response.read().decode(), response.url


def wait_http(host):
    last = None
    for _ in range(30):
        try:
            return request(host)
        except OSError as exc:
            last = str(exc)
            time.sleep(1)
    raise RuntimeError('Health timeout: ' + str(last))


try:
    live = run(['curl', '-fsS', '--max-time', '15', 'https://greatsong.online']).stdout
    RESULT['live_before_sha256'] = hashlib.sha256(live.encode()).hexdigest()
    for name, sub in [('awesome-compose', 'flask/app'), ('flask', 'examples/tutorial')]:
        source = REPOS / name
        RESULT['repositories'][name] = {
            'commit': run(['git', '-C', str(source), 'rev-parse', 'HEAD']).stdout.strip(),
            'subdirectory': sub,
            'source_modified': bool(run(['git', '-C', str(source), 'status', '--porcelain']).stdout.strip())}
        shutil.copytree(source / sub, ROOT / name)

    (ROOT / 'awesome-compose/Dockerfile.proof').write_text('''FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt flask==3.1.2 gunicorn==23.0.0
COPY app.py ./
USER 10001:10001
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--worker-tmp-dir", "/tmp", "app:app"]
''')
    (ROOT / 'flask/wsgi_proof.py').write_text('''from pathlib import Path
from flaskr import create_app
app = create_app({
    'SECRET_KEY': Path('/run/secrets/session_secret').read_text().strip(),
    'DATABASE': '/data/flaskr.sqlite',
})
''')
    (ROOT / 'flask/Dockerfile.proof').write_text('''FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
COPY . /app/
RUN pip install --no-cache-dir . flask==3.1.2 gunicorn==23.0.0 && mkdir -p /app/instance /usr/local/var/flaskr-instance /data && chown -R 10001:10001 /app/instance /usr/local/var/flaskr-instance /data
USER 10001:10001
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--worker-tmp-dir", "/tmp", "wsgi_proof:app"]
''')
    for name in ['awesome-compose', 'flask']:
        started = time.monotonic()
        run(DOCKER + ['build', '--pull=false', '-f', str(ROOT/name/'Dockerfile.proof'),
                     '-t', PROJECT + '-' + name, str(ROOT/name)], timeout=300)
        RESULT['timings'][name + '_build_seconds'] = round(time.monotonic() - started, 2)
        mark('build_' + name, {'seconds': RESULT['timings'][name + '_build_seconds']})

    (ROOT / 'session-secret').write_text(secrets.token_urlsafe(32))
    (ROOT / 'session-secret').chmod(0o644)
    (ROOT / 'Caddyfile').write_text('''{
    auto_https off
    admin off
}
http://backend-real.proof.local {
    reverse_proxy backend:8000
}
http://database-real.proof.local {
    reverse_proxy databaseapp:8000
}
''')
    app_limits = {'mem_limit': '128m', 'cpus': 0.5, 'pids_limit': 64,
                  'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
                  'read_only': True, 'tmpfs': ['/tmp:size=16m']}
    services = {
        'router': {'image': 'caddy:2-alpine', 'ports': ['127.0.0.1:18080:80'],
                   'networks': ['default', 'ingress'], 'mem_limit': '64m',
                   'volumes': [str(ROOT/'Caddyfile') + ':/etc/caddy/Caddyfile:ro']},
        'backend': dict(app_limits, image=PROJECT+'-awesome-compose'),
        'databaseapp': dict(app_limits, image=PROJECT+'-flask',
                            volumes=['database:/data'], secrets=['session_secret'])}
    (ROOT/'compose.json').write_text(json.dumps({'services': services,
        'secrets': {'session_secret': {'file': './session-secret'}},
        'volumes': {'database': {}}, 'networks': {'default': {'internal': True}, 'ingress': {}}}, indent=2))
    # The tutorial init-db drops existing tables: run it ONCE on a new empty fixture volume.
    init = 'from wsgi_proof import app\nfrom flaskr.db import init_db\nwith app.app_context(): init_db()'
    compose('run', '--rm', '--no-deps', 'databaseapp', 'python', '-c', init)
    compose('up', '-d', '--pull', 'never')
    status, body, _ = wait_http('backend-real.proof.local')
    assert status == 200 and body == 'Hello World!'
    mark('upstream_backend_http', {'http': status, 'response': body})
    status, body, _ = wait_http('database-real.proof.local')
    assert status == 200 and 'Flaskr' in body
    mark('upstream_database_home', {'http': status})

    username = 'deployment-proof'
    password = secrets.token_urlsafe(18)
    status, body, url = request('database-real.proof.local', '/auth/register',
                                 {'username': username, 'password': password})
    assert status == 200 and '/auth/login' in url
    status, body, url = request('database-real.proof.local', '/auth/login',
                                 {'username': username, 'password': password})
    assert status == 200 and username in body
    title = 'Deployment proof ' + RUN
    status, body, _ = request('database-real.proof.local', '/create',
                               {'title': title, 'body': 'Persistence check from a real Git application.'})
    assert status == 200 and title in body
    mark('upstream_register_login_create', {'registered': True, 'logged_in': True, 'post_visible': True})

    compose('up', '-d', '--no-deps', '--force-recreate', 'databaseapp')
    status, body, _ = wait_http('database-real.proof.local')
    assert title in body and username in body
    mark('upstream_sqlite_persistence', {'post_survived_recreation': True, 'login_session_preserved': True})
    RESULT['resource_snapshot'] = run(DOCKER + ['stats', '--no-stream', '--format', '{{json .}}',
                                              *compose('ps', '-q').stdout.split()]).stdout
    RESULT['dependencies'] = compose('exec', '-T', 'databaseapp', 'pip', 'freeze').stdout
    RESULT['host_memory'] = run(['free', '-m']).stdout
    after = run(['curl', '-fsS', '--max-time', '15', 'https://greatsong.online']).stdout
    assert hashlib.sha256(after.encode()).hexdigest() == RESULT['live_before_sha256']
    mark('existing_site_unchanged', {'http': 200, 'html_sha256_unchanged': True})
    RESULT['status'] = 'passed'
except Exception as exc:
    RESULT['status'] = 'failed'
    RESULT['error'] = str(exc)
    print('VALIDATION ERROR:', str(exc), flush=True)
finally:
    if (ROOT/'compose.json').exists():
        compose('logs', '--no-color', '--tail', '30', check=False)
        RESULT['cleanup_exit'] = compose('down', '--volumes', '--remove-orphans', check=False).returncode
    (ROOT/'session-secret').unlink(missing_ok=True)
    RESULT['duration_seconds'] = round(time.monotonic() - START, 2)
    (ROOT/'results.json').write_text(json.dumps(RESULT, ensure_ascii=False, indent=2))
    print('RESULTS_FILE=' + str(ROOT/'results.json'), flush=True)
    print('FINAL_STATUS=' + RESULT['status'], flush=True)
if RESULT['status'] != 'passed':
    raise SystemExit(1)
