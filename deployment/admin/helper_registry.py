"""Verified, bounded GHCR fallback for the single official Coolify helper image."""
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import http.client
import io
import json
import re
import shutil
import socket
import tarfile
import time
import urllib.request
import urllib.parse

REPOSITORY = 'coollabsio/coolify-helper'
ACCEPT = ','.join(['application/vnd.oci.image.index.v1+json',
                  'application/vnd.oci.image.manifest.v1+json',
                  'application/vnd.docker.distribution.manifest.v2+json',
                  'application/vnd.docker.distribution.manifest.list.v2+json'])
MAX_COMPRESSED = 1024 * 1024 * 1024
CHUNK = 1024 * 1024


def checked(data, digest):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
        raise ValueError('Invalid official image digest')
    if 'sha256:' + hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Official image checksum mismatch')
    return data


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith('https://'):
            raise ValueError('Refusing non-TLS registry redirect')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.remove_header('Authorization')
        return redirected


def routed_connection(host, ip, **kwargs):
    connection=http.client.HTTPSConnection(host,**kwargs)
    # Route only TCP to a current DNS answer. TLS SNI and certificate hostname
    # verification still use the original official hostname.
    connection._create_connection=lambda address,timeout=None,source_address=None: socket.create_connection(
        (ip,address[1]),timeout,source_address)
    return connection


class RoutedHTTPS(urllib.request.HTTPSHandler):
    def __init__(self,host,ip):
        super().__init__();self.host=host;self.ip=ip

    def https_open(self,request):
        def connect(host,**kwargs):
            if host.split(':')[0]==self.host:return routed_connection(host,self.ip,**kwargs)
            return http.client.HTTPSConnection(host,**kwargs)
        return self.do_open(connect,request,context=self._context)


def select_route(opener,token,layer):
    request=urllib.request.Request('https://ghcr.io/v2/'+REPOSITORY+'/blobs/'+layer['digest'],
        headers={'Authorization':'Bearer '+token,'Range':'bytes=0-65535'})
    with opener.open(request,timeout=20) as response:url=response.url
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname!='pkg-containers.githubusercontent.com':return None
    addresses=sorted({entry[4][0] for entry in socket.getaddrinfo(parsed.hostname,443,family=socket.AF_INET)})
    def probe(ip):
        connection=routed_connection(parsed.hostname,ip,timeout=5)
        start=time.monotonic();size=0
        try:
            connection.request('GET',parsed.path+'?'+parsed.query,headers={'Range':'bytes=0-65535'})
            response=connection.getresponse()
            if response.status!=206:return None
            while size<65536 and time.monotonic()-start<6:
                chunk=response.read1(min(65536-size,16384))
                if not chunk:break
                size+=len(chunk)
            if size==65536:return time.monotonic()-start,ip
        except (OSError,http.client.HTTPException):pass
        finally:connection.close()
    with ThreadPoolExecutor(max_workers=4) as pool:results=[r for r in pool.map(probe,addresses[:8]) if r]
    if not results:return None
    return RoutedHTTPS(parsed.hostname,min(results)[1])


