import importlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from werkzeug.security import generate_password_hash

os.environ.update(EH_NODE_TOKEN='n' * 64, EH_VPN1_TOKEN='a' * 64, EH_VPN2_TOKEN='b' * 64,
                  EH_SESSION_SECRET='s' * 64, EH_ADMIN_PASSWORD_HASH=generate_password_hash('test-password-only'))
import gateway
import node
import persist_amnezia

class FakeResponse:
    status_code = 200
    headers = {'Content-Type': 'application/json'}
    content = b'{"status":true,"data":[]}'
    def json(self):
        return {'ok': True, 'peers': [], 'history': []}
    def raise_for_status(self):
        pass

class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        gateway.ACCOUNT_FILE = Path(self.temp.name) / 'account.json'
        gateway.FAILURES.clear()
        self.client = gateway.app.test_client()
        gateway.app.testing = True
    def tearDown(self):
        self.temp.cleanup()
    def login(self):
        return self.client.post('/api/authenticate', json={'username':'admin','password':'test-password-only'})
    def test_all_private_operations_require_login(self):
        for path in ['/api/eh/overview', '/api/getWireguardConfigurations', '/api/sharePeer/get', '/api/eh/leases', '/fileDownload/test', '/client/']:
            self.assertEqual(self.client.get(path).status_code, 401, path)
    def test_invalid_login_and_rate_limit(self):
        for _ in range(10):
            response = self.client.post('/api/authenticate', json={'username':'admin','password':'wrong'})
            self.assertFalse(response.json['status'])
        self.assertEqual(self.login().status_code, 429)
    def test_selector_routes_operations_to_correct_node(self):
        self.assertTrue(self.login().json['status'])
        with patch.object(gateway, 'upstream', return_value=FakeResponse()) as call:
            self.client.get('/api/getWireguardConfigurations', headers={'X-EH-Request':'1','X-EH-Node':'vpn1'})
            self.assertEqual(call.call_args.args[0], 'vpn1')
            self.client.get('/api/getWireguardConfigurations', headers={'X-EH-Request':'1','X-EH-Node':'vpn2'})
            self.assertEqual(call.call_args.args[0], 'vpn2')
    def test_unknown_node_and_csrf_rejected(self):
        self.login()
        self.assertEqual(self.client.get('/api/eh/leases', headers={'X-EH-Request':'1','X-EH-Node':'outside'}).status_code, 400)
        self.assertEqual(self.client.post('/api/eh/leases', headers={'Origin':'https://outside.example'}, json={}).status_code, 403)
        self.assertEqual(self.client.get('/api/deletePeer').status_code, 403)
    def test_binary_download_keeps_selected_node(self):
        self.login()
        with patch.object(gateway, 'upstream', return_value=FakeResponse()) as call:
            response = self.client.get('/api/downloadWireguardConfigurationBackup?_eh_node=vpn1')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(call.call_args.args[0], 'vpn1')
    def test_logout_clears_shared_login(self):
        self.login()
        self.client.get('/api/signout', headers={'X-EH-Request':'1'})
        self.assertFalse(self.client.get('/api/validateAuthentication').json['status'])
    def test_ui_stays_on_vpn2(self):
        response = FakeResponse()
        response.content = b'<html><head></head></html>'
        with patch.object(gateway, 'upstream', return_value=response) as call:
            result = self.client.get('/', headers={'X-EH-Node':'vpn1'})
            self.assertEqual(call.call_args.args[0], 'vpn2')
            self.assertIn(b'window.EH_GATEWAY=true', result.data)
    def test_central_password_change_invalidates_other_sessions(self):
        self.login()
        other = gateway.app.test_client()
        other.post('/api/authenticate',json={'username':'admin','password':'test-password-only'})
        body = {'section':'Account','key':'password','value':{'currentPassword':'test-password-only','newPassword':'new-test-password','repeatNewPassword':'new-test-password'}}
        response = self.client.post('/api/updateDashboardConfigurationItem',json=body,headers={'X-EH-Request':'1'})
        self.assertTrue(response.json['status'])
        self.assertFalse(other.get('/api/validateAuthentication').json['status'])
        self.assertTrue(self.client.get('/api/validateAuthentication').json['status'])
        self.assertTrue(gateway.check_password_hash(gateway.account()['password_hash'],'new-test-password'))
    def test_network_settings_cannot_expose_backend(self):
        self.login()
        result = self.client.post('/api/updateDashboardConfigurationItem',json={'section':'Server','key':'app_ip','value':'0.0.0.0'},headers={'X-EH-Request':'1'})
        self.assertFalse(result.json['status'])

