"""Private host bridge: existing Amnezia namespace, stats and forwarding leases."""
import ctypes
import datetime as dt
import hmac
import http.client
import ipaddress
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from flask import Flask, jsonify, request

CONTAINER = os.environ.get('EH_AMNEZIA_CONTAINER', 'amnezia-wireguard')
TOKEN = os.environ.get('EH_NODE_TOKEN', '')
STATE = Path(os.environ.get('EH_STATE', '/data'))
PORT_MIN, PORT_MAX = 45100, 45120
LOCK = threading.RLock()
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024

def run(args):
    return subprocess.check_output(args, text=True, timeout=15).strip()

def inspect():
    value = json.loads(run(['docker', 'inspect', CONTAINER]))[0]
    if not value['State']['Running']:
        raise RuntimeError('Amnezia is not running')
    return value

def connect_backend():
    pid = inspect()['State']['Pid']
    original = os.open('/proc/self/ns/net', os.O_RDONLY)
    target = os.open(f'/proc/{pid}/ns/net', os.O_RDONLY)
    libc = ctypes.CDLL(None, use_errno=True)
    sock = None
    try:
        if libc.setns(target, 0x40000000):
            raise OSError(ctypes.get_errno(), 'Cannot enter VPN namespace')
        sock = socket.create_connection(('127.0.0.1', 10086), timeout=15)
    finally:
        error = libc.setns(original, 0x40000000)
        os.close(target)
        os.close(original)
        if error:
            if sock:
                sock.close()
            raise OSError(ctypes.get_errno(), 'Cannot restore host namespace')
    return sock

def db():
    STATE.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(STATE / 'node.sqlite')
    connection.row_factory = sqlite3.Row
    connection.execute('CREATE TABLE IF NOT EXISTS leases (id TEXT PRIMARY KEY, peer TEXT, ip TEXT, local_port INTEGER, public_port INTEGER UNIQUE, protocol TEXT, expires REAL, label TEXT)')
    connection.execute('CREATE TABLE IF NOT EXISTS samples (time REAL, upload REAL, download REAL)')
    connection.execute('CREATE TABLE IF NOT EXISTS counters (peer TEXT PRIMARY KEY, epoch TEXT, up INTEGER, down INTEGER, total_up INTEGER, total_down INTEGER, time REAL)')
    return connection

def peers():
    fields = {}
    for field in ('allowed-ips', 'latest-handshakes', 'transfer', 'endpoints'):
        raw = run(['docker', 'exec', CONTAINER, 'wg', 'show', 'wg0', field])
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) > 1:
                fields.setdefault(parts[0], {'key': parts[0]})[field] = parts[1:]
    return list(fields.values())

def peer_ip(key):
    matches = [p for p in peers() if p['key'] == key]
    if len(matches) != 1:
        raise ValueError('Choose an existing peer on this VPN server')
    addresses = matches[0].get('allowed-ips', [])
    addresses = ','.join(addresses).split(',')
    exact = [ipaddress.ip_network(a.strip(), strict=True) for a in addresses if a.strip()]
    exact = [str(n.network_address) for n in exact if n.version == 4 and n.prefixlen == 32]
    if len(exact) != 1:
        raise ValueError('Forwarding requires one unambiguous IPv4 /32 peer address')
    return exact[0]

def duration(body):
    minutes = body.get('minutes', 60)
    if type(minutes) is not int or not 1 <= minutes <= 10080:
        raise ValueError('Choose a duration from 1 minute to 7 days')
    return minutes * 60

def validate(body):
    protocol = body.get('protocol', 'tcp')
    if protocol not in ('tcp', 'udp', 'both'):
        raise ValueError('Protocol must be TCP, UDP or both')
    port = body.get('local_port')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Local port must be between 1 and 65535')
    key = body.get('peer', '')
    return key, peer_ip(key), port, protocol, duration(body)

def command(prefix, table, *args):
    run(prefix + ['iptables', '-w', '5', '-t', table, *args])

