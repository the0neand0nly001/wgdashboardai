"""Start the private backend without changing the existing VPN interface."""
import configparser
import os
import ipaddress
import json
import subprocess
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
bind_address = '127.0.0.1'
if os.environ.get('EH_PRIVATE_BRIDGE') == '1':
    interface = json.loads(subprocess.check_output(['ip', '-j', '-4', 'addr', 'show', 'dev', 'eth0'], text=True))[0]
    bind_address = str(ipaddress.IPv4Address(next(a['local'] for a in interface['addr_info'] if a['scope'] == 'global')))
    route = json.loads(subprocess.check_output(['ip', '-j', '-4', 'route', 'show', 'default'], text=True))[0]
    gateway = str(ipaddress.IPv4Address(route['gateway']))
    # Reserve only our backend port. Other Amnezia firewall rules are untouched.
    def firewall(*args, optional=False):
        result = subprocess.run(['iptables', '-w', '5', '-t', 'filter', *args],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode and not optional:
            raise RuntimeError('Unable to protect private backend; refusing to listen')
        return result.returncode
    if firewall('-L', 'EHWGD_BACKEND', optional=True):
        firewall('-N', 'EHWGD_BACKEND')
    guard = ['-p', 'tcp', '--dport', '10086', '-m', 'comment', '--comment', 'eh-backend-setup', '-j', 'DROP']
    firewall('-I', 'INPUT', '1', *guard)
    firewall('-F', 'EHWGD_BACKEND')
    firewall('-A', 'EHWGD_BACKEND', '-i', 'eth0', '-s', gateway, '-p', 'tcp', '--dport', '10086', '-j', 'ACCEPT')
    firewall('-A', 'EHWGD_BACKEND', '-p', 'tcp', '--dport', '10086', '-j', 'DROP')
    if firewall('-C', 'INPUT', '-j', 'EHWGD_BACKEND', optional=True):
        firewall('-I', 'INPUT', '1', '-j', 'EHWGD_BACKEND')
    firewall('-D', 'INPUT', *guard)
os.environ['EH_BACKEND_BIND'] = bind_address
values = {
    'Server': {'app_ip': bind_address, 'app_port': '10086', 'auth_req': 'true',
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
