"""Run the built image on an ephemeral local port; compare every served UI asset."""
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from check_integration import ROOT, checks

docker = sys.argv[1]
name = f'blinkspace-integration-check-{int(time.time())}'
started = time.monotonic()
def run(*args):
    return subprocess.check_output([docker, *args], text=True).strip()
try:
    run('run', '-d', '--name', name, '-p', '127.0.0.1::8000', 'blinkspace:integration')
    port = json.loads(run('inspect', name))[0]['NetworkSettings']['Ports']['8000/tcp'][0]['HostPort']
    url = f'http://127.0.0.1:{port}'
    for _ in range(45):
        try:
            health = json.load(urllib.request.urlopen(url + '/api/health', timeout=2))
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError('Docker health endpoint did not become ready')
    ready_s = time.monotonic() - started
    assert health['status'] == 'ok'
    targets = json.load(urllib.request.urlopen(url + '/api/targets'))['targets']
    assert len(targets) == 5 and all(t.get('ready_sequence_id') for t in targets)
    for target in targets:
        data = json.load(urllib.request.urlopen(url + '/api/sequences/' + target['ready_sequence_id']))
        assert data
        body = json.dumps({'message': 'What am I seeing?', 'context': {'target': {'id': target['id']}}}).encode()
        response = json.load(urllib.request.urlopen(urllib.request.Request(url + '/api/assistant/knowledge', body, {'Content-Type': 'application/json'})))
        assert response['sources'][0]['id'] == 'target:' + target['id']
    status = json.load(urllib.request.urlopen(url + '/api/assistant/status'))
    assert status == {'enabled': False, 'provider': None}
    files = 0
    for path in (ROOT / 'frontend/dist').rglob('*'):
        if not path.is_file(): continue
        remote = urllib.request.urlopen(url + '/' + path.relative_to(ROOT / 'frontend/dist').as_posix()).read()
        assert hashlib.sha256(remote).digest() == hashlib.sha256(path.read_bytes()).digest(), str(path)
        files += 1
    headers = urllib.request.urlopen(url).headers
    assert "connect-src 'self'" in headers['Content-Security-Policy']
    assert run('exec', name, 'id', '-u') == '1000'
    run('exec', name, 'python', '/app/docker/verify_seed.py', '/app/seed-data')
    # Verify lazy imports inside the lean image; the inactive upstream services are not required.
    run('exec', name, 'python', '-c', 'from blinkspace.assistant_qfit import Knowledge; assert Knowledge().search("SPHEREx")["hits"]')
    scan = "from pathlib import Path; import re; p=re.compile(rb'(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{28,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)'); found=[str(f) for f in Path('/app').rglob('*') if f.is_file() and p.search(f.read_bytes())]; assert not found, found; print('clean')"
    assert run('exec', name, 'python', '-c', scan) == 'clean'
    checks(url)
    info = json.loads(run('image', 'inspect', 'blinkspace:integration'))[0]
    result = {'image_id': info['Id'], 'image_bytes': info['Size'], 'ready_seconds': round(ready_s, 2), 'uid': 1000,
              'ready_targets': 5, 'source_card_targets': 5, 'http_assets_byte_verified': files, 'assistant_default': status,
              'csp_same_origin': True, 'seed_verified': True, 'image_secret_scan': 'clean',
              'qfit_lazy_import_and_retrieval': 'passed', 'scope': 'HTTP/API and file checks, not browser/GPU rendering',
              'baseline_image_bytes': json.loads((ROOT / 'tools/baseline/runtime.json').read_text(encoding="utf-8"))['image_bytes'],
              'baseline_ready_seconds': None, 'baseline_boot_comparison': 'not available'}
    result['image_delta_bytes'] = result['image_bytes'] - result['baseline_image_bytes']
    (ROOT / 'reports/integration/docker.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
finally:
    subprocess.run([docker, 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