class MigrationTests(unittest.TestCase):
    def test_preserves_image_ports_command_and_privileges(self):
        original = {'Image':'sha256:pinned-original', 'Config':{'Image':'amnezia:latest','Cmd':['/opt/amnezia/start.sh'],'Env':['EXAMPLE=1']},
                    'HostConfig':{'NetworkMode':'bridge','Binds':['/lib/modules:/lib/modules'],'PortBindings':{'33805/udp':[{'HostPort':'33805'}]},'CapAdd':['NET_ADMIN']}}
        payload = persist_amnezia.create_payload(original, Path('/safe/vpnconfig'))
        self.assertEqual(payload['Image'],'sha256:pinned-original')
        self.assertEqual(payload['Cmd'],original['Config']['Cmd'])
        self.assertEqual(payload['HostConfig']['PortBindings'],original['HostConfig']['PortBindings'])
        self.assertEqual(payload['HostConfig']['CapAdd'],['NET_ADMIN'])
        self.assertIn('/safe/vpnconfig:/opt/amnezia/wireguard',payload['HostConfig']['Binds'])
        self.assertFalse(any('/opt/amnezia/start.sh' in bind for bind in payload['HostConfig']['Binds']))
        self.assertEqual(original['HostConfig']['Binds'],['/lib/modules:/lib/modules'])
    def test_refuses_unverified_network_before_migration(self):
        with self.assertRaises(ValueError):
            persist_amnezia.create_payload({'Config':{},'Image':'test','HostConfig':{'NetworkMode':'host'}},Path('/test'))

class NodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        node.STATE = Path(self.temp.name)
        node.app.testing = True
        self.client = node.app.test_client()
        self.headers = {'Authorization':'Bearer ' + node.TOKEN}
        self.peer = patch.object(node, 'peer_ip', return_value='10.8.1.2')
        self.firewall = patch.object(node, 'firewall')
        self.run = patch.object(node, 'run', return_value='')
        self.peer.start(); self.firewall.start(); self.run.start()
    def tearDown(self):
        self.peer.stop(); self.firewall.stop(); self.run.stop(); self.temp.cleanup()
    def allocate(self, **extra):
        body = dict(peer='peer-one', local_port=25565, protocol='tcp', minutes=60)
        body.update(extra)
        return self.client.post('/leases', json=body, headers=self.headers)
    def test_token_required(self):
        self.assertEqual(self.client.get('/stats').status_code, 401)
        self.assertEqual(self.client.post('/leases', json={}).status_code, 401)
    def test_port_range_uniqueness_and_exhaustion(self):
        ports = []
        for _ in range(21):
            response = self.allocate()
            self.assertEqual(response.status_code, 200)
            ports.append(response.json['data'][-1]['public_port'])
        with node.db() as connection:
            actual = {row[0] for row in connection.execute('SELECT public_port FROM leases')}
        self.assertEqual(actual, set(range(45100,45121)))
        self.assertEqual(self.allocate().status_code, 400)
    def test_invalid_port_protocol_and_time(self):
        for extra in ({'local_port':0}, {'local_port':65536}, {'local_port':True}, {'protocol':'shell'}, {'minutes':0}, {'minutes':10081}):
            self.assertEqual(self.allocate(**extra).status_code, 400)
    def test_renew_and_close(self):
        lease = self.allocate().json['data'][0]
        response = self.client.post(f"/leases/{lease['id']}/renew", json={'minutes':1440}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        with node.db() as connection:
            row = connection.execute('SELECT expires FROM leases').fetchone()
            self.assertGreater(row[0], time.time()+86300)
        with patch.object(node, 'forget_connections') as forget:
            self.assertEqual(self.client.post(f"/leases/{lease['id']}/close", json={}, headers=self.headers).status_code, 200)
            forget.assert_called_once_with(lease['public_port'])
        self.assertEqual(self.client.get('/leases', headers=self.headers).json['data'], [])
    def test_failed_firewall_does_not_leave_allocated_lease(self):
        with patch.object(node, 'firewall', side_effect=RuntimeError('firewall failed')):
            self.assertEqual(self.allocate().status_code, 503)
        self.assertEqual(self.client.get('/leases', headers=self.headers).json['data'], [])
    def test_expired_lease_is_not_listed_or_renewable(self):
        lease = self.allocate().json['data'][0]
        with node.db() as connection:
            connection.execute('UPDATE leases SET expires = ?', (time.time()-1,))
        self.assertEqual(self.client.get('/leases', headers=self.headers).json['data'], [])
        self.assertEqual(self.client.post(f"/leases/{lease['id']}/renew", json={'minutes':60}, headers=self.headers).status_code, 400)

if __name__ == '__main__':
    unittest.main()
