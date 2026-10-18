"""Consistent engine database dump plus private configuration/state archive."""
import datetime
import json
from pathlib import Path
import subprocess
import tarfile
import os
import shutil

os.umask(0o077)
root=Path('/var/backups/song-deploy')
target=root/('snapshot-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
target.mkdir(parents=True,mode=0o700)
try:
    with (target/'coolify.sql').open('wb') as out:
        subprocess.run(['docker','exec','coolify-db','pg_dump','-U','coolify','-d','coolify','--no-owner'],stdout=out,check=True)
    with tarfile.open(target/'configuration.tar.gz','w:gz') as archive:
        for path in ['/etc/song-deploy','/etc/letsencrypt','/var/lib/song-deploy','/opt/song-deploy/agent','/opt/song-deploy/admin',
                     '/home/admin/deploy-validation/helper-build','/data/coolify/source','/data/coolify/ssh','/data/coolify/proxy',
                     '/etc/systemd/system/song-deploy-agent.service','/etc/systemd/system/song-deploy-access.service',
                     '/etc/systemd/system/song-deploy-git.service',
                     '/etc/systemd/system/song-ip-certificate.service','/etc/systemd/system/song-ip-certificate.timer',
                     '/home/admin/song_slider/output/song-six-stages-v4/docker-compose.yml',
                     '/home/admin/song_slider/output/song-six-stages-v4/Caddyfile',
                     '/home/admin/song_slider/output/song-six-stages-v4/index.html']:
            if Path(path).exists():archive.add(path,arcname=path.lstrip('/'))
    # Validate archive structure and database dump before marking complete.
    with tarfile.open(target/'configuration.tar.gz','r:gz') as archive:
        assert 'etc/song-deploy/agent.json' in archive.getnames()
    assert (target/'coolify.sql').stat().st_size>10000
    (target/'manifest.json').write_text(json.dumps({'complete':True,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope':'Coolify database, deployment code/configuration/source snapshots; excludes running application database volumes'},indent=2))
    (root/'latest-success.txt').write_text(str(target)+'\n')
    # Retain seven successful snapshots from this script only; other/manual
    # backups and incomplete snapshots remain available for investigation.
    completed=sorted(p for p in root.glob('snapshot-*') if p.is_dir() and not p.is_symlink() and (p/'manifest.json').exists())
    for old in completed[:-7]:shutil.rmtree(old)
    print('Backup verified:',target)
except Exception:
    print('Backup incomplete:',target);raise
