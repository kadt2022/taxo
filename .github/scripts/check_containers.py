"""Check the real Compose stack, including the nginx proxy and persisted scan."""

import json
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


def request(url, data=None):
    body = None if data is None else json.dumps(data).encode('utf-8')
    req = Request(url, data=body, headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=60) as response:
        return response.status, response.read().decode('utf-8')


def wait_for_health(url):
    for _ in range(30):
        try:
            status, body = request(url)
            if status == 200 and json.loads(body).get('status') == 'ok':
                return
        except (URLError, OSError, TimeoutError, ValueError):
            pass
        time.sleep(2)
    raise RuntimeError('Application health did not become ready: ' + url)


def main():
    portal = 'http://127.0.0.1:18080'
    wait_for_health('http://127.0.0.1:18000/api/health')
    wait_for_health(portal + '/api/health')
    status, html = request(portal)
    assert status == 200 and '<div id="root">' in html, html[:200]
    status, body = request(portal + '/api/projects', {'name': 'Taxo CI', 'path': '/taxo-source'})
    assert status == 201, body
    project_id = json.loads(body)['id']
    status, body = request(portal + f'/api/projects/{project_id}/scans', {})
    assert status == 201, body
    scan = json.loads(body)
    assert scan['facts'], 'Expected a nonempty repository inventory.'
    status, body = request(portal + f'/api/projects/{project_id}/scans')
    assert status == 200, body
    assert any(item['id'] == scan['id'] for item in json.loads(body)), body
    print('Compose smoke: portal, nginx proxy, API, scan and persisted history passed.')


if __name__ == '__main__':
    main()
