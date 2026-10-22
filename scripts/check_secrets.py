#!/usr/bin/env python3
"""Audit Git content without printing credential values. Standard library only."""
import argparse
import ast
import re
import subprocess
from pathlib import Path

PATTERNS = (
    ('API credential', re.compile(rb'\bsk-[A-Za-z0-9_-]{20,}\b')),
    ('Ark credential', re.compile(rb'\bark-[a-fA-F0-9-]{30,}\b')),
    ('GitHub credential', re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b')),
    ('AWS access key', re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')),
    ('private key', re.compile(rb'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----')),
    ('credential in URL', re.compile(rb'https?://[^/\s:@]+:[^/@\s]+@')),
)
FORBIDDEN = {'config.py', 'config.local.py', '.env', '.streamlit/secrets.toml'}


def git(*args, check=True):
    return subprocess.run(['git', *args], check=check, capture_output=True).stdout


def known_credentials(root):
    path = root / 'config.py'
    if not path.is_file():
        return []
    values = []
    for node in ast.parse(path.read_text(encoding='utf-8')).body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or not any(
                    term in target.id.upper() for term in ('KEY', 'SECRET', 'TOKEN', 'PASSWORD', 'API_ID')):
                continue
            for value in ast.walk(node.value):
                if isinstance(value, ast.Constant) and isinstance(value.value, (str, int)):
                    text = str(value.value)
                    if len(text) >= 6 and text != target.id:
                        values.append(text.encode())
    return values


def audit(label, path, data, known, findings):
    normalized = path.replace('\\', '/')
    name = Path(normalized).name
    if (normalized in FORBIDDEN or name in ('config.py', 'config.local.py', '.env', 'secrets.toml')
            or (name.startswith('.env.') and name != '.env.example')
            or name.endswith(('.key', '.pem', '.p12', '.pfx'))):
        findings.add((label, path, 'sensitive configuration file'))
    if any(secret in data for secret in known):
        findings.add((label, path, 'known local credential'))
    for reason, pattern in PATTERNS:
        if pattern.search(data):
            findings.add((label, path, reason))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Read Git index blobs instead of working files')
    parser.add_argument('--history', action='store_true', help='Also inspect all reachable Git history')
    args = parser.parse_args()
    root = Path(git('rev-parse', '--show-toplevel').decode().strip())
    known = known_credentials(root)
    findings = set()
    paths = [p.decode() for p in git('ls-files', '-z').split(b'\0') if p]
    for path in paths:
        data = git('show', ':' + path) if args.staged else (root / path).read_bytes()
        audit('index' if args.staged else 'working tree', path, data, known, findings)
    revisions = git('rev-list', '--all', check=False).decode().splitlines() if args.history else []
    seen = set()
    for commit in revisions:
        for entry in git('ls-tree', '-rz', commit).split(b'\0'):
            if not entry:
                continue
            meta, path = entry.split(b'\t', 1)
            mode, kind, sha = meta.split()
            if kind != b'blob' or (sha, path) in seen:
                continue
            seen.add((sha, path))
            audit('history:' + commit[:8], path.decode(), git('cat-file', 'blob', sha.decode()), known, findings)
    for label, path, reason in sorted(findings):
        print(f'FAIL {label}: {path}: {reason}')
    if findings:
        raise SystemExit(1)
    print(f'PASS: {len(paths)} tracked files; {len(revisions)} history commits; no credential matches or sensitive config files')


if __name__ == '__main__':
    main()
