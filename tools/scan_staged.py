"""Scan exact Git index blobs; emit categories/paths, never matched values.

Run with the backend Python environment. This is a publication gate, not a
general-purpose proof of absence of secrets. Local .env values are read only
for in-memory comparisons and are never written to the result.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.run(['git', '-c', 'safe.directory=' + ROOT.as_posix(),
                           '-C', str(ROOT), *args], check=True, capture_output=True).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    known = []
    for directory in (ROOT, ROOT / 'backend', ROOT / 'frontend'):
        for path in directory.glob('.env*'):
            if path.is_file() and path.name != '.env.example':
                for key, value in dotenv_values(path).items():
                    if value and len(value) >= 10 and re.search(r'KEY|TOKEN|SECRET|PASSWORD|EMAIL|URL', key):
                        known.append((key, value.encode()))
    findings, files, benign = [], [], []
    patterns = {
        'Google API credential': rb'AIza[0-9A-Za-z_-]{35}',
        'Supabase privileged credential': rb'sb_secret_[A-Za-z0-9_-]{15,}',
        'JWT-shaped token': rb'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
        'private key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        'database URL with credentials': rb'postgres(?:ql)?://[^\s:"<>]+:[^\s@"<>]+@',
        'literal bearer credential': rb'Bearer [A-Za-z0-9_.-]{24,}',
        'personal filesystem path': rb'[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/][^\s"\']+',
    }
    for record in git('ls-files', '--stage', '-z').split(b'\0'):
        if not record:
            continue
        metadata, path_bytes = record.split(b'\t', 1)
        mode, oid, stage = metadata.decode().split()
        path = path_bytes.decode()
        if stage != '0' or mode not in ('100644', '100755'):
            findings.append({'path': path, 'category': 'unexpected index mode/stage'})
            continue
        data = git('cat-file', 'blob', oid)
        files.append({'path': path, 'bytes': len(data), 'oid': oid})
        parts = Path(path).parts
        if any(p in ('.git', '.local-backups', 'node_modules', 'venv', '.venv', 'build', 'dist', '__pycache__') for p in parts):
            findings.append({'path': path, 'category': 'forbidden generated/private directory'})
        if Path(path).name.startswith('.env') and Path(path).name != '.env.example':
            findings.append({'path': path, 'category': 'private environment file'})
        if len(data) > 2 * 1024 * 1024:
            findings.append({'path': path, 'category': 'large staged file requires review'})
        for name, value in known:
            if value in data:
                findings.append({'path': path, 'category': 'configured value: ' + name})
        for category, pattern in patterns.items():
            matches = re.findall(pattern, data)
            # Exact synthetic negative test, not a blanket exemption for tests.
            if (path == 'frontend/scripts/validate-env.test.cjs'
                    and category == 'Supabase privileged credential'
                    and matches == [b'sb_secret_' + b'NEVER_ECHO_THIS']):
                benign.append({'path': path, 'category': 'known synthetic rejection test'})
            elif matches:
                findings.append({'path': path, 'category': category})
        email_pattern = rb'[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})'
        public_contacts = set()
        if path == 'frontend/package-lock.json':
            # Reviewed upstream maintainer contact in npm's deprecation notice.
            notice = json.loads(data).get('packages', {}).get('node_modules/glob', {}).get('deprecated', '')
            public_contacts = {m.group(0) for m in re.finditer(email_pattern, notice.encode()) if m.group(1) == b'izs.me'}
        for address in re.finditer(email_pattern, data):
            domain = address.group(1).decode().lower()
            if address.group(0) in public_contacts:
                benign.append({'path': path, 'category': 'public upstream maintainer contact in glob deprecation metadata'})
                continue
            if domain not in ('example.com', 'example.org', 'example.net', 'test.com', 'test.local') and not domain.endswith(('.invalid', '.test', '.example')):
                findings.append({'path': path, 'category': 'email metadata requires review'})
                break
    findings = list({(v['path'], v['category']): v for v in findings}.values())
    index_fingerprint = hashlib.sha256('\n'.join(f["path"] + ':' + f['oid'] for f in files).encode()).hexdigest()
    result = {
        'scope': 'exact Git index blobs, not worktree files',
        'files': len(files), 'total_bytes': sum(f['bytes'] for f in files),
        'index_fingerprint_sha256': index_fingerprint,
        'largest_files': sorted(files, key=lambda f: f['bytes'], reverse=True)[:10],
        'findings': findings, 'reviewed_benign_patterns': benign,
        'status': 'PASS' if files and not findings else 'REVIEW_REQUIRED',
        'limits': 'Known local configured values and patterns only; inspect assets, identifiers and license rights separately. No values emitted.',
    }
    output = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(output, encoding='utf-8')
    print(output)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
