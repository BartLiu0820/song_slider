"""Restore the latest dump into an isolated temporary database, then remove it."""
import datetime
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

root=Path('/var/backups/song-deploy')
latest=Path((root/'latest-success.txt').read_text().strip())
assert latest.parent==root and latest.name.startswith('snapshot-')
with tarfile.open(latest/'configuration.tar.gz','r:gz') as archive:
    with tempfile.TemporaryDirectory(prefix='song-restore-',dir='/tmp') as temp:
        for name in ['etc/song-deploy/agent.json','var/lib/song-deploy/security/access.json']:
            value=archive.extractfile(name).read()
            restored=Path(temp)/Path(name).name;restored.write_bytes(value)
            assert json.loads(restored.read_text())
name='song_restore_'+datetime.datetime.now().strftime('%Y%m%d%H%M%S')
base=['docker','exec','-i','coolify-db']
created=False
try:
    subprocess.run(base+['createdb','-U','coolify',name],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    created=True
    with (latest/'coolify.sql').open('rb') as source:
        subprocess.run(base+['psql','-v','ON_ERROR_STOP=1','-U','coolify','-d',name],stdin=source,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    sql="SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
    tables=int(subprocess.check_output(base+['psql','-tA','-U','coolify','-d',name,'-c',sql],text=True))
    assert tables>20
    result={'archive_json_restored':True,'database_restore_success':True,'restored_tables':tables,'backup':latest.name}
    (root/'restore-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
finally:
    if created:subprocess.run(base+['dropdb','-U','coolify',name],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
