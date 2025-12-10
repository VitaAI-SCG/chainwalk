# INSTALL • CHAINWALK

ChainWalk is a sovereign oracle engine for Bitcoin.  
It reads structure — not price — and outputs the constraint geometry of the protocol each day.

## 1) System Requirements

- Python 3.10+
- Windows, macOS, or Linux
- ~2GB disk for block catalogs (optional for full history)
- Internet access for block headers / mempool queries

## 2) Install

```bash
git clone https://github.com/VitaAI-SCG/chainwalk
cd chainwalk
pip install -r requirements.txt

3) Run the Daily Brief
python CHAINWALK_DAILY_BRIEF.py


Outputs will appear in:

/reports


You will get:

chainwalk_daily_YYYY-MM-DD.md — the APEX deck

chainwalk_post_latest.md — X-ready post

chainwalk_spine_history.log — canonical state vector

alert_latest.md — first irreversible event flag (if any)

4) Optional Tools
python -m utils.compression_tape --days 7
python -m utils.evaluate_outcomes --window-days 90


These produce:

Weekly compression tapes (thread-ready)

Calibration honesty reports

5) Uninstall

Just delete the folder.
ChainWalk does not modify system files.

There is no second best.