def ensure_chain(prefix, table, chain, parent):
    try:
        command(prefix, table, '-N', chain)
    except subprocess.CalledProcessError:
        pass
    try:
        command(prefix, table, '-C', parent, '-j', chain)
    except subprocess.CalledProcessError:
        command(prefix, table, '-I', parent, '1', '-j', chain)

def firewall():
    """Touch only dedicated chains. Host filter deadlines also stop existing flows."""
    metadata = inspect()
    networks = metadata['NetworkSettings']['Networks'].values()
    addresses = [n['IPAddress'] for n in networks if n.get('IPAddress')]
    if len(addresses) != 1:
        raise RuntimeError('Expected one Amnezia Docker bridge address')
    container_ip = str(ipaddress.IPv4Address(addresses[0]))
    route = json.loads(run(['ip', '-j', 'route', 'show', 'default']))[0]
    interface = route['dev']
    address_info = json.loads(run(['ip', '-j', '-4', 'addr', 'show', 'dev', interface]))[0]
    host_ip = next(a['local'] for a in address_info['addr_info'] if a['scope'] == 'global')
    host, vpn = [], ['docker', 'exec', CONTAINER]
    for prefix, table, chain, parent in (
        (host, 'filter', 'EHWGD_FORWARD', 'FORWARD'),
        (host, 'nat', 'EHWGD_NAT', 'PREROUTING'),
        (vpn, 'nat', 'EHWGD_DNAT', 'PREROUTING'),
        (vpn, 'nat', 'EHWGD_SNAT', 'POSTROUTING'),
        (vpn, 'filter', 'EHWGD_FORWARD', 'FORWARD')):
        ensure_chain(prefix, table, chain, parent)
    # Block the reserved range during reconstruction, including existing flows.
    guard = ['-m', 'conntrack', '--ctorigdst', host_ip, '--ctorigdstport', f'{PORT_MIN}:{PORT_MAX}', '-j', 'DROP']
    command(host, 'filter', '-I', 'FORWARD', '1', *guard)
    try:
        for prefix, table, chain in ((host, 'filter', 'EHWGD_FORWARD'), (host, 'nat', 'EHWGD_NAT'),
                                    (vpn, 'nat', 'EHWGD_DNAT'), (vpn, 'nat', 'EHWGD_SNAT'), (vpn, 'filter', 'EHWGD_FORWARD')):
            command(prefix, table, '-F', chain)
        with db() as connection:
            leases = [dict(row) for row in connection.execute('SELECT * FROM leases WHERE expires > ?', (time.time(),))]
        for lease in leases:
            expiry = dt.datetime.fromtimestamp(lease['expires'], dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            deadline = ['-m', 'time', '--datestop', expiry]
            for protocol in ('tcp', 'udp') if lease['protocol'] == 'both' else (lease['protocol'],):
                public, local = str(lease['public_port']), str(lease['local_port'])
                command(host, 'nat', '-A', 'EHWGD_NAT', '-i', interface, '-p', protocol, '--dport', public,
                        *deadline, '-j', 'DNAT', '--to-destination', f'{container_ip}:{public}')
                command(host, 'filter', '-A', 'EHWGD_FORWARD', '-p', protocol, '-m', 'conntrack',
                        '--ctorigdst', host_ip, '--ctorigdstport', public, *deadline, '-j', 'ACCEPT')
                command(vpn, 'nat', '-A', 'EHWGD_DNAT', '-p', protocol, '-d', container_ip, '--dport', public,
                        *deadline, '-j', 'DNAT', '--to-destination', f"{lease['ip']}:{local}")
                command(vpn, 'nat', '-A', 'EHWGD_SNAT', '-p', protocol, '-o', 'wg0', '-d', lease['ip'],
                        '--dport', local, *deadline, '-j', 'MASQUERADE')
                command(vpn, 'filter', '-A', 'EHWGD_FORWARD', '-p', protocol, '-d', lease['ip'], '--dport', local, '-j', 'ACCEPT')
                command(vpn, 'filter', '-A', 'EHWGD_FORWARD', '-p', protocol, '-s', lease['ip'], '--sport', local,
                        '-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT')
        command(host, 'filter', '-A', 'EHWGD_FORWARD', *guard)
    except Exception:
        # Leave the temporary guard in place: a failed rebuild must fail closed.
        raise
    else:
        command(host, 'filter', '-D', 'FORWARD', *guard)

def forget_connections(port):
    for protocol in ('tcp', 'udp'):
        try:
            run(['conntrack', '-D', '-p', protocol, '--orig-port-dst', str(port)])
        except subprocess.CalledProcessError:
            pass

def snapshot():
    now = time.time()
    metadata = inspect()
    epoch = metadata['Id'] + metadata['State']['StartedAt']
    devices = []
    with LOCK, db() as connection:
        for peer in peers():
            key = peer['key']
            up, down = map(int, peer.get('transfer', ['0', '0']))
            old = connection.execute('SELECT * FROM counters WHERE peer = ?', (key,)).fetchone()
            delta_up = delta_down = 0
            if old:
                delta_up = max(0, up - old['up']) if old['epoch'] == epoch and up >= old['up'] else up
                delta_down = max(0, down - old['down']) if old['epoch'] == epoch and down >= old['down'] else down
            total_up = (old['total_up'] if old else 0) + delta_up
            total_down = (old['total_down'] if old else 0) + delta_down
            seconds = max(1, now - old['time']) if old else 1
            handshake = int(peer.get('latest-handshakes', ['0'])[0])
            devices.append({'key': key, 'tunnel_ip': ', '.join(peer.get('allowed-ips', [])),
                            'endpoint': ' '.join(peer.get('endpoints', [])), 'handshake': handshake,
                            'active': handshake > 0 and now - handshake < 180,
                            'upload_speed': delta_up / seconds, 'download_speed': delta_down / seconds,
                            'total_upload': total_up, 'total_download': total_down})
            connection.execute('INSERT OR REPLACE INTO counters VALUES (?, ?, ?, ?, ?, ?, ?)',
                               (key, epoch, up, down, total_up, total_down, now))
        upload = sum(p['upload_speed'] for p in devices)
        download = sum(p['download_speed'] for p in devices)
        connection.execute('INSERT INTO samples VALUES (?, ?, ?)', (now, upload, download))
        connection.execute('DELETE FROM samples WHERE time < ?', (now - 7 * 86400,))
        history = [dict(row) for row in connection.execute('SELECT CAST(time / 60 AS INT) * 60 AS time, AVG(upload) AS upload, AVG(download) AS download FROM samples WHERE time > ? GROUP BY CAST(time / 60 AS INT) ORDER BY time', (now - 86400,))]
    return {'ok': True, 'time': now, 'peers': devices, 'history': history,
            'load': os.getloadavg(), 'public_ip': os.environ.get('EH_PUBLIC_IP', '')}

CACHE = {'ok': False, 'error': 'Waiting for the first sample', 'peers': [], 'history': []}
LAST_FIREWALL_ERROR = None

def worker():
    global CACHE, LAST_FIREWALL_ERROR
    last_namespace = None
    while True:
        try:
            CACHE = snapshot()
            metadata = inspect()
            identity = (metadata['Id'], metadata['State']['Pid'])
            with LOCK, db() as connection:
                configured = {p['key']: [address.strip() for address in p['tunnel_ip'].split(',')] for p in CACHE['peers']}
                invalid = [row for row in connection.execute('SELECT id, peer, ip, public_port, expires FROM leases')
                           if row['expires'] <= time.time() or row['ip'] + '/32' not in configured.get(row['peer'], [])]
                expired = invalid
                connection.executemany('DELETE FROM leases WHERE id = ?', [(row['id'],) for row in invalid])
            if expired or identity != last_namespace or LAST_FIREWALL_ERROR:
                with LOCK:
                    firewall()
                    for lease in expired:
                        forget_connections(lease['public_port'])
                last_namespace = identity
                LAST_FIREWALL_ERROR = None
        except Exception as error:
            CACHE = {'ok': False, 'error': str(error), 'peers': [], 'history': []}
            LAST_FIREWALL_ERROR = str(error)
        time.sleep(5)

@app.before_request
def auth():
    if not TOKEN or not hmac.compare_digest(request.headers.get('Authorization', ''), 'Bearer ' + TOKEN):
        return jsonify(status=False, message='Unauthorized'), 401

@app.errorhandler(ValueError)
def invalid(error):
    return jsonify(status=False, message=str(error)), 400

@app.errorhandler(RuntimeError)
@app.errorhandler(subprocess.SubprocessError)
def unavailable(error):
    app.logger.error('Node operation failed: %s', error)
    return jsonify(status=False, message='Node operation failed; check node logs'), 503

@app.get('/stats')
def stats():
    return jsonify(CACHE)

@app.route('/leases', methods=['GET', 'POST'])
def leases():
    with LOCK, db() as connection:
        if request.method == 'POST':
            key, ip, local, protocol, seconds = validate(request.get_json() or {})
            used = {row[0] for row in connection.execute('SELECT public_port FROM leases')}
            listeners = run(['ss', '-H', '-lntu'])
            used.update(int(match) for match in __import__('re').findall(r':(\d+)\s', listeners))
            # Also avoid Docker-published ports, which need not appear in ss.
            bindings = run(['docker', 'ps', '--format', '{{.Ports}}'])
            used.update(int(match) for match in __import__('re').findall(r':(\d+)->', bindings))
            choices = [port for port in range(PORT_MIN, PORT_MAX + 1) if port not in used]
            if not choices:
                raise ValueError('All 21 forwarding ports on this server are allocated')
            lease_id = secrets.token_hex(16)
            connection.execute('INSERT INTO leases VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                               (lease_id, key, ip, local, secrets.choice(choices), protocol,
                                time.time() + seconds, str((request.get_json() or {}).get('label', ''))[:100]))
            connection.commit()
            try:
                firewall()
            except Exception:
                connection.execute('DELETE FROM leases WHERE id = ?', (lease_id,))
                connection.commit()
                raise
        result = [dict(row) for row in connection.execute('SELECT * FROM leases WHERE expires > ? ORDER BY expires', (time.time(),))]
    return jsonify(status=True, data=result)

