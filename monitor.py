#!/usr/bin/env python3
"""
BioNode V2.1 — mission monitor dashboard
========================================

READS the latest reading from the shared mission database and serves a live
dashboard. Does NOT touch the I2C bus — logger.py is the sole bus owner, so the
two run side by side with zero contention.

Also provides activity start/end marking: pressing the dashboard button writes
an 'activity_change' event into the same database, so roving segments (EVA sim,
workout, etc.) can be bounded and later sliced out of the timeline.

  logger.py  -> owns the I2C bus, WRITES readings + power_restart events
  monitor.py -> READS latest reading, WRITES activity events only
  (Two writers to one SQLite file is safe under WAL, which is already enabled.)

Design notes:
  * SCD30 is PRIMARY CO2 (co2_ppm). SGP30 eCO2 is a PROXY, shown small + labelled.
  * The "current activity" is tracked in the DB via activity_change events, so it
    survives a monitor restart — state is not held in memory.
  * Reads the same fixed mission file the logger writes: data/aat112_mission.db.

Run manually:
    source ~/bio_node_v2/.venv/bin/activate
    python3 monitor.py
Then open http://<pi-ip>:5001  (port 5001 to avoid clashing with app.py on 5000)
"""

from __future__ import annotations

import datetime
import sqlite3
from typing import Optional

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

DB_PATH = "/home/aris/bio_node_v2/data/aat112_mission.db"

# Activities the dashboard can start. 'none' = nothing running (idle/chamber).
ACTIVITIES = ["eva", "exercise", "teamwork", "meal", "rest", "work", "sleep"]


# -----------------------------
# DB HELPERS (read-mostly; one write path for activity events)
# -----------------------------
def _connect() -> sqlite3.Connection:
    # Short timeout so a momentary logger write-lock doesn't hang the dashboard.
    conn = sqlite3.connect(DB_PATH, timeout=2.0)
    conn.row_factory = sqlite3.Row
    return conn


def get_latest_reading() -> Optional[dict]:
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT * FROM readings ORDER BY reading_id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"read latest error: {e}")
        return None


def get_current_activity() -> str:
    """
    Current activity = the label of the most recent activity_change event.
    Held in the DB, not memory, so it survives a monitor restart.
    'none' means no activity is currently running.
    """
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT label FROM events WHERE event_type = 'activity_change' "
            "ORDER BY event_id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row and row["label"]:
            return row["label"]
        return "none"
    except Exception as e:
        print(f"read activity error: {e}")
        return "none"


def get_active_session_id() -> Optional[int]:
    """Newest session — the one the logger is currently writing to."""
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT session_id FROM sessions ORDER BY session_id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return row["session_id"] if row else None
    except Exception as e:
        print(f"read session error: {e}")
        return None


def write_activity_event(label: str) -> bool:
    """
    Write an activity_change event. label is an activity name to START one,
    or 'none' to END the current activity. Attaches to the active session.
    """
    session_id = get_active_session_id()
    if session_id is None:
        return False
    try:
        conn = _connect()
        ts = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        conn.execute(
            "INSERT INTO events (session_id, timestamp_utc, event_type, label) "
            "VALUES (?, ?, 'activity_change', ?)",
            (session_id, ts, label),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"write activity error: {e}")
        return False


# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
def index():
    return render_template_string(PAGE, activities=ACTIVITIES)


