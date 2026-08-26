#!/usr/bin/env python3
"""
HR live view -- separate broadcast link on :5002.

Reads ONLY the latest row from hr_mission.db. Independent of BioNode's
monitor (:5001). Auto-refreshes every 2s. Includes a staleness flag so you
can see at a glance if the strap dropped.

Requires: pip3 install flask
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template_string

DB_PATH = Path(__file__).parent / "data" / "hr_mission.db"
STALE_SECONDS = 10

app = Flask(__name__)

PAGE = """
<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="2">
<title>HR live</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;background:#111;color:#eee;
     text-align:center;padding-top:14vh;margin:0}
.lbl{color:#999;letter-spacing:.2em;text-transform:uppercase;font-size:.9rem}
.hr{font-size:7rem;font-weight:700;line-height:1}
.stale{color:#e55}.ok{color:#5e5}
.meta{color:#888;margin-top:1.2rem;font-size:.95rem}
</style></head><body>
<div class="lbl">Heart Rate</div>
<div class="hr {{cls}}">{{hr}}</div>
<div class="meta">RR: {{rr}} ms &nbsp;|&nbsp; contact: {{contact}}</div>
<div class="meta">{{age}}s ago &nbsp;|&nbsp; {{ts}}</div>
</body></html>
"""


def latest():
    if not DB_PATH.exists():
        return None
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT ts_utc, hr_bpm, rr_ms, contact FROM hr ORDER BY ts_utc DESC LIMIT 1"
    ).fetchone()
    con.close()
    return row


@app.route("/")
def index():
    row = latest()
    if row is None:
        return render_template_string(
            PAGE, hr="--", rr="--", contact="--", age="--", ts="no data", cls="stale"
        )
    ts = datetime.fromisoformat(row["ts_utc"])
    age = int((datetime.now(timezone.utc) - ts).total_seconds())
    cls = "stale" if age > STALE_SECONDS else "ok"
    return render_template_string(
        PAGE,
        hr=row["hr_bpm"],
        rr=row["rr_ms"] or "--",
        contact=row["contact"] if row["contact"] is not None else "--",
        age=age,
        ts=row["ts_utc"],
        cls=cls,
    )


@app.route("/api")
def api():
    row = latest()
    if row is None:
        return jsonify({"status": "no_data"})
    ts = datetime.fromisoformat(row["ts_utc"])
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return jsonify(
        {
            "ts_utc": row["ts_utc"],
            "hr_bpm": row["hr_bpm"],
            "rr_ms": row["rr_ms"],
            "contact": row["contact"],
            "age_s": round(age, 1),
            "stale": age > STALE_SECONDS,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
