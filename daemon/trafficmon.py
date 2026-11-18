#!/usr/bin/env python
# trafficmon.py - per-remote-host byte counter for rooted webOS TV (Python 2.7).
# Counts IPv4/IPv6 bytes in/out per remote IP on one interface, classifies each
# remote as lan/private/multicast/wan, and appends JSON lines to a daily log.
# Usage: trafficmon.py [-i wlan0] [-d /var/lib/trafficmon] [-f 60]
#        trafficmon.py --report [-d /var/lib/trafficmon] [--hours 24]
import json
import os
import signal
import socket
import struct
import sys
import threading
import time

ETH_P_ALL = 0x0003
RUNNING = True
LIVE = {'since': 0, 'hosts': []}


def _stop(signum, frame):
    global RUNNING
    RUNNING = False


def local_ips(iface):
    ips = set()
    try:
        import fcntl
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ips.add(socket.inet_ntoa(fcntl.ioctl(
            s.fileno(), 0x8915,  # SIOCGIFADDR
            struct.pack('256s', iface[:15])))[20:24])
    except Exception:
        pass
    try:
        with open('/proc/net/if_inet6') as f:
            for line in f:
                parts = line.split()
                if len(parts) == 6 and parts[5] == iface:
                    raw = parts[0]
                    ip = socket.inet_ntop(socket.AF_INET6,
                                          raw.decode('hex'))
                    ips.add(ip)
    except Exception:
        pass
    return ips


def classify(ip):
    if ':' in ip:
        if ip.startswith('ff'):
            return 'multicast'
        if ip.startswith('fe80') or ip.startswith('fc') or ip.startswith('fd'):
            return 'lan'
        return 'wan'
    o = [int(x) for x in ip.split('.')]
    if o[0] >= 224:
        return 'multicast'
    if o[0] == 10 or o[0] == 127 or (o[0] == 172 and 16 <= o[1] <= 31) \
            or (o[0] == 192 and o[1] == 168) or (o[0] == 169 and o[1] == 254):
        return 'lan'
    return 'wan'


def parse(frame, local):
    """Return (remote_ip, direction, nbytes) or None."""
    if len(frame) < 14:
        return None
    eth = struct.unpack('!H', frame[12:14])[0]
    off = 14
    if eth in (0x8100, 0x88a8):  # VLAN tags
        eth = struct.unpack('!H', frame[16:18])[0]
        off = 18
    if eth == 0x0800 and len(frame) >= off + 20:
        ihl = (ord(frame[off]) & 0x0f) * 4
        n = struct.unpack('!H', frame[off + 2:off + 4])[0]
        src = socket.inet_ntoa(frame[off + 12:off + 16])
        dst = socket.inet_ntoa(frame[off + 16:off + 20])
    elif eth == 0x86dd and len(frame) >= off + 40:
        n = struct.unpack('!H', frame[off + 4:off + 6])[0] + 40
        src = socket.inet_ntop(socket.AF_INET6, frame[off + 8:off + 24])
        dst = socket.inet_ntop(socket.AF_INET6, frame[off + 24:off + 40])
    else:
        return None
    if src in local:
        return dst, 'tx', n
    if dst in local:
        return src, 'rx', n
    return None


def flush(acct, logpath, started):
    rec = {
        'ts': int(time.time()),
        'since': started,
        'hosts': [{'ip': ip, 'cls': cls, 'tx': v[0], 'rx': v[1]}
                  for (ip, cls), v in sorted(
                      acct.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))],
    }
    with open(logpath, 'a') as f:
        f.write(json.dumps(rec) + '\n')


def aggregate(datadir, hours):
    """Sum JSONL deltas over the last `hours` hours.

    Returns {'hosts': {key: [tx, rx]}, 'series': {minute_ts: [tx, rx]}}.
    """
    cutoff = time.time() - hours * 3600
    agg = {}
    series = {}
    for name in sorted(os.listdir(datadir)):
        if not name.startswith('stats-') or not name.endswith('.jsonl'):
            continue
        with open(os.path.join(datadir, name)) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get('ts', 0) < cutoff:
                    continue
                bucket = int(rec['ts'] // 60) * 60
                b = series.setdefault(bucket, [0, 0])
                for h in rec.get('hosts', []):
                    k = (h['ip'], h['cls'])
                    a = agg.setdefault(k, [0, 0])
                    a[0] += h['tx']
                    a[1] += h['rx']
                    b[0] += h['tx']
                    b[1] += h['rx']
    return agg, series


def report(datadir, hours):
    agg, _ = aggregate(datadir, hours)
    rows = sorted(agg.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))
    print('%-40s %-9s %12s %12s' % ('remote', 'class', 'tx_bytes', 'rx_bytes'))
    for (ip, cls), (tx, rx) in rows[:40]:
        print('%-40s %-9s %12d %12d' % (ip, cls, tx, rx))


