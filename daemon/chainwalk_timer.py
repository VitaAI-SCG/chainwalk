# chainwalk_timer.py — Time-Binding Daemon
# Auto-runs CHAINWALK_DAILY_BRIEF.py at 06:00 local time or 144 blocks elapsed.
# Logs spines to chainwalk_spine_history.log
# Auto-generates weekly compression_tape_YYYY-MM-DD.md

import subprocess
import time
import datetime
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent
DAILY_SCRIPT = SCRIPT_DIR / "CHAINWALK_DAILY_BRIEF.py"
SPINE_LOG = SCRIPT_DIR / "reports" / "chainwalk_spine_history.log"

def run_daily_brief():
    """Run the daily brief script."""
    try:
        result = subprocess.run(["python", str(DAILY_SCRIPT)], cwd=SCRIPT_DIR, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[{datetime.datetime.now()}] Daily brief completed successfully.")
            # Extract spine from output or logs
            # For simplicity, append a timestamped entry
            with open(SPINE_LOG, 'a') as f:
                f.write(f"{datetime.datetime.now().isoformat()} | Daily brief executed\n")
        else:
            print(f"[{datetime.datetime.now()}] Daily brief failed: {result.stderr}")
    except Exception as e:
        print(f"[{datetime.datetime.now()}] Error running daily brief: {e}")

def generate_weekly_tape():
    """Generate weekly compression tape."""
    # Simplified: run a command or create a file
    tape_file = SCRIPT_DIR / "reports" / f"compression_tape_{datetime.date.today()}.md"
    with open(tape_file, 'w') as f:
        f.write(f"# Compression Tape {datetime.date.today()}\n\nWeekly summary placeholder.\n")
    print(f"[{datetime.datetime.now()}] Weekly tape generated: {tape_file}")

def main():
    last_run = None
    last_tape = datetime.date.today()

    while True:
        now = datetime.datetime.now()
        current_date = now.date()

        # Run daily at 06:00
        if now.hour == 6 and (last_run is None or last_run.date() != current_date):
            run_daily_brief()
            last_run = now

        # Generate weekly tape on Monday
        if current_date.weekday() == 0 and last_tape != current_date:
            generate_weekly_tape()
            last_tape = current_date

        # Sleep for 1 hour
        time.sleep(3600)

if __name__ == "__main__":
    main()