"""Fail on lost contracts, changed science inputs, altered vendor sources or failed checks."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def additive(old, new, trail=''):
    if isinstance(old, dict):
        assert isinstance(new, dict), f'API type changed: {trail}'
        for key, value in old.items():
            assert key in new, f'API field removed: {trail}/{key}'
            additive(value, new[key], f'{trail}/{key}')
    else:
        assert old == new, f'API value changed: {trail}'


def scan_secrets(paths):
    # Do not print the matched value, even if a genuine key is found.
    pattern = re.compile(rb'(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{28,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
    findings = []
    for path in paths:
        if path.is_file() and pattern.search(path.read_bytes()):
            findings.append(str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path))
    assert not findings, f'Potential secrets in files (values suppressed): {findings}'


def checks(api_url=None):
    baseline = json.loads((ROOT / 'tools/baseline/data-sha256.json').read_text(encoding="utf-8"))
    for name, expected in baseline.items():
        assert digest(ROOT / name) == expected, f'Science data changed: {name}'
    vendor = ROOT / 'backend/vendor/qfit'
    manifest = json.loads((vendor / 'VENDOR_MANIFEST.json').read_text(encoding="utf-8"))
    for entry in manifest['files']:
        assert digest(vendor / entry['path']) == entry['sha256'], f'Vendor changed: {entry["path"]}'
    if api_url:
        with urllib.request.urlopen(api_url.rstrip('/') + '/api/openapi.json', timeout=10) as response:
            current = json.load(response)
    else:
        from blinkspace.api import create_app
        current = create_app(start_workers=False).openapi()
    old = json.loads((ROOT / 'tools/baseline/openapi.json').read_text(encoding="utf-8"))
    additive(old['paths'], current['paths'], '/paths')
    additive(old['components']['schemas'], current['components']['schemas'], '/components/schemas')
    evidence = ROOT / 'evidence/integration'
    front = json.loads((evidence / 'frontend-tests.json').read_text(encoding="utf-8"))
    assert front['numFailedTests'] == 0 and front['numPassedTests'] >= 166
    # The JUnit root may be testsuites; count leaf test cases once.
    cases = ET.parse(evidence / 'backend-tests.xml').getroot().findall('.//testcase')
    assert not any(c.find('failure') is not None or c.find('error') is not None for c in cases)
    backend_passed = sum(c.find('skipped') is None for c in cases)
    assert backend_passed >= 178
    scan_secrets((ROOT / 'frontend/dist').rglob('*'))
    scan_secrets((ROOT / 'backend/vendor/qfit').rglob('*'))
    result = {'baseline_commit': '77b410705f6de705423aca025794a03a73afd614', 'science_files_unchanged': len(baseline),
              'qfit_vendor_files_unchanged': len(manifest['files']), 'api_added_paths': sorted(set(current['paths']) - set(old['paths'])),
              'api_removed_or_changed_fields': 0, 'frontend_passed': front['numPassedTests'], 'backend_passed': backend_passed,
              'backend_skipped': len(cases) - backend_passed, 'secret_scan': 'no matching key/private-key patterns',
              'browser_visual_gpu_acceptance': 'not performed: prior saved browser access denial; no bypass used',
              'paid_provider_live_test': json.loads((ROOT / 'reports/integration/assistant-eval.json').read_text(encoding="utf-8")) if (ROOT / 'reports/integration/assistant-eval.json').exists() else 'not recorded', 'public_deployment': False}
    (ROOT / 'reports/integration/regression.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--api-url')
    args = parser.parse_args()
    checks(args.api_url)
