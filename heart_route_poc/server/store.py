"""
Routes that survive a restart.

`_ROUTE_CACHE` made a repeat request instant and lost everything when the
process ended, so the first rider after every restart paid 8 to 53 seconds for
a route the server had already computed - possibly many times.

SQLITE, FROM THE STANDARD LIBRARY. No dependency to install for something a
person has to be able to run in one command, one file to delete when it goes
wrong, and it answers the question this actually is: a key-value store that has
to outlive a process and be inspectable when a route comes out wrong.

WHAT IS STORED IS THE ROUTE, NOT THE PICTURE. A route answer measures 1,068 KB
and 1,045 of those are `streets` - the 16,433 road polylines the page draws
behind the route. Those are a filter over the network by bounding box, so they
are regenerated on the way out and never written down. What is left is 22 KB.
At 1,500 routes that is 33 MB instead of 1.6 GB.

THE FINGERPRINT IS THE PART THAT MATTERS. A stored route is only valid while
the shape still means what it meant: the gear got its centre bore between two
rounds of this project and five shapes were redrawn under their own names,
which silently corrupted the rater pool for weeks (BACKLOG 45). So every row
carries a hash of the outline it was fitted to, and a row whose shape no longer
hashes the same is dropped at load rather than served. Cheap, and it makes the
class of bug that has already cost this project the most impossible here.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS routes (
    key         TEXT PRIMARY KEY,
    shape       TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    target_km   REAL NOT NULL,
    mode        TEXT NOT NULL,
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    built_at    REAL NOT NULL,
    answer      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS routes_by_shape ON routes (shape);
"""
# Regenerated on the way out, never stored - see the module docstring.
DERIVED = ("streets",)

_lock = threading.Lock()


def fingerprint(shape: str, points: int = 64) -> str:
    """A hash of the outline, so a redrawn shape cannot serve an old route."""
    from routeshape.shapes.library import resample_by_arclength

    xy = np.round(resample_by_arclength(shape, points), 4)
    return hashlib.sha1(xy.tobytes()).hexdigest()[:16]


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._db.commit()

    def put(self, key: tuple, answer: dict) -> None:
        shape = answer.get("shape", "")
        try:
            mark = fingerprint(shape)
        except Exception:                                # noqa: BLE001
            return                                       # not a library shape
        thin = {k: v for k, v in answer.items() if k not in DERIVED}
        with _lock:
            self._db.execute(
                "INSERT OR REPLACE INTO routes VALUES (?,?,?,?,?,?,?,?,?)",
                ("|".join(str(k) for k in key), shape, mark, key[1], key[2],
                 key[3], key[4], time.time(),
                 json.dumps(thin, ensure_ascii=False)))
            self._db.commit()

    def load(self) -> tuple[dict, int]:
        """(everything still valid, keyed as the cache keys it, how many were
        dropped because their shape has been redrawn or withdrawn)."""
        from routeshape.shapes.library import SHAPES

        marks: dict[str, str] = {}
        out, dropped = {}, 0
        with _lock:
            rows = self._db.execute(
                "SELECT key, shape, fingerprint, answer FROM routes").fetchall()
        stale = []
        for key, shape, mark, answer in rows:
            if shape not in SHAPES:
                dropped += 1
                stale.append(key)
                continue
            if shape not in marks:
                marks[shape] = fingerprint(shape)
            if marks[shape] != mark:
                dropped += 1
                stale.append(key)
                continue
            parts = key.split("|")
            if len(parts) != 6:          # written before variants existed
                dropped += 1
                stale.append(key)
                continue
            out[(parts[0], float(parts[1]), parts[2], float(parts[3]),
                 float(parts[4]), int(parts[5]))] = json.loads(answer)
        if stale:
            with _lock:
                self._db.executemany("DELETE FROM routes WHERE key = ?",
                                     [(k,) for k in stale])
                self._db.commit()
        return out, dropped

    def count(self) -> int:
        with _lock:
            return self._db.execute("SELECT COUNT(*) FROM routes").fetchone()[0]