def download(version, root, progress, platform='amd64'):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version) or platform not in ['amd64', 'arm64']:
        raise ValueError('Unsupported helper version or platform')
    deadline = time.monotonic() + 420
    opener = urllib.request.build_opener(Redirect())
    with opener.open('https://ghcr.io/token?scope=repository:' + REPOSITORY + ':pull', timeout=20) as r:
        token = json.load(r)['token']

    def get(path, byte_range=None, limit=4*1024*1024):
        for attempt in range(3):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Official helper download exceeded time limit')
            headers = {'Authorization': 'Bearer ' + token, 'Accept': ACCEPT}
            if byte_range:
                headers['Range'] = 'bytes=%d-%d' % byte_range
            req = urllib.request.Request('https://ghcr.io/v2/' + REPOSITORY + '/' + path, headers=headers)
            try:
                with opener.open(req, timeout=min(25, remaining)) as response:
                    chunks=[];size=0
                    while size<=limit:
                        if time.monotonic()>deadline:
                            raise TimeoutError('Official helper download exceeded time limit')
                        chunk=response.read1(min(65536,limit+1-size))
                        if not chunk:break
                        chunks.append(chunk);size+=len(chunk)
                    data=b''.join(chunks)
                    if len(data) > limit:
                        raise ValueError('Registry response exceeds expected size')
                    if byte_range and (response.status != 206 or
                            response.headers.get('Content-Range', '').split('/')[0] !=
                            'bytes %d-%d' % byte_range):
                        raise ValueError('Registry did not honor exact byte range')
                    return data, response.headers
            except Exception:
                if attempt == 2:
                    raise

    progress('download', '正在读取官方构建工具镜像清单并校验摘要…')
    raw, headers = get('manifests/' + version)
    index_digest = headers.get('Docker-Content-Digest')
    checked(raw, index_digest)
    manifest = json.loads(raw)
    manifest_digest = index_digest
    if 'manifests' in manifest:
        selected = next(m for m in manifest['manifests'] if
                        m.get('platform', {}).get('os') == 'linux' and
                        m['platform'].get('architecture') == platform)
        manifest_digest = selected['digest']
        raw, _ = get('manifests/' + manifest_digest)
        manifest = json.loads(checked(raw, manifest_digest))
    layers = manifest['layers']
    if not layers or len(layers) > 64 or any(type(l['size']) is not int or l['size'] < 0 for l in layers):
        raise ValueError('Invalid helper layer list')
    total = sum(l['size'] for l in layers)
    if total > MAX_COMPRESSED or shutil.disk_usage(root).free < total * 4 + 512 * 1024 * 1024:
        raise ValueError('Insufficient disk space for verified helper download')
    progress('download', '正在选择可用的官方镜像下载线路…')
    route=select_route(opener,token,max(layers,key=lambda layer:layer['size']))
    if route:opener=urllib.request.build_opener(Redirect(),route)
    progress('download', '正在读取官方镜像配置…')
    config_raw, _ = get('blobs/' + manifest['config']['digest'])
    config = json.loads(checked(config_raw, manifest['config']['digest']))
    if config['architecture'] != platform or config['os'] != 'linux':
        raise ValueError('Unexpected helper architecture')
    if len(layers) != len(config['rootfs']['diff_ids']):
        raise ValueError('Helper filesystem layer count mismatch')

    completed = 0
    for layer in {l['digest']: l for l in layers}.values():
        digest = layer['digest']
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
            raise ValueError('Invalid layer digest')
        path = root / digest[7:]
        def part(start):
            end = min(start + CHUNK, layer['size']) - 1
            data, _ = get('blobs/' + digest, (start, end), end-start+1)
            if len(data) != end-start+1:
                raise ValueError('Truncated helper layer chunk')
            return data
        h = hashlib.sha256()
        with path.open('wb') as target:
            if layer['size'] > CHUNK:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    for batch in range(0,layer['size'],8*CHUNK):
                        for data in pool.map(part,range(batch,min(batch+8*CHUNK,layer['size']),CHUNK)):
                            target.write(data); h.update(data)
            else:
                data, _ = get('blobs/' + digest, limit=layer['size'])
                if len(data) != layer['size']:
                    raise ValueError('Truncated helper layer')
                target.write(data); h.update(data)
        if 'sha256:' + h.hexdigest() != digest:
            raise ValueError('Helper layer checksum mismatch')
        completed += layer['size']
        progress('download', '正在从官方源分块下载并校验构建工具：%d / %d MB' %
                 (completed // 1048576, total // 1048576))

    archive = root / 'helper.tar.gz'
    def add(tar, name, content):
        info = tarfile.TarInfo(name); info.size = len(content); info.mode = 0o644
        tar.addfile(info, io.BytesIO(content))
    progress('verify', '下载完成，正在验证文件系统并导入构建工具…')
    names = []
    added = set()
    expanded_total = 0
    with tarfile.open(archive, 'w:gz', compresslevel=1) as tar:
        config_name = manifest['config']['digest'][7:] + '.json'
        add(tar, config_name, config_raw)
        for layer, diff in zip(layers, config['rootfs']['diff_ids']):
            if not re.fullmatch(r'sha256:[a-f0-9]{64}', diff):
                raise ValueError('Invalid filesystem digest')
            name = diff[7:] + '/layer.tar'; names.append(name)
            if name in added:
                continue
            compressed = root / layer['digest'][7:]
            expanded = root / 'expanded.tar'
            if layer['mediaType'].endswith('+gzip') or layer['mediaType'].endswith('.gzip'):
                reader = gzip.open(compressed, 'rb')
            elif layer['mediaType'].endswith('.tar'):
                reader = compressed.open('rb')
            else:
                raise ValueError('Unsupported helper compression')
            h = hashlib.sha256()
            with reader, expanded.open('wb') as target:
                for chunk in iter(lambda: reader.read(1024*1024), b''):
                    expanded_total += len(chunk)
                    if expanded_total > 3 * MAX_COMPRESSED or time.monotonic() > deadline:
                        raise ValueError('Helper expansion exceeds resource limit')
                    target.write(chunk); h.update(chunk)
            if 'sha256:' + h.hexdigest() != diff:
                raise ValueError('Helper filesystem checksum mismatch')
            tar.add(expanded, arcname=name); expanded.unlink(); added.add(name)
        add(tar, 'manifest.json', json.dumps([{'Config': config_name,
            'RepoTags': ['ghcr.io/' + REPOSITORY + ':' + version], 'Layers': names}]).encode())
    return archive, {'official_index_digest': index_digest, 'official_manifest_digest': manifest_digest,
                     'config_digest': manifest['config']['digest'], 'diff_ids': config['rootfs']['diff_ids'],
                     'cdn_route': {'hostname':route.host,'address':route.ip,'tls_hostname_verified':True} if route else None}
