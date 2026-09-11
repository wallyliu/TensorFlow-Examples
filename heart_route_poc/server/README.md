# The pipeline, behind three endpoints

Everything this project does has been reachable only by running Python in a
terminal. This is the same code behind an HTTP service, so a page can ask for a
route and get a `.gpx` back.

```
python server/app.py              # http://127.0.0.1:8000
python server/app.py --warm       # load the Taipei bike network before serving
python server/app.py --port 8080 --host 0.0.0.0
```

Standard library only — no framework to install. The work per request is a few
seconds of numpy and networkx, so the web layer is never the bottleneck and a
dependency would only add a setup step.

## Endpoints

| | |
|---|---|
| `GET /` | the page |
| `GET /api/shapes?mode=bike` | every shape with its `n_min` and minimum distance |
| `POST /api/plan` | `{shape, target_km, mode}` → feasibility. No map, returns immediately |
| `POST /api/route` | the same, plus `lat`/`lon` → fits a route, returns coordinates and a GPX link |
| `GET /api/route/<id>.gpx` | the file |

## What costs time

Downloading a city's street network takes minutes and it is the same network for
every request in that city, so it is loaded once per (place, mode) and kept in
memory. The first request after startup pays for it; `--warm` pays it up front.

Measured on the Taipei bike network (4,500 m half-size, 23,554 nodes):

| | |
|---|---|
| first request, cold | ~30 s — 16 s loading the network, 13.5 s fitting |
| later requests | **~12.6 s** |
| `/api/plan` | immediate — it is arithmetic, no map involved |

Most of the 12.6 s is fitting three candidate placements and keeping the best.
`N_CANDIDATES = 1` costs about a third of that and takes whichever placement the
coarse scan liked most; three is worth it because the coarse scan's ranking and
the final shape distance disagree often enough to matter.

## What it does not do

- **One city.** The network half-size and the default centre are Taipei's. Other
  coordinates work, but the first request for each pays the download.
- **Routes live in memory.** Restarting the server drops every GPX link. A real
  deployment writes them somewhere.
- **No authentication, no rate limit.** A fit is seconds of CPU, so do not put
  this on a public address as it stands.
