# Traffic Monitor for webOS TV

Shows what your rooted LG webOS TV talks to: per-remote-host byte counters,
classified as WAN / LAN / multicast, with per-minute history.

Two parts:

- **`daemon/trafficmon.py`** — a Python 2.7 daemon that runs *on the TV*:
  raw `AF_PACKET` capture on `wlan0`, per-minute JSONL deltas under
  `/var/lib/trafficmon/`, plus a tiny built-in JSON API on `:8899`
  (`/api/summary?hours=N`, `/api/live`). No dependencies beyond stock
  webOS Python 2.7.
- **`app/`** — a plain HTML/JS webOS app that fetches the API and renders
  24h totals, a per-minute traffic chart and a top-talkers table.

## Build & install

```sh
python3 make_icon.py        # regenerate app/icon.png
python3 build_ipk.py        # -> io.github.dzienisz.trafficmon_<ver>_all.ipk
```

Install on a rooted TV through the Homebrew Channel service:

```sh
luna-send -i -a webosbrew -f luna://org.webosbrew.hbchannel.service/install \
  '{"ipkUrl":"http://<dev-machine>:8000/<pkg>.ipk","ipkHash":"<sha256>","subscribe":true}'
```

The ipk is a deb-style `ar` archive; `build_ipk.py` produces the exact
layout webOS `appinstalld` expects (`webOS-Package-Format-Version: 2` in
control, `usr/palm/packages/<id>/` dir entry in data.tar.gz — both
required, a bare ar archive gets `FAILED_IPKG_INSTALL`).

## Daemon deployment

```sh
scp daemon/trafficmon.py tv:/var/lib/trafficmon/trafficmon.py
# boot hook (runs via webosbrew init.d):
cat /var/lib/webosbrew/init.d/95-trafficmon
```

Hook script:

```sh
#!/bin/sh
[ -x /var/lib/trafficmon/trafficmon.py ] || exit 0
pgrep -f "^/usr/bin/python /var/lib/trafficmon/trafficmon.py" >/dev/null 2>&1 && exit 0
( nohup /usr/bin/python /var/lib/trafficmon/trafficmon.py -i wlan0 --http 8899 \
    >/var/lib/trafficmon/trafficmon.log 2>&1 & ) || true
exit 0
```

The `pgrep` pattern must be anchored to the full argv — a loose pattern
also matches the invoking ssh/sh command line.

## Notes

- WAN traffic on webOS 5/6 TVs is mostly IPv6 — don't draw conclusions from
  IPv4-only views.
- The API binds `0.0.0.0:8899` (LAN-readable, read-only stats, no auth).
- Requires a rooted TV (Homebrew Channel). Developed on OLED55BX3LB,
  webOS 5.6.2.
