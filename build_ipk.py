#!/usr/bin/env python3
"""Build an .ipk (ar archive) from app/ without external tools.

ipk = ar(debian-binary, control.tar.gz, data.tar.gz)
Output: io.github.dzienisz.trafficmon_<ver>_all.ipk
"""
import io
import json
import os
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, 'app')

with open(os.path.join(APP, 'appinfo.json')) as f:
    info = json.load(f)
pkg_id = info['id']
version = info['version']
out = os.path.join(HERE, '%s_%s_all.ipk' % (pkg_id, version))


def tar_gz(entries):
    """entries: [(arcname, bytes|None)] — None means a directory entry."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as t:
        for name, data in entries:
            ti = tarfile.TarInfo(name)
            ti.mtime = int(time.time())
            if data is None:
                ti.type = tarfile.DIRTYPE
                ti.mode = 0o755
                t.addfile(ti)
            else:
                ti.mode = 0o644
                ti.size = len(data)
                t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


control = tar_gz([('control', ('''\
Package: %s
Version: %s
Section: misc
Priority: optional
Architecture: all
Installed-Size: 1
Maintainer: dzienisz <nobody@example.com>
Description: Traffic Monitor - per-host byte counters (trafficmon.py)
webOS-Package-Format-Version: 2
webOS-Packager-Version: x.y.x
''' % (pkg_id, version)).encode())])

appdir = 'usr/palm/applications/%s/' % pkg_id
data_entries = [
    ('usr/', None), ('usr/palm/', None), ('usr/palm/applications/', None),
    ('usr/palm/packages/', None),
    ('usr/palm/packages/%s/' % pkg_id, None),
    (appdir, None),
]
for name in sorted(os.listdir(APP)):
    path = os.path.join(APP, name)
    with open(path, 'rb') as f:
        data_entries.append((appdir + name, f.read()))
data = tar_gz(data_entries)


def ar_member(name, payload):
    hdr = ('%-16s%-12d%-6d%-6d%-8o%-10d`\n' % (
        name, int(time.time()), 0, 0, 0o100644, len(payload))).encode()
    return hdr + payload + (b'\n' if len(payload) % 2 else b'')


ipk = (b'!<arch>\n'
       + ar_member('debian-binary', b'2.0\n')
       + ar_member('control.tar.gz', control)
       + ar_member('data.tar.gz', data))
with open(out, 'wb') as f:
    f.write(ipk)

import hashlib
print('%s  sha256=%s  %d bytes' % (
    os.path.basename(out), hashlib.sha256(ipk).hexdigest(), len(ipk)))
