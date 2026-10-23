"""Build the local helper for the version selected by the running Coolify engine.

Manual recovery command; normal workbench deployments now prepare helpers automatically.
Does not restart services, alter registry policy, or trigger an application deploy.
"""
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
REMOTE = r'''
import fcntl,hashlib,json,re,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path

payload=json.load(sys.stdin)
lock=Path('/run/song-deploy-cleanup/maintenance.lock').open('rb')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
sys.path.insert(0,'/opt/song-deploy/admin')
import cleanup
cleanup.assert_idle()
php="""<?php
require '/var/www/html/vendor/autoload.php';
$app=require '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();
echo json_encode(['version'=>getHelperVersion(),'image'=>coolifyHelperImage()]);
"""
def selected():
 return json.loads(subprocess.check_output(['docker','exec','-i','coolify','php'],input=php,text=True))
settings=selected()
version=settings['version']
if settings['image']!='song-deploy/coolify-helper' or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version):
 raise RuntimeError('Unexpected helper configuration; no changes made')
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup=Path('/var/backups/song-deploy')/('helper-sync-'+stamp)
backup.mkdir(mode=0o700)
context=Path('/opt/song-deploy/helper-build')
if context.exists():shutil.copytree(context,backup/'source')
context.mkdir(parents=True,exist_ok=True);context.chmod(0o755)
image=settings['image']+':'+version
previous=subprocess.run(['docker','image','inspect',image,'--format','{{.Id}}'],capture_output=True,text=True)
if previous.returncode==0:
 old=previous.stdout.strip()
 subprocess.run(['docker','tag',old,'song-deploy/helper-rollback:'+stamp],check=True)
 (backup/'previous-image-id').write_text(old+'\n')
for name,content in payload.items():
 (context/name).write_text(content);(context/name).chmod(0o644)
subprocess.run(['docker','build','--build-arg','HELPER_VERSION='+version,
 '-f',str(context/'Helper.Dockerfile'),'-t',image,str(context)],check=True,stdout=sys.stderr)
# Test executable selection without network, credentials, or Docker socket access.
smoke=subprocess.check_output(['docker','run','--rm','--pull=never','--network=none',image,'sh','-ec',
 'test "$(command -v git)" = /usr/local/bin/git; '
 'test "$(command -v docker)" = /usr/local/bin/docker; '
 'git --version; docker --version; docker buildx version; '
 'sha256sum /usr/local/bin/git /usr/local/bin/docker'],text=True)
for name in ['git-wrapper','docker-wrapper']:
 if hashlib.sha256(payload[name].encode()).hexdigest() not in smoke:
  raise RuntimeError('Helper wrapper checksum mismatch: '+name)
if selected()!=settings:
 raise RuntimeError('Engine helper selection changed while building; run sync again')
base=json.loads(subprocess.check_output(['docker','image','inspect','ghcr.io/coollabsio/coolify-helper:'+version],text=True))[0]
identity=subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip()
report={'selected':settings,'image_id':identity,'loaded_base_repo_digests':base['RepoDigests'],
 'backup':str(backup),'smoke':smoke,'checked_at':datetime.now(timezone.utc).isoformat()}
(backup/'result.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
'''


if __name__ == '__main__':
    payload = {name: (HERE / name).read_text() for name in
               ['Helper.Dockerfile', 'git-wrapper', 'docker-wrapper']}
    subprocess.run(['ssh', '-o', 'BatchMode=yes', 'songhuang-server',
                    'sudo -n python3 -c ' + shlex.quote(REMOTE)],
                   input=json.dumps(payload), text=True, check=True)