@app.post('/leases/<lease_id>/<action>')
def change_lease(lease_id, action):
    with LOCK, db() as connection:
        lease = connection.execute('SELECT * FROM leases WHERE id = ? AND expires > ?', (lease_id, time.time())).fetchone()
        if not lease:
            raise ValueError('Lease does not exist or has expired')
        if action == 'close':
            connection.execute('DELETE FROM leases WHERE id = ?', (lease_id,))
        elif action == 'renew':
            if peer_ip(lease['peer']) != lease['ip']:
                raise ValueError('Peer address changed; close this lease and create a new one')
            connection.execute('UPDATE leases SET expires = ? WHERE id = ?', (time.time() + duration(request.get_json() or {}), lease_id))
        else:
            raise ValueError('Unknown action')
        connection.commit()
        firewall()
        if action == 'close':
            forget_connections(lease['public_port'])
    return jsonify(status=True)

@app.route('/proxy/<path:path>', methods=['GET', 'POST', 'DELETE', 'PUT', 'PATCH'])
def proxy(path):
    connection = http.client.HTTPConnection('localhost', 10086, timeout=30)
    connection.sock = connect_backend()
    suffix = '?' + request.query_string.decode() if request.query_string else ''
    try:
        headers = {'X-EH-Node-Token': TOKEN, 'Content-Type': request.headers.get('Content-Type', 'application/json')}
        connection.request(request.method, '/' + path + suffix, body=request.get_data(), headers=headers)
        response = connection.getresponse()
        return response.read(), response.status, {'Content-Type': response.getheader('Content-Type', 'application/octet-stream'),
                                                 'Content-Disposition': response.getheader('Content-Disposition', 'inline')}
    finally:
        connection.close()

def start():
    if len(TOKEN) < 32:
        raise RuntimeError('Set a strong EH_NODE_TOKEN before starting')
    db().close()
    threading.Thread(target=worker, daemon=True).start()
