"""Start the private backend without changing the existing VPN interface."""
import configparser
import os
from pathlib import Path

state = Path(os.environ.get('CONFIGURATION_PATH', '/data'))
state.mkdir(parents=True, exist_ok=True)
for name in ('db',):
    (state / name).mkdir(exist_ok=True)
    target = Path(name)
    if not target.exists():
        target.symlink_to(state / name, target_is_directory=True)
config = configparser.RawConfigParser()
config.read(state / 'wg-dashboard.ini')
values = {
    'Server': {'app_ip': '127.0.0.1', 'app_port': '10086', 'auth_req': 'true',
               'wg_conf_path': '/etc/wireguard', 'awg_conf_path': '/etc/amnezia/amneziawg'},
    'WireGuardConfiguration': {'autostart': '', 'peer_tracking': 'true'},
    'Other': {'welcome_session': 'false'},
}
for section, entries in values.items():
    if not config.has_section(section):
        config.add_section(section)
    for key, value in entries.items():
        config.set(section, key, value)
with (state / 'wg-dashboard.ini').open('w') as output:
    config.write(output)
if not Path('wg-dashboard.ini').exists():
    Path('wg-dashboard.ini').symlink_to(state / 'wg-dashboard.ini')
os.makedirs('log', exist_ok=True)
os.execvp('gunicorn', ['gunicorn', '-c', '/app/deploy/eh/backend_gunicorn.py', 'dashboard:app'])
