"""Shared loading for the QC scripts."""
from __future__ import annotations

import csv
import os


def load_batch(path: str) -> list[dict]:
    if not os.path.exists(path):
        raise SystemExit(f"batch file not found: {path}\n"
                         f"run:  python -m sim.batch --events 600 --seed 261 --out {path}")
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{path} is empty")
    return rows


def load_traces(batch_path: str) -> dict[int, list[tuple[float, float]]]:
    tpath = os.path.splitext(batch_path)[0] + "_traces.csv"
    if not os.path.exists(tpath):
        raise SystemExit(f"traces file not found: {tpath}\n"
                         f"re-run the batch without --no-traces")
    out: dict[int, list[tuple[float, float]]] = {}
    with open(tpath, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(int(r["event_id"]), []).append((float(r["t_s"]), float(r["ph"])))
    return out


def fnum(rows: list[dict], key: str) -> list[float]:
    return [float(r[key]) for r in rows if r.get(key) not in ("", None)]


def chem_source(rows: list[dict]) -> str:
    return rows[0].get("chem_source", "UNKNOWN")
