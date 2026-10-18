"""Manage the temporary IP entry without changing the domain publication gate."""
import argparse
import json
from pathlib import Path
import subprocess
from publication_admin import atomic, read_state, STATE

IP = '47.116.108.184'
ROUTES = Path('/data/coolify/proxy/dynamic/song-ip.yaml')
CERT = Path('/etc/letsencrypt/song-ip/live/song-ip/fullchain.pem')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','enable','disable','status'])
    action=parser.parse_args().action
    state=read_state()
    if action=='status':
        print(json.dumps({'ip_enabled':state.get('ip_enabled',False),'domain_enabled':state['enabled']}));return
    if action=='enable':
        subprocess.run(['openssl','verify','-CAfile','/etc/ssl/certs/ca-certificates.crt',
                        '-untrusted',str(CERT),'-verify_ip',IP,str(CERT)],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(['openssl','x509','-in',str(CERT),'-checkend','3600','-noout'],check=True,stdout=subprocess.DEVNULL)
        state['ip_enabled']=True
    elif action=='disable':state['ip_enabled']=False
    routers={'song-ip-http':{'rule':f'Host(`{IP}`)','entryPoints':['http'],'priority':70000,'service':'song-ip'},
             'song-domain-acme':{'rule':r'(Host(`deploy.greatsong.online`) || HostRegexp(`^[a-z0-9-]+\.preview\.greatsong\.online$`)) && PathPrefix(`/.well-known/acme-challenge/`)',
                                 'entryPoints':['http'],'priority':1000000,'service':'acme-http@internal'}}
    if CERT.exists():routers['song-ip-https']={**routers['song-ip-http'],'entryPoints':['https'],'tls':{}}
    atomic(ROUTES,{'http':{'routers':routers,'services':{'song-ip':{'loadBalancer':{'servers':[{'url':'http://172.21.0.1:9100'}]}}}}})
    atomic(STATE,state)
    print(json.dumps({'ip_enabled':state.get('ip_enabled',False),'domain_enabled':state['enabled']}))

if __name__=='__main__':main()