@app.route("/api/latest")
def api_latest():
    r = get_latest_reading()
    activity = get_current_activity()

    if r is None:
        return jsonify({"ok": False, "activity": activity})

    # Staleness: how old is the newest row? If the logger stopped, this grows.
    stale_seconds = None
    try:
        t = datetime.datetime.strptime(r["timestamp_utc"], "%Y-%m-%d %H:%M:%S")
        t = t.replace(tzinfo=datetime.timezone.utc)
        stale_seconds = (
            datetime.datetime.now(datetime.timezone.utc) - t
        ).total_seconds()
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "activity": activity,
        "stale_seconds": stale_seconds,
        "timestamp_utc": r["timestamp_utc"],
        # Heroes
        "co2_ppm": r["co2_ppm"],
        "scd30_temp_c": r["scd30_temp_c"],
        "scd30_rh_pct": r["scd30_rh_pct"],
        "bme280_temp_c": r["bme280_temp_c"],
        "bme280_rh_pct": r["bme280_rh_pct"],
        "bme280_pressure_hpa": r["bme280_pressure_hpa"],
        "tvoc_ppb": r["tvoc_ppb"],
        "eco2_proxy_ppm": r["eco2_proxy_ppm"],
        # Secondary
        "lux": r["lux"],
        "heart_rate_bpm": r["heart_rate_bpm"],
        "spo2_pct": r["spo2_pct"],
        "surface_temp_c": r["surface_temp_c"],
    })


@app.route("/api/activity", methods=["POST"])
def api_activity():
    data = request.get_json(silent=True) or {}
    label = data.get("label", "none")
    if label != "none" and label not in ACTIVITIES:
        return jsonify({"ok": False, "error": "unknown activity"}), 400
    ok = write_activity_event(label)
    return jsonify({"ok": ok, "activity": get_current_activity()})


