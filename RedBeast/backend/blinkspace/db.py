"""Kalıcı kayıtlar (SQLite).

Kayıt türleri: arama isteği, gözlem önbelleği (arşiv yanıtı), ham dosya, hazırlama işi, hazırlanmış görüntü
dizisi (kareleriyle), paylaşılmış gözlem (işaretleriyle), öğretici görev, katalog önbelleği.
Her bağlantı tek iş parçacığında kullanılır; yazmalar kısa işlemlerdir (WAL).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import zlib
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS searches (
  id TEXT PRIMARY KEY, created_at REAL NOT NULL, request_key TEXT NOT NULL, params TEXT NOT NULL, job_id TEXT
);
CREATE TABLE IF NOT EXISTS tap_cache (
  key TEXT PRIMARY KEY, fetched_at REAL NOT NULL, meta TEXT NOT NULL, payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS catalog_cache (
  key TEXT PRIMARY KEY, fetched_at REAL NOT NULL, payload BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS raw_files (
  url TEXT PRIMARY KEY, sha256 TEXT NOT NULL, size INTEGER NOT NULL, fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, request_key TEXT NOT NULL, kind TEXT NOT NULL, params TEXT NOT NULL,
  status TEXT NOT NULL, stage TEXT, progress REAL NOT NULL DEFAULT 0, detail TEXT,
  error TEXT, sequence_id TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_key ON jobs(request_key, created_at);
CREATE TABLE IF NOT EXISTS sequences (
  id TEXT PRIMARY KEY, sequence_key TEXT NOT NULL UNIQUE, request_key TEXT NOT NULL,
  status TEXT NOT NULL, params TEXT NOT NULL, meta TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sequences_req ON sequences(request_key, created_at);
CREATE TABLE IF NOT EXISTS frames (
  sequence_id TEXT NOT NULL, idx INTEGER NOT NULL, obs_id TEXT NOT NULL, detector INTEGER NOT NULL,
  mjd_avg REAL NOT NULL, lam_um REAL NOT NULL, meta TEXT NOT NULL,
  PRIMARY KEY (sequence_id, idx)
);
CREATE TABLE IF NOT EXISTS shared_observations (
  id TEXT PRIMARY KEY, sequence_id TEXT NOT NULL, title TEXT NOT NULL, note TEXT NOT NULL,
  marks TEXT NOT NULL, view TEXT NOT NULL, edit_token_hash TEXT NOT NULL, app_version TEXT NOT NULL,
  created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tutorials (id TEXT PRIMARY KEY, position INTEGER NOT NULL, data TEXT NOT NULL);
"""

