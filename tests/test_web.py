"""Integration checks using real HTTP and isolated temporary SQLite databases."""
import os
import socket
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import requests
import uvicorn

_temp = tempfile.TemporaryDirectory()
os.environ['F1VE_DATA_DIR'] = _temp.name
import web_server as web


class WebIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sock = socket.socket()
        cls.sock.bind(('127.0.0.1', 0))
        cls.base = f'http://127.0.0.1:{cls.sock.getsockname()[1]}'
        cls.server = uvicorn.Server(uvicorn.Config(web.app, log_level='error'))
        cls.thread = threading.Thread(target=cls.server.run, kwargs={'sockets': [cls.sock]}, daemon=True)
        cls.thread.start()
        for _ in range(100):
            if cls.server.started:
                break
            time.sleep(.05)
        assert cls.server.started
        cls.users = []
        for index in range(3):
            data = {'nume': f'Test {index}', 'email': f'web{index}@example.com', 'parola': 'test-password-123', 'facultate': 'Test'}
            response = requests.post(cls.base + '/v1/users/register', json=data, timeout=10)
            assert response.status_code == 201, response.text
            response = requests.post(cls.base + '/v1/users/login', json=data, timeout=10)
            assert response.status_code == 200, response.text
            cls.users.append({'Authorization': 'Bearer ' + response.json()['access_token']})

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=10)
        cls.sock.close()
        _temp.cleanup()

    def call(self, method, path, user=0, data=None, headers=None):
        return requests.request(method, self.base + path, json=data,
                                headers={**(self.users[user] if user is not None else {}), **(headers or {})}, timeout=20)

    def test_01_health_and_static(self):
        self.assertEqual(self.call('GET', '/api/status', None).json()['engine'], 'LIGHTDARK.py')
        self.assertIn('F1VE DR1VE', self.call('GET', '/', None).text)
        self.assertEqual(self.call('GET', '/api/routes', None).status_code, 401)

    def test_02_schedule_ownership_and_validation(self):
        data = {'title': 'Web', 'location': 'Iași', 'day': 'Luni', 'time': '09:00'}
        self.assertEqual(self.call('POST', '/api/schedule', data=data).status_code, 201)
        lesson = self.call('GET', '/api/schedule').json()[0]
        self.assertEqual(self.call('GET', '/api/schedule', 1).json(), [])
        self.call('DELETE', f'/api/schedule/{lesson["id"]}', 1)
        self.assertEqual(len(self.call('GET', '/api/schedule').json()), 1)
        self.call('DELETE', f'/api/schedule/{lesson["id"]}')
        self.assertEqual(self.call('GET', '/api/schedule').json(), [])
        self.assertEqual(self.call('POST', '/api/schedule', data={**data, 'time': '99:00'}).status_code, 422)

    def test_03_ride_last_seat_and_cancellation(self):
        data = {'origin': 'Palas', 'destination': 'UAIC', 'date': '2099-01-01', 'time': '09:00', 'seats': 1}
        self.assertEqual(self.call('POST', '/api/rides', data=data).status_code, 201)
        ride = self.call('GET', '/api/rides').json()[0]
        path = f'/api/rides/{ride["id"]}'
        self.assertTrue(ride['mine'])
        self.assertEqual(self.call('POST', path + '/reservation').status_code, 409)
        self.assertEqual(self.call('DELETE', path, 1).status_code, 404)
        with ThreadPoolExecutor(2) as pool:
            responses = list(pool.map(lambda index: (index, self.call('POST', path + '/reservation', index)), [1, 2]))
        self.assertEqual(sorted(r.status_code for _, r in responses), [200, 409])
        winner = next(index for index, response in responses if response.status_code == 200)
        self.assertEqual(self.call('GET', '/api/rides', winner).json()[0]['seats'], 0)
        self.assertTrue(self.call('GET', '/api/rides', winner).json()[0]['booked'])
        self.assertEqual(self.call('POST', path + '/reservation', winner).status_code, 409)
        self.call('DELETE', path + '/reservation', winner)
        self.call('DELETE', path + '/reservation', winner)
        self.assertEqual(self.call('GET', '/api/rides').json()[0]['seats'], 1)
        self.call('DELETE', path)
        self.assertEqual(self.call('GET', '/api/rides').json(), [])

    def test_04_engine_history_and_failure(self):
        route = {'distance': 3500, 'duration': 480, 'geometry': {'coordinates': [[27.58, 47.15], [27.57, 47.17]]},
                 'legs': [{'steps': [{'name': 'Independenței', 'distance': 3500, 'maneuver': {'type': 'depart'}}]}]}
        data = {'origin': 'Palas', 'destination': 'UAIC', 'time': '09:00'}
        with patch.object(web.core, 'coordonate', return_value=(27.58, 47.15)) as geocode, patch.object(web.core, 'calculeaza_rute', return_value=[route]) as engine:
            result = self.call('POST', '/api/routes', data=data)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(geocode.call_count, 2)
            engine.assert_called_once()
            option = result.json()['options'][0]
            self.assertEqual(option['duration'], 8)
            self.assertEqual(option['arrival'], '09:08')
            self.assertEqual(option['traffic'], 'Date insuficiente')
        route_id = result.json()['id']
        self.assertEqual(len(self.call('GET', '/api/routes').json()), 1)
        self.assertEqual(self.call('GET', '/api/routes', 1).json(), [])
        self.assertEqual(self.call('DELETE', f'/api/routes/{route_id}', 1).status_code, 404)
        self.call('DELETE', f'/api/routes/{route_id}')
        with patch.object(web.core, 'coordonate', side_effect=requests.Timeout):
            self.assertEqual(self.call('POST', '/api/routes', data=data).status_code, 502)
        self.assertEqual(self.call('GET', '/api/routes').json(), [])

    def test_05_origin_guard_and_bad_login(self):
        response = self.call('POST', '/v1/users/login', None, {'email': 'web0@example.com', 'parola': 'wrong'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.call('POST', '/api/schedule', data={}, headers={'Origin': 'https://other.example'}).status_code, 403)
        self.assertEqual(self.call('GET', '/api/schedule').headers.get('Cache-Control'), 'no-store')


if __name__ == '__main__':
    unittest.main(verbosity=2)
