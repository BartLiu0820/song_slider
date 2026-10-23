"""Unprivileged client for the fixed helper-preparation operation."""
import json
import socket
import time

SOCKET = '/run/song-deploy-helper/control.sock'


class HelperUnavailable(RuntimeError):
    pass


def request(action):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(8); connection.connect(SOCKET)
            connection.sendall(json.dumps({'action': action}).encode()+b'\n')
            with connection.makefile('rb') as source:
                data = source.readline(16385)
            if len(data) > 16384:
                raise ValueError('Oversized helper status')
            result = json.loads(data)
            if not isinstance(result, dict) or result.get('status') not in ['idle', 'preparing', 'ready', 'failed']:
                raise ValueError('Invalid helper status')
            return result
    except (OSError, ValueError) as exc:
        raise HelperUnavailable('服务器构建工具准备服务暂时不可用；旧版本继续运行，请稍后重试部署。') from exc


def ensure(report, cancelled=lambda: False):
    # Type=simple services can be running just before their socket is bound.
    for attempt in range(5):
        try:
            result = request('ensure');break
        except HelperUnavailable as exc:
            if attempt==4 or not isinstance(exc.__cause__,(FileNotFoundError,ConnectionRefusedError)):
                raise
            time.sleep(1)
    deadline = time.monotonic()+900
    while True:
        if cancelled():
            return None
        if result['status'] == 'ready':
            return result
        if result['status'] == 'failed':
            raise HelperUnavailable(result.get('message') or '服务器构建工具准备失败，请重试部署。')
        if result['status'] != 'preparing':
            raise HelperUnavailable('构建工具准备服务已重启，请重新部署。')
        report(result.get('message', '正在准备服务器构建工具…'))
        if time.monotonic() >= deadline:
            raise HelperUnavailable('服务器准备构建工具超时；旧版本继续运行，可稍后重新部署。')
        time.sleep(2)
        result = request('status')