TERMINAL = ("done", "insufficient_data", "failed", "cancelled")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        # executescript kendi işlemini yönetir (önce COMMIT eder); açık işlem içinde çağrılmaz.
        self._conn().executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA foreign_keys=ON")
            self._local.conn = c
        return c

    @contextmanager
    def tx(self):
        c = self._conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise

    def close(self) -> None:
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    # ---- arşiv ve katalog önbelleği -------------------------------------------------
    def get_tap(self, key: str, max_age_s: float):
        r = self._conn().execute("SELECT fetched_at, meta, payload FROM tap_cache WHERE key=?", (key,)).fetchone()
        if not r or (time.time() - r["fetched_at"]) > max_age_s:
            return None
        return {"fetched_at": r["fetched_at"], "meta": json.loads(r["meta"]), "rows": json.loads(zlib.decompress(r["payload"]))}

    def put_tap(self, key: str, meta: dict, rows: list[dict]) -> None:
        blob = zlib.compress(json.dumps(rows, separators=(",", ":")).encode(), 6)
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO tap_cache(key, fetched_at, meta, payload) VALUES (?,?,?,?)",
                      (key, time.time(), json.dumps(meta), blob))

    def get_catalog(self, key: str, max_age_s: float):
        r = self._conn().execute("SELECT fetched_at, payload FROM catalog_cache WHERE key=?", (key,)).fetchone()
        if not r or (time.time() - r["fetched_at"]) > max_age_s:
            return None
        return json.loads(zlib.decompress(r["payload"]))

    def put_catalog(self, key: str, payload) -> None:
        blob = zlib.compress(json.dumps(payload, separators=(",", ":")).encode(), 6)
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO catalog_cache(key, fetched_at, payload) VALUES (?,?,?)", (key, time.time(), blob))

    # ---- ham dosyalar ----------------------------------------------------------------
    def get_raw(self, url: str):
        r = self._conn().execute("SELECT sha256, size, fetched_at FROM raw_files WHERE url=?", (url,)).fetchone()
        return dict(r) if r else None

    def put_raw(self, url: str, sha256: str, size: int) -> None:
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO raw_files(url, sha256, size, fetched_at) VALUES (?,?,?,?)",
                      (url, sha256, size, time.time()))

    # ---- arama istekleri -------------------------------------------------------------
    def add_search(self, search_id: str, request_key: str, params: dict, job_id: str | None) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO searches(id, created_at, request_key, params, job_id) VALUES (?,?,?,?,?)",
                      (search_id, time.time(), request_key, json.dumps(params), job_id))

    # ---- işler -----------------------------------------------------------------------
    def create_job(self, job_id: str, request_key: str, kind: str, params: dict) -> None:
        now = time.time()
        with self.tx() as c:
            c.execute(
                "INSERT INTO jobs(id, request_key, kind, params, status, stage, progress, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (job_id, request_key, kind, json.dumps(params), "queued", "queued", 0.0, now, now),
            )

    def update_job(self, job_id: str, **fields) -> None:
        if not fields:
            return
        if "detail" in fields and not isinstance(fields["detail"], (str, type(None))):
            fields["detail"] = json.dumps(fields["detail"])
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k}=?" for k in fields)
        with self.tx() as c:
            c.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))

    def get_job(self, job_id: str):
        r = self._conn().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._job(r)

    @staticmethod
    def _job(r):
        if not r:
            return None
        d = dict(r)
        d["params"] = json.loads(d["params"])
        d["cancel_requested"] = bool(d["cancel_requested"])
        if d.get("detail"):
            try:
                d["detail"] = json.loads(d["detail"])
            except json.JSONDecodeError:
                pass
        return d

    def active_job_for(self, request_key: str):
        """Aynı istek için bitmemiş iş (aynı isteği birleştirme)."""
        r = self._conn().execute(
            f"SELECT * FROM jobs WHERE request_key=? AND status NOT IN ({','.join('?' * len(TERMINAL))}) "
            "ORDER BY created_at DESC LIMIT 1",
            (request_key, *TERMINAL),
        ).fetchone()
        return self._job(r)

    def request_cancel(self, job_id: str) -> bool:
        with self.tx() as c:
            cur = c.execute(
                f"UPDATE jobs SET cancel_requested=1, updated_at=? WHERE id=? AND status NOT IN ({','.join('?' * len(TERMINAL))})",
                (time.time(), job_id, *TERMINAL),
            )
            return cur.rowcount > 0

    def is_cancel_requested(self, job_id: str) -> bool:
        r = self._conn().execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        return bool(r and r["cancel_requested"])

    def interrupt_unfinished_jobs(self) -> int:
        """Sunucu yeniden başladığında yarım kalan işleri gerçek durumuyla işaretler."""
        with self.tx() as c:
            cur = c.execute(
                f"UPDATE jobs SET status='failed', stage='failed', error='interrupted_by_restart', updated_at=? "
                f"WHERE status NOT IN ({','.join('?' * len(TERMINAL))})",
                (time.time(), *TERMINAL),
            )
            return cur.rowcount

    def count_active_before(self, job_id: str) -> int:
        """Unfinished jobs created before this one: how many are ahead of it in the queue."""
        r = self._conn().execute(
            f"SELECT COUNT(*) AS n FROM jobs WHERE status NOT IN ({','.join('?' * len(TERMINAL))}) "
            "AND rowid < (SELECT rowid FROM jobs WHERE id=?)", (*TERMINAL, job_id)      # insertion order; clock ticks can tie
        ).fetchone()
        return int(r["n"])

    def count_active_jobs(self) -> int:
        r = self._conn().execute(
            f"SELECT COUNT(*) AS n FROM jobs WHERE status NOT IN ({','.join('?' * len(TERMINAL))})", TERMINAL
        ).fetchone()
        return int(r["n"])

    # ---- diziler ve kareler ----------------------------------------------------------
    def put_sequence(self, seq_id: str, sequence_key: str, request_key: str, status: str, params: dict, meta: dict, frames: list[dict]) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO sequences(id, sequence_key, request_key, status, params, meta, created_at) VALUES (?,?,?,?,?,?,?)",
                (seq_id, sequence_key, request_key, status, json.dumps(params), json.dumps(meta), time.time()),
            )
            for f in frames:
                c.execute(
                    "INSERT INTO frames(sequence_id, idx, obs_id, detector, mjd_avg, lam_um, meta) VALUES (?,?,?,?,?,?,?)",
                    (seq_id, f["index"], f["obs_id"], f["detector"], f["mjd_avg"], f["lam_um"], json.dumps(f)),
                )

    def _sequence(self, r):
        if not r:
            return None
        d = dict(r)
        d["params"] = json.loads(d["params"])
        d["meta"] = json.loads(d["meta"])
        rows = self._conn().execute("SELECT meta FROM frames WHERE sequence_id=? ORDER BY idx", (d["id"],)).fetchall()
        d["frames"] = [json.loads(x["meta"]) for x in rows]
        return d

    def get_sequence(self, seq_id: str):
        return self._sequence(self._conn().execute("SELECT * FROM sequences WHERE id=?", (seq_id,)).fetchone())

    def get_sequence_by_key(self, sequence_key: str):
        return self._sequence(self._conn().execute("SELECT * FROM sequences WHERE sequence_key=?", (sequence_key,)).fetchone())

    def latest_sequence_for(self, request_key: str, max_age_s: float | None = None):
        r = self._conn().execute(
            "SELECT * FROM sequences WHERE request_key=? ORDER BY created_at DESC LIMIT 1", (request_key,)
        ).fetchone()
        if r and max_age_s is not None and (time.time() - r["created_at"]) > max_age_s:
            return None
        return self._sequence(r)

    # ---- paylaşılan gözlemler --------------------------------------------------------
    def put_shared(self, rec: dict) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO shared_observations(id, sequence_id, title, note, marks, view, edit_token_hash, app_version, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (rec["id"], rec["sequence_id"], rec["title"], rec["note"], json.dumps(rec["marks"]), json.dumps(rec["view"]),
                 rec["edit_token_hash"], rec["app_version"], rec["created_at"], rec["updated_at"]),
            )

    def update_shared(self, shared_id: str, title: str, note: str, marks: list, view: dict) -> None:
        with self.tx() as c:
            c.execute("UPDATE shared_observations SET title=?, note=?, marks=?, view=?, updated_at=? WHERE id=?",
                      (title, note, json.dumps(marks), json.dumps(view), time.time(), shared_id))

    def delete_shared(self, shared_id: str) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM shared_observations WHERE id=?", (shared_id,))

    def get_shared(self, shared_id: str):
        r = self._conn().execute("SELECT * FROM shared_observations WHERE id=?", (shared_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["marks"] = json.loads(d["marks"])
        d["view"] = json.loads(d["view"])
        return d

    # ---- öğretici görevler -----------------------------------------------------------
    def replace_tutorials(self, tutorials: list[dict]) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM tutorials")
            for i, t in enumerate(tutorials):
                c.execute("INSERT INTO tutorials(id, position, data) VALUES (?,?,?)", (t["id"], i, json.dumps(t)))

    def list_tutorials(self) -> list[dict]:
        rows = self._conn().execute("SELECT data FROM tutorials ORDER BY position").fetchall()
        return [json.loads(r["data"]) for r in rows]

    # ---- hazır hedef -> dizi eşlemesi (meta) -----------------------------------------
    def set_meta(self, key: str, value) -> None:
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", (key, json.dumps(value)))

    def get_meta(self, key: str, default=None):
        r = self._conn().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default
