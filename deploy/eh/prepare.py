"""Run on each Oracle host before Komodo deploy. Does not restart the VPN."""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

def run(args):
    return subprocess.check_output(args, text=True, timeout=15).strip()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('role', choices=['vpn1', 'vpn2'])
    parser.add_argument('--secrets', type=Path, help='Existing root-only shared secrets file from VPN2')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo on the actual Oracle host')
    state = Path('/etc/komodo/eh-wgdashboard')
    state.mkdir(parents=True, exist_ok=True)
    state.chmod(0o700)
    for name in ('backend', 'node', 'gateway', 'backups'):
        (state / name).mkdir(exist_ok=True)
    config = '/opt/amnezia/wireguard'
    info = json.loads(run(['docker', 'inspect', 'amnezia-wireguard']))[0]
    if not info['State']['Running']:
        raise SystemExit('Amnezia must be running')
    mounts = [mount for mount in info['Mounts'] if mount['Destination'] == config]
    if len(mounts) != 1 or mounts[0]['Type'] != 'bind':
        raise SystemExit('First run sudo python3 deploy/eh/persist_amnezia.py to persist the existing VPN config')
    source = Path(mounts[0]['Source'])
    if not (source / 'wg0.conf').is_file():
        raise SystemExit('Expected existing wg0.conf was not found; do not deploy')
    backup = state / 'backups' / time.strftime('wg0-%Y%m%d-%H%M%S.conf')
    backup.write_bytes((source / 'wg0.conf').read_bytes())
    backup.chmod(0o600)
    env_path = state / f'{args.role}.env'
    values = {}
    secret_file = args.secrets or env_path
    if secret_file.exists():
        for line in secret_file.read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                values[key] = value.strip("'\"")
    if args.role == 'vpn2':
        for key in ('EH_VPN1_TOKEN', 'EH_VPN2_TOKEN', 'EH_SESSION_SECRET'):
            values.setdefault(key, secrets.token_hex(32))
        if not values.get('EH_ADMIN_USERNAME'):
            values['EH_ADMIN_USERNAME'] = input('Admin username [admin]: ').strip() or 'admin'
        if not values.get('EH_ADMIN_PASSWORD_HASH'):
            password = getpass.getpass('Choose the central admin password (minimum 8 characters): ')
            if len(password) < 8 or password != getpass.getpass('Confirm password: '):
                raise SystemExit('Password too short or confirmation does not match')
            # Generate using the same Werkzeug version inside the services image,
            # or install Flask in a temporary host venv before using this helper.
            from werkzeug.security import generate_password_hash
            values['EH_ADMIN_PASSWORD_HASH'] = generate_password_hash(password)
        peer_env = state / 'vpn1-shared.env'
        peer_env.write_text(f"EH_VPN1_TOKEN='{values['EH_VPN1_TOKEN']}'\n")
        peer_env.chmod(0o600)
        print('Copy only vpn1-shared.env securely to VPN1; it contains no admin password.')
    elif not values.get('EH_VPN1_TOKEN'):
        raise SystemExit('Supply --secrets pointing to vpn1-shared.env from VPN2')
    values['EH_WG_CONFIG_DIR'] = str(source)
    env_path.write_text(''.join(f"{key}='{value}'\n" for key, value in values.items()))
    env_path.chmod(0o600)
    print(f'Prepared {args.role}. Existing VPN config backed up. Secrets saved to {env_path}.')
    print('Use that file as the Compose --env-file for the Komodo stack.')

if __name__ == '__main__':
    main()
