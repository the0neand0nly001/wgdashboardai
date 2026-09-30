"""Local UI preview using labelled example stats and a disposable backend.

Never run on an Oracle host: forwarding is intentionally mocked in this file.
"""
import os
import threading
import time
import requests
from werkzeug.security import generate_password_hash
os.environ.update(EH_NODE_TOKEN='preview-node-token-' + 'p'*48,
                  EH_VPN1_TOKEN='preview-node-token-' + 'p'*48,
                  EH_VPN2_TOKEN='preview-node-token-' + 'p'*48,
                  EH_SESSION_SECRET='preview-session-' + 's'*48,
                  EH_ADMIN_PASSWORD_HASH=generate_password_hash('preview-only'),
                  EH_AMNEZIA_CONTAINER='eh-wgd-smoke', EH_STATE='/tmp/eh-preview')
import gateway
import node
node.firewall = lambda: None
node.forget_connections = lambda port: None
node.peer_ip = lambda key: '10.8.1.2'
node.run = lambda *args, **kwargs: ''  # No host commands in the simulation.
now = time.time()
node.CACHE = {'ok': True, 'time':now,'public_ip':'192.0.2.10', 'load':[.12,.09,.08],
              'peers':[{'key':'example-device-key', 'tunnel_ip':'10.8.1.2/32','endpoint':'198.51.100.20:50000',
                        'handshake':int(now)-20,'active':True,'upload_speed':125000,'download_speed':1250000,
                        'total_upload':1500000000,'total_download':12000000000}],
              'history':[{'time':now-60*(120-i),'upload':100000+(i%12)*15000,'download':700000+(i%17)*60000} for i in range(121)]}
def preview_upstream(identity, path, method='GET', body=None, content_type='application/json'):
    if path.startswith('/proxy/'):
        return requests.request(method, 'http://eh-wgd-preview-backend:10086/' + path.removeprefix('/proxy/'),
                                data=body, headers={'X-EH-Node-Token':node.TOKEN,'Content-Type':content_type}, timeout=10)
    with node.app.test_client() as client:
        response = client.open(path, method=method, data=body,
                               headers={'Authorization':'Bearer '+node.TOKEN,'Content-Type':content_type})
        result = requests.Response()
        result.status_code = response.status_code
        result._content = response.data
        result.headers['Content-Type'] = response.content_type
        return result
gateway.upstream = preview_upstream
@gateway.app.get('/preview-mobile')
def mobile_preview():
    # The iframe renders the real application at a phone viewport, without
    # relying on browser-specific device emulation. This route exists only here.
    return '<!doctype html><html><head><title>Endless VPN mobile preview</title></head><body style="margin:0;background:#080c10;color:#9aa9b7;font:14px sans-serif"><p style="margin:16px">Mobile layout check · 390 × 844</p><iframe title="Endless VPN at phone size" src="/#/overview" style="display:block;border:1px solid #26303a;width:390px;height:844px;margin:16px"></iframe></body></html>'
@gateway.app.after_request
def mark_preview(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    if response.content_type.startswith('text/html'):
        response.set_data(response.get_data().replace(b'<head>',b'<head><script>window.EH_PREVIEW=true;</script>',1))
    return response
gateway.app.run(host='0.0.0.0',port=8787,threaded=True)
