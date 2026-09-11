"""Re-export the library routes from the current service, so the files match the code."""
import json, sys, urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8021"
GPX = Path(__file__).with_name("gpx")
WANTED = [("heart", 10.0), ("crescent", 9.0), ("triangle", 8.0),
          ("star5", 14.0), ("trex", 34.0)]

def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=900).read())

for shape, km in WANTED:
    r = post("/api/route", {"shape": shape, "target_km": km, "mode": "bike"})
    if r.get("status") != "ok":
        print(f"{shape}: {r.get('status') or r.get('error')}")
        continue
    with urllib.request.urlopen(BASE + r["gpx_url"], timeout=120) as f:
        gpx = f.read().decode()
    out = GPX / f"{shape}.gpx"
    out.write_text(gpx, encoding="utf-8")
    print(f"{out.name:<16}{r['route_km']:6.1f} km  dist {r['shape_distance']:.3f}  "
          f"{r['points']:3d} pts  upright {r['upright_deg']:6.1f} deg")