# -----------------------------
# PAGE
# -----------------------------
PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>BioNode V2.1 — AAT-112 Monitor</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { font-family: Arial, sans-serif; background:#0f172a; color:#e5e7eb;
         margin:0; padding:20px; }
  h1 { margin:0 0 4px; font-size:1.5rem; }
  .sub { color:#94a3b8; font-size:0.85rem; margin-bottom:16px; }

  .co2-hero { background:#1e293b; border-radius:16px; padding:24px; margin-bottom:16px;
              border:2px solid #334155; }
  .co2-hero .label { color:#94a3b8; font-size:0.9rem; }
  .co2-hero .value { font-size:3.5rem; font-weight:bold; line-height:1.1; }
  .co2-hero .unit { font-size:1.2rem; color:#94a3b8; }

  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
          gap:12px; margin-bottom:16px; }
  .card { background:#1e293b; border-radius:12px; padding:14px; }
  .card .label { color:#94a3b8; font-size:0.8rem; margin-bottom:4px; }
  .card .value { font-size:1.4rem; font-weight:bold; }
  .card.secondary { opacity:0.75; }
  .card .tag { font-size:0.65rem; color:#f59e0b; }

  .normal { color:#22c55e; } .caution { color:#f59e0b; } .critical { color:#ef4444; }

  .activity-bar { background:#111827; border-radius:12px; padding:16px; margin-bottom:16px; }
  .activity-bar .cur { font-size:1.1rem; margin-bottom:10px; }
  .activity-bar .cur b { color:#38bdf8; }
  button { background:#334155; color:#e5e7eb; border:none; border-radius:8px;
           padding:10px 14px; margin:3px; font-size:0.9rem; cursor:pointer; }
  button:hover { background:#475569; }
  button.end { background:#7f1d1d; } button.end:hover { background:#991b1b; }

  .status { color:#94a3b8; font-size:0.8rem; }
  .stale { color:#ef4444; font-weight:bold; }
</style>
</head>
<body>
  <h1>BioNode V2.1 — AAT-112 Monitor</h1>
  <div class="sub">Live view (reads logged data). SCD30 = primary CO2.</div>

  <div class="co2-hero">
    <div class="label">CO2 (SCD30, NDIR)</div>
    <div class="value" id="co2">--</div>
    <div class="unit">ppm</div>
  </div>

  <div class="activity-bar">
    <div class="cur">Current activity: <b id="activity">none</b></div>
    <div id="activity-buttons">
      {% for a in activities %}
      <button onclick="setActivity('{{a}}')">{{a}}</button>
      {% endfor %}
      <button class="end" onclick="setActivity('none')">END ACTIVITY</button>
    </div>
  </div>

  <div class="grid">
    <div class="card"><div class="label">SCD30 Temp</div><div class="value" id="scd_t">--</div></div>
    <div class="card"><div class="label">SCD30 RH</div><div class="value" id="scd_rh">--</div></div>
    <div class="card"><div class="label">BME280 Pressure</div><div class="value" id="bme_p">--</div></div>
    <div class="card"><div class="label">BME280 Temp</div><div class="value" id="bme_t">--</div></div>
    <div class="card"><div class="label">BME280 RH</div><div class="value" id="bme_rh">--</div></div>
    <div class="card"><div class="label">TVOC (SGP30)</div><div class="value" id="tvoc">--</div></div>
    <div class="card secondary"><div class="label">eCO2 <span class="tag">PROXY</span></div><div class="value" id="eco2">--</div></div>
    <div class="card secondary"><div class="label">Light</div><div class="value" id="lux">--</div></div>
    <div class="card secondary"><div class="label">Heart Rate</div><div class="value" id="hr">--</div></div>
    <div class="card secondary"><div class="label">SpO2</div><div class="value" id="spo2">--</div></div>
    <div class="card secondary"><div class="label">Surface Temp</div><div class="value" id="surf">--</div></div>
  </div>

  <div class="status" id="status">Connecting...</div>

<script>
const CO2_CAUTION = 1000, CO2_CRITICAL = 2000;

function fmt(v, unit, digits) {
  if (v === null || v === undefined) return '--';
  return (digits !== undefined ? Number(v).toFixed(digits) : v) + (unit || '');
}

async function refresh() {
  try {
    const r = await fetch('/api/latest');
    const d = await r.json();
    document.getElementById('activity').textContent = d.activity || 'none';

    if (!d.ok) { document.getElementById('status').textContent =
        'No readings yet — is the logger running?'; return; }

    const co2El = document.getElementById('co2');
    co2El.textContent = fmt(d.co2_ppm, '', 0);
    co2El.className = 'value ' + (d.co2_ppm >= CO2_CRITICAL ? 'critical'
                     : d.co2_ppm >= CO2_CAUTION ? 'caution' : 'normal');

    document.getElementById('scd_t').textContent  = fmt(d.scd30_temp_c, ' °C', 1);
    document.getElementById('scd_rh').textContent = fmt(d.scd30_rh_pct, ' %', 1);
    document.getElementById('bme_p').textContent  = fmt(d.bme280_pressure_hpa, ' hPa', 1);
    document.getElementById('bme_t').textContent  = fmt(d.bme280_temp_c, ' °C', 1);
    document.getElementById('bme_rh').textContent = fmt(d.bme280_rh_pct, ' %', 1);
    document.getElementById('tvoc').textContent   = fmt(d.tvoc_ppb, ' ppb', 0);
    document.getElementById('eco2').textContent   = fmt(d.eco2_proxy_ppm, ' ppm', 0);
    document.getElementById('lux').textContent    = fmt(d.lux, ' lux', 0);
    document.getElementById('hr').textContent     = fmt(d.heart_rate_bpm, ' bpm', 0);
    document.getElementById('spo2').textContent   = fmt(d.spo2_pct, ' %', 0);
    document.getElementById('surf').textContent   = fmt(d.surface_temp_c, ' °C', 1);

    const st = document.getElementById('status');
    if (d.stale_seconds !== null && d.stale_seconds > 10) {
      st.innerHTML = '<span class="stale">STALE: last reading ' +
        Math.round(d.stale_seconds) + 's ago — logger may be down</span>';
    } else {
      st.textContent = 'Live · last reading ' + d.timestamp_utc + ' UTC';
    }
  } catch (e) {
    document.getElementById('status').textContent = 'Error: ' + e;
  }
}

async function setActivity(label) {
  try {
    await fetch('/api/activity', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({label})
    });
    refresh();
  } catch (e) { alert('Failed to set activity: ' + e); }
}

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
