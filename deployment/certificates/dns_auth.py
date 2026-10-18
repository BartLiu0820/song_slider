"""Collect manual DNS challenges, then wait for authoritative DNS propagation."""
import json
import os
from pathlib import Path
import time
import dns.resolver

path = Path('/var/lib/song-acme/dns-challenges.json')
domain = os.environ['CERTBOT_DOMAIN'].removeprefix('*.')
record = {'name': '_acme-challenge.' + domain, 'type': 'TXT',
          'value': os.environ['CERTBOT_VALIDATION']}
records = json.loads(path.read_text()) if path.exists() else []
records = [r for r in records if r['name'] != record['name']] + [record]
path.write_text(json.dumps(records, indent=2) + '\n')
print(json.dumps(record), flush=True)
if int(os.environ.get('CERTBOT_REMAINING_CHALLENGES', '0')) == 0:
    deadline = time.monotonic() + 3600
    while time.monotonic() < deadline:
        try:
            servers = [str(a) for ns in dns.resolver.resolve('greatsong.online', 'NS')
                       for a in dns.resolver.resolve(str(ns.target), 'A')]
            ready = bool(servers)
            for server in servers:
                resolver = dns.resolver.Resolver(configure=False)
                resolver.nameservers = [server]
                resolver.lifetime = 5
                for item in records:
                    answers = resolver.resolve(item['name'], 'TXT')
                    ready &= item['value'] in [b''.join(a.strings).decode() for a in answers]
            if ready:
                time.sleep(30)
                print('All authoritative nameservers verified.', flush=True)
                break
        except dns.exception.DNSException:
            pass
        time.sleep(10)
    else:
        raise SystemExit('DNS validation records were not published within one hour.')
