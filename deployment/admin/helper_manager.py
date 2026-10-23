"""Narrow root broker: prepare only the helper selected by the local Coolify engine.

No caller-supplied images, versions, paths, commands or Docker arguments are accepted.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import re
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time

import helper_registry

RUNTIME = Path('/run/song-deploy-helper')
STATE = Path('/var/lib/song-deploy-helper')
CONTEXT = Path('/opt/song-deploy/helper-build')
MAINTENANCE = Path('/run/song-deploy-cleanup/maintenance.lock')
FILES = ['Helper.Dockerfile', 'git-wrapper', 'docker-wrapper']
IMAGE = 'song-deploy/coolify-helper'
LOCK = threading.RLock()
CURRENT = {'status': 'idle'}
PHP = r'''<?php
require '/var/www/html/vendor/autoload.php';
$app=require '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
echo json_encode(['version'=>getHelperVersion(),'image'=>coolifyHelperImage()]);
'''


def run(args, timeout=30, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout, **kwargs)


def selected():
    result = json.loads(run(['docker', 'exec', '-i', 'coolify', 'php'], input=PHP).stdout)
    if result.get('image') != IMAGE or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', result.get('version', '')):
        raise ValueError('Unexpected engine helper configuration')
    return result['version']


def fingerprint():
    result = hashlib.sha256()
    for name in FILES:
        path = CONTEXT / name
        stat = path.stat()
        if path.is_symlink() or stat.st_uid != 0 or stat.st_mode & 0o022:
            raise ValueError('Helper source must be root-owned and not writable by other users')
        result.update(name.encode() + b'\0' + path.read_bytes())
    directory = CONTEXT.stat()
    if directory.st_uid != 0 or directory.st_mode & 0o022 or CONTEXT.is_symlink():
        raise ValueError('Unsafe helper build directory')
    return result.hexdigest()


def inspect(image):
    result = subprocess.run(['docker', 'image', 'inspect', image], capture_output=True, text=True, timeout=20)
    if result.returncode:
        return None
    return json.loads(result.stdout)[0]


def publish(phase, message):
    with LOCK:
        CURRENT.update(phase=phase, message=message, updated_at=int(time.time()))


def prepare(version, source_hash):
    target = IMAGE + ':' + version
    receipt_path = STATE / ('ready-' + version + '.json')
    try:
        receipt = json.loads(receipt_path.read_text())
        if not isinstance(receipt,dict):receipt={}
    except (OSError,ValueError):
        receipt = {}
    current = inspect(target)
    if current and receipt.get('source_hash') == source_hash and receipt.get('image_id') == current['Id']:
        return {**receipt, 'cached': True}
    base = 'ghcr.io/coollabsio/coolify-helper:' + version
    provenance = None
    if not inspect(base):
        publish('pull', '正在下载官方构建工具 '+version+'；连接过慢时会自动切换分块下载…')
        try:
            run(['docker', 'pull', base], timeout=75)
        except (subprocess.SubprocessError, OSError):
            publish('download', '普通下载未完成，正在切换官方源分块下载并校验…')
            with tempfile.TemporaryDirectory(prefix='download-', dir=STATE) as temp:
                arch = {'x86_64': 'amd64', 'aarch64': 'arm64'}[platform.machine()]
                archive, provenance = helper_registry.download(version, Path(temp), publish, arch)
                run(['docker', 'load', '-i', str(archive)], timeout=90)
                loaded = inspect(base)
                if not loaded or loaded['RootFS']['Layers'] != provenance['diff_ids']:
                    raise ValueError('Loaded helper filesystem differs from official source')
    publish('build', '正在构建本机适配的工具镜像 '+version+'…')
    candidate = 'song-deploy/helper-staging:' + version + '-' + source_hash[:12]
    run(['docker', 'build', '--build-arg', 'HELPER_VERSION='+version, '-f', str(CONTEXT/'Helper.Dockerfile'),
         '-t', candidate, str(CONTEXT)], timeout=120)
    publish('verify', '正在验证构建工具和网络适配脚本…')
    smoke = run(['docker', 'run', '--rm', '--pull=never', '--network=none', candidate, 'sh', '-ec',
        'test "$(command -v git)" = /usr/local/bin/git; '
        'test "$(command -v docker)" = /usr/local/bin/docker; '
        'git --version; docker --version; docker buildx version; '
        'sha256sum /usr/local/bin/git /usr/local/bin/docker']).stdout
    for name in FILES[1:]:
        if hashlib.sha256((CONTEXT/name).read_bytes()).hexdigest() not in smoke:
            raise ValueError('Helper wrapper checksum mismatch')
    if fingerprint() != source_hash:
        raise ValueError('Helper source changed during preparation')
    # Keep the prior verified image available until the replacement has passed smoke checks.
    if current:
        run(['docker', 'tag', current['Id'], 'song-deploy/helper-rollback:'+version+'-'+str(time.time_ns())])
    run(['docker', 'tag', candidate, target])
    image = inspect(target)
    result = {'version': version, 'source_hash': source_hash, 'image_id': image['Id'],
              'prepared_at': int(time.time()), 'smoke': smoke, 'provenance': provenance}
    temporary = receipt_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result)); temporary.replace(receipt_path)
    return {**result, 'cached': False}


def work():
    try:
        # Shared with deployment workers; excludes destructive cleanup without deadlocking them.
        with MAINTENANCE.open('rb') as handle:
            fcntl.flock(handle, fcntl.LOCK_SH)
            for _ in range(3):
                version = selected()
                publish('check', '正在检查构建工具 '+version+'…')
                result = prepare(version, fingerprint())
                if selected() == version:
                    with LOCK:
                        CURRENT.update(status='ready', phase='ready', version=version,
                            image_id=result['image_id'], cached=result['cached'],
                            message='构建工具已就绪', updated_at=int(time.time()))
                    return
            raise RuntimeError('Helper version repeatedly changed during preparation')
    except Exception as exc:
        # Details stay in root-only diagnostics; never expose shell/registry response data to the app.
        (STATE/'last-error.json').write_text(json.dumps({'type':type(exc).__name__, 'detail':str(exc),
                                                      'at':int(time.time())}))
        with LOCK:
            CURRENT.update(status='failed', phase='failed', updated_at=int(time.time()),
                message='服务器未能自动准备构建工具（网络、磁盘或镜像校验未通过）。旧版本继续运行；再次部署会重新尝试。')


def dispatch(message):
    global CURRENT
    if not isinstance(message, dict) or set(message) != {'action'} or message['action'] not in ['ensure', 'status']:
        raise ValueError('Only fixed helper ensure/status requests are accepted')
    with LOCK:
        if message['action'] == 'ensure' and CURRENT['status'] != 'preparing':
            CURRENT = {'status':'preparing', 'phase':'check', 'message':'正在检查服务器构建工具…',
                       'updated_at':int(time.time())}
            threading.Thread(target=work, daemon=True).start()
        return dict(CURRENT)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        try:
            _, uid, _ = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid not in [0, pwd.getpwnam('song-deploy').pw_uid]:
                raise ValueError('Access denied')
            line = self.rfile.readline(1025)
            if len(line) > 1024:
                raise ValueError('Request too large')
            result = dispatch(json.loads(line))
        except Exception:
            result = {'status':'failed', 'message':'构建工具准备服务拒绝了请求。'}
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode()+b'\n')


def main():
    group = pwd.getpwnam('song-deploy').pw_gid
    RUNTIME.mkdir(mode=0o750, exist_ok=True); os.chown(RUNTIME, 0, group)
    STATE.mkdir(mode=0o700, exist_ok=True)
    path = RUNTIME/'control.sock'; path.unlink(missing_ok=True)
    server = socketserver.ThreadingUnixStreamServer(str(path), Handler)
    path.chmod(0o660); os.chown(path, 0, group)
    server.serve_forever()


if __name__ == '__main__':
    main()
