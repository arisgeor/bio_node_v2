# HR capture — independent side-channel (NOT part of BioNode)

Two files, mirroring the logger/monitor split. Fully isolated from BioNode:
own DB (`data/hr_mission.db`), own port (`:5002`), BLE-only (no I2C). A failure
here cannot affect logger.py / monitor.py or the environmental data.

- `hr_logger.py` — sole BLE owner. Captures HR + RR intervals, writes SQLite (WAL, UTC).
- `hr_monitor.py` — live view on `:5002`, latest row only + staleness flag.

Parser validated against crafted 0x2A37 payloads (uint8, uint16, RR present/absent, contact bit).

---

## Install
```bash
pip3 install bleak flask
```

## Test — ONE sitting, tonight. Timebox: 45 minutes.
1. Wear the strap. Wet the contacts (it won't advertise BLE dry / unworn).
2. Terminal A: `python3 hr_logger.py`
   - Within ~20s you should see HR lines printing.
   - If name-match fails: read the printed scan list, copy the strap's MAC into
     `STRAP_ADDRESS` at the top of `hr_logger.py`, rerun.
3. Terminal B: `python3 hr_monitor.py` → open `http://<pi-ip>:5002` on the phone.

**Pass = HR lines print. You're done — you have a bonus channel.**
**If BLE won't connect after ~45 min → STOP.** 

---

## Watch vs Pi — no conflict
Watch ↔ strap = ANT+. Pi ↔ strap = BLE. The HRM-Pro Plus broadcasts both
simultaneously. Keep the watch recording natively — that is the **primary,
guaranteed** log (export FIT → parse with `fitparse` after). The Pi BLE capture
is enhancement only.

## Clocks / merge
`hr_mission.db` uses the Pi system clock in UTC — same convention as
`aat112_mission.db`. The single clock-offset capture you do at seal covers both.
Merge post-hoc by `ts_utc`.

---

## OPTIONAL — only if the test passed and you want it hands-off for 7 days
Independent systemd units so it survives reboot. These do NOT interfere with
BioNode's services (different resources, different files). Skip entirely if unsure.

`/etc/systemd/system/hr_logger.service`
```ini
[Unit]
Description=HR logger (BLE strap)
After=bluetooth.target
[Service]
ExecStart=/usr/bin/python3 /home/pi/bio_node_v2/hr_logger.py
WorkingDirectory=/home/pi/bio_node_v2
Restart=always
RestartSec=5
User=pi
[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/hr_monitor.service`
```ini
[Unit]
Description=HR live view (:5002)
After=network.target
[Service]
ExecStart=/usr/bin/python3 /home/pi/bio_node_v2/hr_monitor.py
WorkingDirectory=/home/pi/bio_node_v2
Restart=always
RestartSec=5
User=pi
[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hr_logger hr_monitor
```
(Adjust paths/user to match your Pi. `*.db` stays gitignored — export the file, not via git.)
