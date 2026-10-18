"""Stage legacy-site routing without changing the public listener."""
import json
import shlex
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
routes = {
    'http': {
        'routers': {'legacy-site-http': {
            'rule': 'Host(`greatsong.online`) || Host(`www.greatsong.online`)',
            'entryPoints': ['http'], 'service': 'legacy-site-http'}},
        'services': {'legacy-site-http': {'loadBalancer': {
            'servers': [{'url': 'http://song-slider:80'}]}}},
    },
    'tcp': {
        'routers': {'legacy-site-tls': {
            'rule': 'HostSNI(`greatsong.online`) || HostSNI(`www.greatsong.online`)',
            'entryPoints': ['https'], 'service': 'legacy-site-tls',
            'tls': {'passthrough': True}}},
        'services': {'legacy-site-tls': {'loadBalancer': {
            'servers': [{'address': 'song-slider:443'}]}}},
    },
}
(HERE/'legacy-routing.json').write_text(json.dumps(routes, indent=2)+'\n')
remote = r'''
import json,sys,subprocess,os
from pathlib import Path
p=json.load(sys.stdin)
f=Path('/data/coolify/proxy/dynamic/legacy-site.yml')
f.write_text(json.dumps(p,indent=2));os.chown(f,9999,0)
net=json.loads(subprocess.check_output(['docker','inspect','song-slider']))[0]['NetworkSettings']['Networks']
if 'coolify' not in net: subprocess.run(['docker','network','connect','coolify','song-slider'],check=True)
print('Legacy routing staged; public ports unchanged')
'''
subprocess.run(['ssh','-o','BatchMode=yes','songhuang-server',
    'sudo -n python3 -c '+shlex.quote(remote)],input=json.dumps(routes),text=True,check=True)
php = """<?php
require '/var/www/html/vendor/autoload.php';
$app = require '/var/www/html/bootstrap/app.php';
$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();
App\\Models\\Server::findOrFail(0)->setupDynamicProxyConfiguration();
echo "Dashboard routing generated\\n";
"""
subprocess.run(['ssh','-o','BatchMode=yes','songhuang-server',
    'sudo -n docker exec -i coolify php'],input=php,text=True,check=True)
