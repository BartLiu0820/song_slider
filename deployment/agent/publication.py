"""Publication state shared by the workbench and preview access gate."""
import json
import os
from pathlib import Path

PUBLIC_HOST = 'deploy.greatsong.online'
PREVIEW_SUFFIX = '.preview.greatsong.online'
READY_PATH = '/_song/ready'
ROOT = Path(os.environ.get('SONG_STATE', '/var/lib/song-deploy'))


def state():
    path = ROOT / 'system' / 'publication.json'
    return json.loads(path.read_text()) if path.exists() else {'enabled': False, 'proof': 'not-prepared'}


def enabled(): return state().get('enabled') is True


def domains(slug):
    scheme = 'https' if enabled() else 'http'
    return scheme+'://'+slug+PREVIEW_SUFFIX+',http://'+slug+'.localhost'
