"""Render a pip --dry-run --ignore-installed --report resolution into a hash lock."""
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
rows = []
for package in report['install']:
    metadata = package['metadata']
    digest = package['download_info']['archive_info']['hashes']['sha256']
    rows.append(f"{metadata['name']}=={metadata['version']} --hash=sha256:{digest}")
Path(sys.argv[2]).write_text('# Generated from a real pip resolution; platform-specific wheels.\n' + '\n'.join(sorted(rows, key=str.lower)) + '\n', encoding='utf-8')
