"""Single authenticated dashboard on VPN2; node credentials never reach the browser."""
import datetime as dt
import hmac
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlparse
import requests
from flask import Flask, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('EH_SESSION_SECRET', '')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                  PERMANENT_SESSION_LIFETIME=dt.timedelta(hours=8), MAX_CONTENT_LENGTH=4 * 1024 * 1024)
NODES = {
    'vpn1': {'name': 'Oracle VPN1', 'url': 'http://127.0.0.1:18791', 'token': os.environ.get('EH_VPN1_TOKEN', '')},
    'vpn2': {'name': 'Oracle VPN2', 'url': 'http://127.0.0.1:8791', 'token': os.environ.get('EH_VPN2_TOKEN', '')},
}
FAILURES = {}
LOCK = threading.Lock()
ACCOUNT_FILE = Path(os.environ.get('EH_ACCOUNT_FILE', '/data/account.json'))
PRELOGIN = {'/api/authenticate', '/api/validateAuthentication', '/api/locale', '/api/getDashboardTheme',
            '/api/getDashboardVersion', '/api/isTotpEnabled', '/api/requireAuthentication'}

def result(data=None, status=True, message=None, code=200):
    return jsonify(status=status, data=data, message=message), code

def account():
    if ACCOUNT_FILE.exists():
        return json.loads(ACCOUNT_FILE.read_text())
    return {'username':os.environ.get('EH_ADMIN_USERNAME','admin'),
            'password_hash':os.environ['EH_ADMIN_PASSWORD_HASH'], 'version':0}

def save_account(value):
    ACCOUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = ACCOUNT_FILE.with_suffix('.tmp')
    temporary.write_text(json.dumps(value))
    temporary.chmod(0o600)
    temporary.replace(ACCOUNT_FILE)

def node_id():
    value = request.headers.get('X-EH-Node') or request.args.get('_eh_node', 'vpn2')
    if value not in NODES:
        raise ValueError('Unknown server')
    return value

def upstream(node, path, method='GET', body=None, content_type='application/json'):
    info = NODES[node]
    return requests.request(method, info['url'] + path, data=body,
                            headers={'Authorization': 'Bearer ' + info['token'], 'Content-Type': content_type},
                            timeout=(5, 30), allow_redirects=False)

@app.before_request
def gate():
    # The shell assets contain no private data; all APIs and downloads are gated.
    if request.path.startswith(('/api/', '/fileDownload', '/client')):
        if session.get('admin') and session.get('account_version') != account()['version']:
            session.clear()
        if request.path not in PRELOGIN and not session.get('admin'):
            return result(status=False, message='Please sign in', code=401)
        origin = request.headers.get('Origin')
        if origin and origin != request.host_url.rstrip('/'):
            return result(status=False, message='Invalid origin', code=403)
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            return result(status=False, message='Cross-site request blocked', code=403)
        download = request.method == 'GET' and request.path == '/api/downloadWireguardConfigurationBackup'
        if request.path.startswith('/api/') and request.path not in PRELOGIN and not download and request.headers.get('X-EH-Request') != '1':
            return result(status=False, message='Missing request protection', code=403)

@app.errorhandler(ValueError)
def bad_request(error):
    return result(status=False, message=str(error), code=400)

@app.errorhandler(requests.RequestException)
def unavailable(error):
    app.logger.warning('A private node is unavailable: %s', type(error).__name__)
    return result(status=False, message='VPN server unavailable; check the private link and node service', code=503)

@app.post('/api/authenticate')
def login():
    body = request.get_json(silent=True) or {}
    address = request.remote_addr
    now = time.monotonic()
    with LOCK:
        attempts = [t for t in FAILURES.get(address, []) if now - t < 300]
        if len(attempts) >= 10:
            return result(status=False, message='Too many attempts; try again in five minutes', code=429)
    username = str(body.get('username', ''))
    password = str(body.get('password', ''))
    credentials = account()
    valid = check_password_hash(credentials['password_hash'], password)
    valid = valid and hmac.compare_digest(username, credentials['username'])
    if not valid:
        with LOCK:
            FAILURES[address] = attempts + [now]
        return result(status=False, message='Incorrect username or password')
    session.clear()
    session['admin'] = True
    session['account_version'] = credentials['version']
    session.permanent = True
    with LOCK:
        FAILURES.pop(address, None)
    return result()

@app.get('/api/validateAuthentication')
def validate_auth():
    return result(status=bool(session.get('admin')))

