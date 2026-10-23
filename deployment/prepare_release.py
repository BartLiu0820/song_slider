"""Prepare everything that can be completed before ICP filing is cleared."""
import json
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
payload={part:{p.name:p.read_text() for p in (HERE/part).iterdir() if p.is_file()} for part in ['admin','agent']}
payload['helper']={name:(HERE/name).read_text() for name in ['Helper.Dockerfile','git-wrapper','docker-wrapper']}
remote=r'''
import json,sys,subprocess,os,re
from pathlib import Path
p=json.load(sys.stdin)
admin=Path('/opt/song-deploy/admin');admin.mkdir(exist_ok=True,mode=0o755)
for name,content in p['admin'].items():(admin/name).write_text(content)
# Backup live code and state before changing services or domain ownership.
subprocess.run(['python3',str(admin/'backup.py')],check=True)
helper=Path('/opt/song-deploy/helper-build');helper.mkdir(parents=True,exist_ok=True)
for name,content in p['helper'].items():(helper/name).write_text(content)
# Helper updates are independent of Coolify's own automatic-update setting.
# Resolve the exact runtime version instead of rebuilding an obsolete local tag.
version_php="""<?php
require '/var/www/html/vendor/autoload.php';
$app=require '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();
echo getHelperVersion();
"""
version=subprocess.check_output(['docker','exec','-i','coolify','php'],input=version_php,text=True).strip()
if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version):
 raise RuntimeError('Unexpected Coolify helper version: '+repr(version))
subprocess.run(['docker','build','--build-arg','HELPER_VERSION='+version,'-f',str(helper/'Helper.Dockerfile'),'-t','song-deploy/coolify-helper:'+version,str(helper)],check=True)
code=Path('/opt/song-deploy/agent')
for name,content in p['agent'].items():(code/name).write_text(content)
for name in ['song-deploy-agent.service','song-deploy-access.service']:
 Path('/etc/systemd/system',name).write_text(p['agent'][name])
for name in ['song-deploy-backup.service','song-deploy-backup.timer']:
 Path('/etc/systemd/system',name).write_text(p['admin'][name])
php="""<?php
require '/var/www/html/vendor/autoload.php';
$app=require '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();
$settings=App\\Models\\InstanceSettings::findOrFail(0);
$settings->fqdn=null;$settings->save();
App\\Models\\Server::findOrFail(0)->setupDynamicProxyConfiguration();
echo 'Engine public domain removed; local SSH access retained.';
"""
subprocess.run(['docker','exec','-i','coolify','php'],input=php,text=True,check=True)
subprocess.run(['docker','exec','-i','coolify','php'],input=p['admin']['enable_log_read.php'],text=True,check=True)
subprocess.run(['python3',str(admin/'publication_admin.py'),'prepare'],stdout=subprocess.DEVNULL,check=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','restart','song-deploy-agent','song-deploy-access'],check=True)
subprocess.run(['systemctl','enable','--now','song-deploy-backup.timer'],check=True)
print('\nWorkbench and protected public-readiness routes installed; certificates not requested.')
'''
ssh=['ssh','-S',str(Path.home()/'.ssh/song-deploy-tunnel.sock'),'songhuang-server']
subprocess.run(ssh+['sudo -n python3 -c '+shlex.quote(remote)],input=json.dumps(payload),text=True,check=True)
