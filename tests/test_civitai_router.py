import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _DummyAsyncClient:
    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({
            'url': url,
            'params': params or {},
            'headers': headers or {},
            'timeout': timeout,
        })
        return _DummyResponse({
            'items': [
                {
                    'id': 123,
                    'name': 'SDXL Test Model',
                    'type': 'Checkpoint',
                    'creator': {'username': 'tester'},
                    'stats': {'downloadCount': 42},
                    'tags': ['sdxl'],
                    'modelVersions': [
                        {
                            'id': 1,
                            'name': 'v1',
                            'baseModel': 'SDXL',
                            'images': [{'url': 'https://example.com/thumb.jpg'}],
                        }
                    ],
                }
            ],
            'metadata': {'nextCursor': None},
        })


class CivitaiRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_query_search_omits_page_param_for_civitai(self):
        dummy_client = _DummyAsyncClient()
        with patch('backend.routers.civitai.httpx.AsyncClient', return_value=dummy_client):
            response = self.client.get('/api/civitai/search', params={'q': 'sdxl', 'limit': 3})

        self.assertEqual(response.status_code, 200, msg=response.text)
        payload = response.json()
        self.assertEqual(len(payload.get('models', [])), 1)
        self.assertEqual(payload['models'][0]['thumbnail'], 'https://example.com/thumb.jpg')
        self.assertEqual(len(dummy_client.calls), 1)
        self.assertNotIn('page', dummy_client.calls[0]['params'])
        self.assertEqual(dummy_client.calls[0]['params'].get('query'), 'sdxl')


if __name__ == '__main__':
    unittest.main()
