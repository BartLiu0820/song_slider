"""Configure the installed instance and save its API token outside the repository."""
from pathlib import Path
import json
import subprocess

here=Path(__file__).resolve().parent
private=Path.home()/'.config/song-deploy'
token_path=private/'coolify-api-token'
issue='0' if token_path.exists() else '1'
p=subprocess.run(['ssh','-o','BatchMode=yes','songhuang-server',
    'sudo -n docker exec -i -e ISSUE_TOKEN='+issue+' coolify php'],
    input=(here/'configure_coolify.php').read_text(),capture_output=True,text=True,timeout=60)
if p.returncode:
    print(p.stderr[-1500:])
    raise SystemExit(p.returncode)
result=json.loads(p.stdout)
token=result.pop('token',None)
if token:
    token_path.write_text(token+'\n')
    token_path.chmod(0o600)
(here/'instance.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