@app.get('/api/signout')
def logout():
    session.clear()
    return result()

@app.get('/api/isTotpEnabled')
def totp():
    return result(False)

@app.get('/api/requireAuthentication')
def require_auth():
    return result(True)

@app.post('/api/updateDashboardConfigurationItem')
def settings():
    body = request.get_json(silent=True) or {}
    if body.get('section') == 'Account':
        with LOCK:
            value = account()
            if body.get('key') == 'password':
                change = body.get('value', {})
                if not isinstance(change, dict) or not check_password_hash(value['password_hash'], str(change.get('currentPassword',''))):
                    return result(status=False, message='Current password is incorrect')
                password = str(change.get('newPassword',''))
                if len(password) < 8 or password != change.get('repeatNewPassword'):
                    return result(status=False, message='Use at least 8 characters and matching confirmation')
                value['password_hash'] = generate_password_hash(password)
            elif body.get('key') == 'username':
                name = str(body.get('value','')).strip()
                if not 1 <= len(name) <= 64:
                    return result(status=False, message='Use a username between 1 and 64 characters')
                value['username'] = name
            else:
                return result(status=False, message='This setting belongs to the central gateway')
            value['version'] += 1
            save_account(value)
            session['account_version'] = value['version']
        return result()
    if body.get('section') == 'Server' and body.get('key') in {'app_ip','app_port','app_prefix','wg_conf_path','awg_conf_path','auth_req'}:
        return result(status=False, message='Private network and configuration paths are managed by the deployment')
    response = upstream(node_id(), '/proxy/api/updateDashboardConfigurationItem', 'POST', request.get_data())
    return response.content, response.status_code, {'Content-Type':'application/json'}

@app.get('/api/getDashboardConfiguration')
def configuration():
    response = upstream(node_id(), '/proxy/api/getDashboardConfiguration')
    if response.status_code != 200:
        return response.content, response.status_code, {'Content-Type':'application/json'}
    data = response.json()
    if data.get('status'):
        data['data']['Account'] = {'username':account()['username'], 'password':'', 'enable_totp':False}
    return jsonify(data)

@app.get('/api/getDashboardTheme')
def theme():
    return result('dark')

@app.get('/api/getDashboardVersion')
def version():
    return result('EH · WGDashboard v4.3.3')

@app.get('/api/eh/overview')
def overview():
    data = []
    for identity, info in NODES.items():
        try:
            response = upstream(identity, '/stats')
            response.raise_for_status()
            value = response.json()
        except (requests.RequestException, ValueError):
            value = {'ok': False, 'error': 'Private node unavailable', 'peers': [], 'history': []}
        data.append(dict(value, id=identity, name=info['name']))
    return result(data)

@app.route('/api/eh/leases', methods=['GET', 'POST'])
@app.post('/api/eh/leases/<lease_id>/<action>')
def leases(lease_id=None, action=None):
    path = '/leases' + (f'/{lease_id}/{action}' if lease_id else '')
    response = upstream(node_id(), path, request.method, request.get_data())
    return response.content, response.status_code, {'Content-Type': 'application/json'}

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def proxy(path):
    # Only VPN2 serves the UI. Server selection affects API operations, not assets.
    identity = node_id() if path.startswith(('api/', 'fileDownload')) else 'vpn2'
    query = '?' + request.query_string.decode() if request.query_string else ''
    target = '/proxy/' + (path or 'index.html') + query
    response = upstream(identity, target, request.method, request.get_data(), request.headers.get('Content-Type', 'application/json'))
    content = response.content
    if path in ('', 'index.html') and response.status_code == 200:
        content = content.replace(b'<head>', b'<head><script>window.EH_GATEWAY=true;</script>', 1)
    headers = {'Content-Type': response.headers.get('Content-Type', 'application/octet-stream'), 'Cache-Control': 'no-store',
               'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin', 'X-Frame-Options': 'DENY'}
    if 'Content-Disposition' in response.headers:
        headers['Content-Disposition'] = response.headers['Content-Disposition']
    # Backend sessions are transport-only and must never overwrite gateway login.
    return content, response.status_code, headers

def check_config():
    if len(app.secret_key) < 32 or not os.environ.get('EH_ADMIN_PASSWORD_HASH'):
        raise RuntimeError('Configure gateway login and session secret before starting')
    if any(len(value['token']) < 32 for value in NODES.values()):
        raise RuntimeError('Configure both private node tokens before starting')

if __name__ == '__main__':
    check_config()
    app.run(host='127.0.0.1', port=8787)
