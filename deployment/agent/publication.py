"""Publication state shared by the workbench and preview access gate."""
import json
import os
from pathlib import Path

PUBLIC_HOST = 'deploy.greatsong.online'
TEMP_IP = '47.116.108.184'
PREVIEW_SUFFIX = '.preview.greatsong.online'
READY_PATH = '/_song/ready'
ROOT = Path(os.environ.get('SONG_STATE', '/var/lib/song-deploy'))


def state():
    path = ROOT / 'system' / 'publication.json'
    return json.loads(path.read_text()) if path.exists() else {'enabled': False, 'proof': 'not-prepared'}


def enabled(): return state().get('enabled') is True


def ip_enabled(): return state().get('ip_enabled') is True


def acme_request(host, path):
    import re
    known = host in [TEMP_IP, PUBLIC_HOST] or host.endswith(PREVIEW_SUFFIX)
    return known and re.fullmatch(r'/\.well-known/acme-challenge/[A-Za-z0-9_-]+', path) is not None


def domains(slug):
    scheme = 'https' if enabled() else 'http'
    return scheme+'://'+slug+PREVIEW_SUFFIX+',http://'+slug+'.localhost'