def api_response(path, datadir):
    """Return (status, body-dict) for a GET path like /api/summary?hours=1."""
    parts = path.split('?', 1)
    qs = {}
    if len(parts) == 2:
        for kv in parts[1].split('&'):
            if '=' in kv:
                k, v = kv.split('=', 1)
                qs[k] = v
    if parts[0] == '/api/summary':
        try:
            hours = float(qs.get('hours', 24))
        except ValueError:
            hours = 24
        agg, series = aggregate(datadir, hours)
        hosts = [{'ip': ip, 'cls': cls, 'tx': v[0], 'rx': v[1]}
                 for (ip, cls), v in sorted(
                     agg.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))]
        return 200, {
            'hours': hours,
            'generated': int(time.time()),
            'hosts': hosts,
            'live': {'since': LIVE['since'],
                     'hosts': [dict(h) for h in LIVE['hosts']]},
            'series': [{'t': t, 'tx': v[0], 'rx': v[1]}
                       for t, v in sorted(series.items())],
        }
    if parts[0] == '/api/live':
        return 200, dict(LIVE)
    return 404, {'error': 'not found'}


def serve_http(port, datadir):
    """Minimal HTTP/1.0 JSON server (stdlib httpd modules are absent on webOS).

    Runs on a daemon thread; each request is answered on its own thread so a
    slow client cannot block the accept loop.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('', port))
    srv.listen(8)

    def handle(conn):
        try:
            conn.settimeout(10)
            req = conn.recv(8192).decode('latin-1')
            path = req.split(' ')[1] if req.startswith('GET ') else '/'
            code, obj = api_response(path, datadir)
            body = json.dumps(obj).encode()
            reason = {200: 'OK', 404: 'Not Found'}.get(code, 'ERR')
            conn.sendall(
                ('HTTP/1.0 %d %s\r\nContent-Type: application/json\r\n'
                 'Content-Length: %d\r\nAccess-Control-Allow-Origin: *\r\n'
                 '\r\n' % (code, reason, len(body))).encode() + body)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def loop():
        while RUNNING:
            try:
                conn, _ = srv.accept()
            except Exception:
                continue
            t = threading.Thread(target=handle, args=(conn,))
            t.daemon = True
            t.start()

    t = threading.Thread(target=loop)
    t.daemon = True
    t.start()


def main():
    iface = 'wlan0'
    datadir = '/var/lib/trafficmon'
    flush_s = 60
    args = sys.argv[1:]
    if '--report' in args:
        hours = 24
        if '--hours' in args:
            hours = float(args[args.index('--hours') + 1])
        if '-d' in args:
            datadir = args[args.index('-d') + 1]
        report(datadir, hours)
        return
    if '-i' in args:
        iface = args[args.index('-i') + 1]
    if '-d' in args:
        datadir = args[args.index('-d') + 1]
    if '-f' in args:
        flush_s = int(args[args.index('-f') + 1])
    if '--http' in args:
        port = int(args[args.index('--http') + 1])
        serve_http(port, datadir)

    if not os.path.isdir(datadir):
        os.makedirs(datadir)
    local = local_ips(iface)
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW,
                      socket.htons(ETH_P_ALL))
    s.bind((iface, 0))
    s.settimeout(5)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    acct = {}
    day = time.strftime('%Y-%m-%d')
    logpath = os.path.join(datadir, 'stats-%s.jsonl' % day)
    last_flush = started = time.time()
    live_ts = 0

    while RUNNING:
        try:
            frame = s.recv(65535)
        except socket.timeout:
            frame = None
        except socket.error:
            frame = None
        if frame:
            p = parse(frame, local)
            if p:
                ip, direction, n = p
                key = (ip, classify(ip))
                v = acct.get(key)
                if v is None:
                    acct[key] = [n, 0] if direction == 'tx' else [0, n]
                elif direction == 'tx':
                    v[0] += n
                else:
                    v[1] += n
        now = time.time()
        today = time.strftime('%Y-%m-%d')
        if today != day:
            day = today
            logpath = os.path.join(datadir, 'stats-%s.jsonl' % day)
            acct = {}
            started = now
        if now - last_flush >= flush_s:
            try:
                flush(acct, logpath, started)
            except Exception:
                pass
            acct = {}
            started = now
            last_flush = now
        if now - live_ts >= 5:
            LIVE['since'] = started
            LIVE['hosts'] = [{'ip': ip, 'cls': cls, 'tx': v[0], 'rx': v[1]}
                             for (ip, cls), v in acct.items()]
            live_ts = now
    try:
        flush(acct, logpath, started)
    except Exception:
        pass


if __name__ == '__main__':
    main()
