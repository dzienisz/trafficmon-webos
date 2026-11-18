#!/usr/bin/env python3
"""Emit the homebrew-repo manifest for the current app version.

Reads app/appinfo.json, builds the ipk if missing, and writes
<build_dir>/<id>.manifest.json with real sha256/size so the file can be
uploaded to the GitHub release verbatim.
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = sys.argv[1] if len(sys.argv) > 1 else HERE

with open(os.path.join(HERE, 'app', 'appinfo.json')) as f:
    info = json.load(f)

ipk_name = '%s_%s_all.ipk' % (info['id'], info['version'])
ipk_path = os.path.join(BUILD, ipk_name)
if not os.path.exists(ipk_path):
    subprocess.check_call(
        [sys.executable, os.path.join(HERE, 'build_ipk.py')],
        cwd=BUILD)

data = open(ipk_path, 'rb').read()
manifest = {
    'id': info['id'],
    'version': info['version'],
    'type': 'web',
    'title': info['title'],
    'appDescription': info.get('appDescription', ''),
    'iconUri': 'https://raw.githubusercontent.com/dzienisz/trafficmon-webos/main/app/icon.png',
    'sourceUrl': 'https://github.com/dzienisz/trafficmon-webos',
    'rootRequired': 'required',
    'ipkUrl': ipk_name,
    'ipkHash': {'sha256': hashlib.sha256(data).hexdigest()},
    'ipkSize': len(data),
}
out = os.path.join(BUILD, '%s.manifest.json' % info['id'])
with open(out, 'w') as f:
    json.dump(manifest, f, indent=2)
print(out)
