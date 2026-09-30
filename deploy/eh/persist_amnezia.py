"""Give existing Amnezia config a persistent bind mount, preserving a rollback.

Run once on each host BEFORE installing the dashboard. This briefly restarts
Amnezia but keeps its image, config, public ports, command and existing peers.
"""
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

NAME = 'amnezia-wireguard'
DESTINATION = '/opt/amnezia/wireguard'
STATE = Path('/etc/komodo/eh-wgdashboard')

class DockerConnection(http.client.HTTPConnection):
    def __init__(self):
        super().__init__('localhost', timeout=60)
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(60)
        self.sock.connect('/var/run/docker.sock')

def api(method, path, body=None):
    connection = DockerConnection()
    try:
        connection.request(method, path, body=json.dumps(body) if body is not None else None,
                           headers={'Content-Type':'application/json'})
        response = connection.getresponse()
        raw = response.read()
        value = json.loads(raw) if raw else {}
        if response.status >= 400:
            raise RuntimeError(f"Docker operation failed ({response.status}): {value.get('message','')}" )
        return value
    finally:
        connection.close()

def create_payload(metadata, source):
    if metadata['HostConfig']['NetworkMode'] != 'bridge':
        raise ValueError('This helper only supports the verified default Docker bridge setup')
    payload = dict(metadata['Config'])
    payload['Image'] = metadata['Image']  # Pin the already-running local image ID.
    host = dict(metadata['HostConfig'])
    host['Binds'] = list(host.get('Binds') or []) + [str(source) + ':' + DESTINATION,
                      str(Path(source).parent / 'amnezia-start.sh') + ':/opt/amnezia/start.sh:ro']
    payload['HostConfig'] = host
    return payload

def main():
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo on the actual Oracle host')
    metadata = api('GET', '/containers/' + NAME + '/json')
    existing = [m for m in metadata['Mounts'] if m['Destination'] == DESTINATION]
    if existing:
        print('The Amnezia config directory is already persistent. No change required.')
        return
    if not metadata['State']['Running']:
        raise SystemExit('Expected the existing VPN container to be running')
    create_payload(metadata, STATE / 'vpnconfig')  # Validate before stopping anything.
    stamp = time.strftime('%Y%m%d-%H%M%S')
    STATE.mkdir(parents=True, exist_ok=True)
    STATE.chmod(0o700)
    backup = STATE / 'backups' / ('amnezia-' + stamp)
    backup.mkdir(parents=True, mode=0o700)
    (backup / 'inspect.json').write_text(json.dumps(metadata))
    (backup / 'inspect.json').chmod(0o600)
    config_dir = STATE / 'vpnconfig'
    if config_dir.exists():
        raise SystemExit('vpnconfig already exists without an active mount; inspect it before proceeding')
    config_dir.mkdir(mode=0o700)
    subprocess.run(['docker','cp', NAME + ':' + DESTINATION + '/.', str(config_dir)], check=True)
    if not (config_dir / 'wg0.conf').is_file():
        raise SystemExit('Config copy did not contain wg0.conf; original container is unchanged')
    shutil.copytree(config_dir, backup / 'config')
    startup = STATE / 'amnezia-start.sh'
    subprocess.run(['docker','cp',NAME + ':/opt/amnezia/start.sh',str(startup)],check=True)
    startup.chmod(0o700)
    shutil.copy2(startup, backup / 'start.sh')
    expected = (config_dir / 'wg0.conf').read_bytes()
    old_name = NAME + '-before-eh-' + stamp
    created = False
    renamed = False
    stopped = False
    try:
        api('POST', '/containers/' + NAME + '/stop?t=15')
        stopped = True
        api('POST', '/containers/' + NAME + '/rename?name=' + old_name)
        renamed = True
        api('POST', '/containers/create?name=' + NAME, create_payload(metadata, config_dir))
        created = True
        api('POST', '/containers/' + NAME + '/start')
        time.sleep(3)
        current = api('GET', '/containers/' + NAME + '/json')
        if not current['State']['Running']:
            raise RuntimeError('Replacement did not remain running')
        interfaces = subprocess.check_output(['docker','exec',NAME,'wg','show','interfaces'],text=True,timeout=10)
        if 'wg0' not in interfaces.split() or (config_dir / 'wg0.conf').read_bytes() != expected:
            raise RuntimeError('VPN interface/config verification failed')
        print('Existing VPN restarted with the same config and public ports.')
        print('Rollback container retained as:', old_name)
        print('Root-only config backup:', backup)
    except Exception:
        if created:
            api('DELETE', '/containers/' + NAME + '?force=true')
        if renamed:
            api('POST', '/containers/' + old_name + '/rename?name=' + NAME)
        if stopped:
            api('POST', '/containers/' + NAME + '/start')
        raise

if __name__ == '__main__':
    main()
