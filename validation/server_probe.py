"""Run on the server via SSH. Creates isolated, disposable deployment fixtures.

Uses the real public static repository plus a generated Git fixture for Python/Postgres.
Does not edit the live site's container, files, domains, or proxy configuration.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request

RUN = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
ROOT = Path.home() / 'deploy-validation' / RUN
ROOT.mkdir(parents=True, exist_ok=False)
os.chmod(ROOT, 0o700)
PROJECT = 'songproof-' + RUN
RESULTS = {'run': RUN, 'directory': str(ROOT), 'checks': [], 'timings': {}}
DOCKER = ['sudo', '-n', 'docker']
IMAGE = 'song-deploy-proof:' + RUN
START = time.monotonic()


def run(args, timeout=90, check=True, env=None):
    p = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)
    with (ROOT / 'commands.log').open('a') as f:
        f.write('\n$ ' + ' '.join(args) + '\n' + p.stdout + p.stderr)
    if check and p.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(args[:7]) + '\n' + p.stderr[-1200:])
    return p


def mark(name, detail):
    RESULTS['checks'].append({'name': name, 'passed': True, 'detail': detail})
    print(json.dumps(RESULTS['checks'][-1], ensure_ascii=False), flush=True)


def compose(*args, version='v1', timeout=90, check=True):
    # sudo strips caller environment; explicitly pass a non-secret Compose env file.
    env_file = ROOT / 'compose-image.env'
    env_file.write_text('APP_IMAGE=' + IMAGE + '-' + version + '\n')
    return run(DOCKER + ['compose', '--env-file', str(env_file), '-p', PROJECT,
                        '-f', str(ROOT / 'compose.json'), *args],
               timeout=timeout, check=check)


def request(host, path='/', method='GET', body=None):
    req = urllib.request.Request('http://127.0.0.1:18080' + path, data=body,
                                 headers={'Host': host}, method=method)
    with urllib.request.urlopen(req, timeout=4) as r:
        return r.status, r.read(), dict(r.headers)


def wait_http(host, path='/health'):
    deadline = time.monotonic() + 40
    last_error = None
    while time.monotonic() < deadline:
        try:
            status, body, _ = request(host, path)
            if status == 200:
                return json.loads(body)
        except (OSError, ValueError, urllib.error.HTTPError) as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError('Health timeout: ' + host + ': ' + str(last_error))


APP = '''import json, os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pg8000.dbapi
VERSION = Path('/app/VERSION').read_text().strip()
def connect():
    return pg8000.dbapi.connect(host='database', user='proof', database='proof',
        password=Path('/run/secrets/db_password').read_text().strip(), timeout=3)
class Handler(BaseHTTPRequestHandler):
    def respond(self, status, data):
        raw=json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        if os.getenv('FAIL_HEALTH') == '1':
            return self.respond(503, {'healthy':False})
        data={'version':VERSION,'healthy':True}
        try:
            if os.getenv('USE_DB') == '1':
                con=connect()
                try:
                    cur=con.cursor()
                    cur.execute('CREATE TABLE IF NOT EXISTS visits (id serial PRIMARY KEY)')
                    if self.path == '/items':
                        cur.execute('SELECT COUNT(*) FROM visits')
                        data['count']=cur.fetchone()[0]
                    else:
                        cur.execute('SELECT 1')
                        data['database']=cur.fetchone()[0] == 1
                    con.commit()
                finally: con.close()
            self.respond(200,data)
        except Exception:
            self.respond(503,{'healthy':False,'database':False})
    def do_POST(self):
        if self.path != '/items' or os.getenv('USE_DB') != '1':
            return self.respond(404,{'error':'not found'})
        try:
            con=connect()
            try:
                cur=con.cursor()
                cur.execute('INSERT INTO visits DEFAULT VALUES RETURNING id')
                row=cur.fetchone()[0]
                con.commit()
            finally: con.close()
            self.respond(201,{'id':row})
        except Exception:
            self.respond(503,{'healthy':False})
ThreadingHTTPServer(('0.0.0.0',8000), Handler).serve_forever()
'''

try:
    RESULTS['live_before'] = run(['curl', '-fsS', '--max-time', '15', 'https://greatsong.online']).stdout
    RESULTS['live_before'] = hashlib.sha256(RESULTS['live_before'].encode()).hexdigest()
    t = time.monotonic()
    run(['git', 'clone', '--depth', '1', 'https://github.com/BartLiu0820/song_slider.git', 'static-source'], timeout=150)
    RESULTS['static_commit'] = run(['git', '-C', 'static-source', 'rev-parse', 'HEAD']).stdout.strip()
    RESULTS['timings']['static_git_clone_seconds'] = round(time.monotonic() - t, 2)
    static = ROOT / 'static-source/output/song-six-stages-v4'
    assert (static / 'index.html').exists()

    source = ROOT / 'backend-source'
    source.mkdir()
    (source / 'app.py').write_text(APP)
    (source / 'VERSION').write_text('v1\n')
    (source / 'Dockerfile').write_text('FROM public.ecr.aws/docker/library/python:3.12-slim\n'
        'WORKDIR /app\nRUN pip install --no-cache-dir pg8000==1.31.5\n'
        'COPY app.py VERSION /app/\nUSER 10001:10001\nEXPOSE 8000\nCMD ["python", "app.py"]\n')
    run(['git', 'init', str(source)])
    run(['git', '-C', str(source), 'add', '.'])
    git_commit = ['git', '-C', str(source), '-c', 'user.name=Deployment Probe',
                  '-c', 'user.email=probe@localhost', 'commit', '-m']
    run(git_commit + ['Synthetic backend fixture v1'])
    run(['git', 'clone', str(source), 'backend-checkout'])
    RESULTS['backend_v1_commit'] = run(['git', '-C', 'backend-checkout', 'rev-parse', 'HEAD']).stdout.strip()
    t = time.monotonic()
    run(DOCKER + ['build', '--pull=false', '-t', IMAGE + '-v1', str(ROOT / 'backend-checkout')], timeout=300)
    RESULTS['timings']['first_backend_build_seconds'] = round(time.monotonic() - t, 2)

    (ROOT / 'db-password').write_text(secrets.token_urlsafe(32))
    # Parent directory is 0700; file readable by the non-root API container.
    (ROOT / 'db-password').chmod(0o644)
    (ROOT / 'Caddyfile').write_text('''{
    auto_https off
    admin off
}
http://static.proof.local {
    reverse_proxy static:80
}
http://api.proof.local {
    reverse_proxy backend:8000
}
http://db.proof.local {
    reverse_proxy dbapi:8000
}
''')
    restricted = {'read_only': True, 'cap_drop': ['ALL'],
                  'security_opt': ['no-new-privileges:true'], 'pids_limit': 64,
                  'mem_limit': '128m', 'cpus': 0.5, 'tmpfs': ['/tmp:size=16m']}
    services = {
        'router': {'image': 'caddy:2-alpine', 'ports': ['127.0.0.1:18080:80'],
                   'networks': ['default', 'ingress'],
                   'volumes': [str(ROOT / 'Caddyfile') + ':/etc/caddy/Caddyfile:ro'],
                   'mem_limit': '64m', 'cpus': 0.25},
        'static': {'image': 'caddy:2-alpine', 'command': ['caddy', 'file-server', '--root', '/srv', '--listen', ':80'],
                   'volumes': [str(static) + ':/srv:ro'], 'mem_limit': '64m', 'cpus': 0.25},
        'backend': dict(restricted, image='${APP_IMAGE}'),
        'dbapi': dict(restricted, image='${APP_IMAGE}', environment={'USE_DB': '1'},
                      secrets=['db_password']),
        'database': {'image': 'public.ecr.aws/docker/library/postgres:16-alpine',
                     'environment': {'POSTGRES_USER': 'proof', 'POSTGRES_DB': 'proof',
                                     'POSTGRES_PASSWORD_FILE': '/run/secrets/db_password'},
                     'secrets': ['db_password'], 'volumes': ['database:/var/lib/postgresql/data'],
                     'mem_limit': '256m', 'cpus': 0.5, 'pids_limit': 128}
    }
    (ROOT / 'compose.json').write_text(json.dumps({'services': services,
        'secrets': {'db_password': {'file': './db-password'}}, 'volumes': {'database': {}},
        'networks': {'default': {'internal': True}, 'ingress': {}}}, indent=2))
    compose('up', '-d', '--pull', 'never', timeout=120)
    wait_http('api.proof.local')
    wait_http('db.proof.local')

    status, body, _ = request('static.proof.local')
    assert status == 200 and body == (static / 'index.html').read_bytes()
    req = urllib.request.Request('http://127.0.0.1:18080/evolution.mp4',
        headers={'Host': 'static.proof.local', 'Range': 'bytes=0-1023'})
    with urllib.request.urlopen(req, timeout=8) as r:
        assert r.status == 206 and len(r.read()) == 1024
    mark('real_static_git_deploy', {'commit': RESULTS['static_commit'], 'html_match': True, 'video_range': 206})
    assert wait_http('api.proof.local')['version'] == 'v1'
    mark('backend_deploy', {'version': 'v1', 'port_exposed_publicly': False})

    status, body, _ = request('db.proof.local', '/items', method='POST', body=b'')
    assert status == 201
    assert json.loads(request('db.proof.local', '/items')[1])['count'] == 1
    compose('up', '-d', '--force-recreate', 'database', 'dbapi', timeout=120)
    wait_http('db.proof.local')
    assert json.loads(request('db.proof.local', '/items')[1])['count'] == 1
    mark('database_persistence', {'inserted_rows': 1, 'rows_after_container_recreation': 1})

    (source / 'VERSION').write_text('v2\n')
    run(['git', '-C', str(source), 'add', 'VERSION'])
    run(git_commit + ['Synthetic backend fixture v2'])
    run(['git', '-C', 'backend-checkout', 'pull', '--ff-only'])
    RESULTS['backend_v2_commit'] = run(['git', '-C', 'backend-checkout', 'rev-parse', 'HEAD']).stdout.strip()
    t = time.monotonic()
    run(DOCKER + ['build', '--pull=false', '-t', IMAGE + '-v2', str(ROOT / 'backend-checkout')], timeout=180)
    RESULTS['timings']['incremental_build_seconds'] = round(time.monotonic() - t, 2)
    compose('up', '-d', '--no-deps', 'backend', version='v2')
    assert wait_http('api.proof.local')['version'] == 'v2'
    mark('git_update_deploy', {'version': 'v2', 'commit': RESULTS['backend_v2_commit']})

    run(DOCKER + ['run', '-d', '--name', PROJECT + '-bad', '--network', PROJECT + '_default',
        '--memory', '128m', '--cpus', '0.5', '--pids-limit', '64', '--read-only',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
        '-e', 'FAIL_HEALTH=1', IMAGE + '-v2'])
    probe = "import urllib.request,urllib.error;\ntry: urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)\nexcept urllib.error.HTTPError as e: print(e.code)"
    detected = False
    for _ in range(10):
        p = run(DOCKER + ['exec', PROJECT + '-bad', 'python', '-c', probe], check=False)
        if p.stdout.strip() == '503':
            detected = True
            break
        time.sleep(1)
    assert detected, 'Candidate did not return expected unhealthy status'
    # Health gate refuses publication; active backend remains v2.
    assert wait_http('api.proof.local')['version'] == 'v2'
    mark('failed_candidate_gate', {'candidate_health': 503, 'active_version': 'v2'})

    compose('up', '-d', '--no-deps', 'backend', version='v1')
    assert wait_http('api.proof.local')['version'] == 'v1'
    assert json.loads(request('db.proof.local', '/items')[1])['count'] == 1
    mark('application_rollback', {'active_version': 'v1', 'database_rows': 1, 'schema_rollback_tested': False})

    ids = compose('ps', '-q').stdout.split()
    RESULTS['resource_snapshot'] = run(DOCKER + ['stats', '--no-stream', '--format', '{{json .}}', *ids]).stdout
    RESULTS['host_memory'] = run(['free', '-m']).stdout
    RESULTS['host_disk'] = run(['df', '-h', '/']).stdout
    live_after = run(['curl', '-fsS', '--max-time', '15', 'https://greatsong.online']).stdout
    assert hashlib.sha256(live_after.encode()).hexdigest() == RESULTS['live_before']
    mark('existing_site_unchanged', {'http': 200, 'html_sha256_unchanged': True})
    RESULTS['status'] = 'passed'
except Exception as exc:
    RESULTS['status'] = 'failed'
    RESULTS['error'] = str(exc)
    print('VALIDATION ERROR:', str(exc), flush=True)
finally:
    if (ROOT / 'compose.json').exists():
        compose('logs', '--no-color', '--tail', '40', check=False)
        p = compose('down', '--volumes', '--remove-orphans', check=False, timeout=90)
        RESULTS['cleanup_compose_exit'] = p.returncode
    run(DOCKER + ['rm', '-f', PROJECT + '-bad'], check=False)
    (ROOT / 'db-password').unlink(missing_ok=True)
    RESULTS['duration_seconds'] = round(time.monotonic() - START, 2)
    (ROOT / 'results.json').write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2))
    print('RESULTS_FILE=' + str(ROOT / 'results.json'), flush=True)
    print('FINAL_STATUS=' + RESULTS['status'], flush=True)
    print('DURATION_SECONDS=' + str(RESULTS['duration_seconds']), flush=True)

if RESULTS['status'] != 'passed':
    raise SystemExit(1)
