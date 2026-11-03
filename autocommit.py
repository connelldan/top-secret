#!/usr/bin/env python3
"""
Autonomous commit scheduler for maintaining GitHub contribution activity.
- Runs periodically (e.g. via macOS LaunchAgent).
- Generates a realistic, randomized daily commit plan with no obvious patterns.
- Weekdays: 1 to 6 commits distributed between ~08:30 and 22:30.
- Weekends: 0 to 3 commits.
- Jittered minutes and seconds for human-like timing.
- Handles sleep/wake gracefully and avoids bulk-commit bursts.
"""

import os
import sys
import json
import random
import argparse
import subprocess
from datetime import datetime, timedelta
import zoneinfo

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(REPO_DIR, ".scheduler_state.json")
LOG_FILE = os.path.join(REPO_DIR, "autocommit.log")
TZ = zoneinfo.ZoneInfo("America/Denver")

def log(msg: str):
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    line = f"[{timestamp}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"Failed to write to log file: {e}", file=sys.stderr)

def format_date_str(dt: datetime) -> str:
    # Matches macOS 'date' output: e.g. 'Mon Nov  2 09:14:22 MST 2026'
    day_str = f"{dt.day:2d}"
    return f"{dt.strftime('%a %b')} {day_str} {dt.strftime('%H:%M:%S %Z %Y')}"

def run_cmd(cmd, env_vars=None):
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)
    res = subprocess.run(cmd, cwd=REPO_DIR, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {' '.join(cmd)}\nStderr: {res.stderr}\nStdout: {res.stdout}")
    return res.stdout.strip()

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            log(f"Warning: Could not read state file ({e}), resetting state.")
    return {"date": "", "planned_times": [], "executed_times": []}

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def generate_daily_plan(date_obj: datetime) -> list:
    weekday = date_obj.weekday()
    if weekday in (5, 6): # Saturday, Sunday
        count = random.choices([0, 1, 2, 3], weights=[0.25, 0.35, 0.25, 0.15])[0]
    else: # Monday through Friday
        count = random.choices([1, 2, 3, 4, 5, 6], weights=[0.10, 0.25, 0.30, 0.20, 0.10, 0.05])[0]

    planned = []
    if count > 0:
        # Window: 08:30 (510 min) to 22:30 (1350 min)
        minutes_sample = sorted(random.sample(range(510, 1350), count))
        for m in minutes_sample:
            hour = m // 60
            minute = m % 60
            sec = random.randint(0, 59)
            dt = date_obj.replace(hour=hour, minute=minute, second=sec, microsecond=0)
            planned.append(dt.isoformat())
    return planned

def make_commit(dt: datetime, dry_run=False):
    date_str = format_date_str(dt)
    commit_msg = f"Auto-commit: {date_str}"
    timestamp_file = os.path.join(REPO_DIR, ".last_commit_timestamp")

    if dry_run:
        log(f"[DRY-RUN] Would commit: '{commit_msg}'")
        return True

    try:
        with open(timestamp_file, "w") as f:
            f.write(f"Timestamp: {date_str}\n")
        
        run_cmd(["git", "add", ".last_commit_timestamp"])
        run_cmd(["git", "commit", "-m", commit_msg])
        
        # Determine current branch
        branch = run_cmd(["git", "branch", "--show-current"]) or "main"
        run_cmd(["git", "push", "origin", branch])
        log(f"Successfully committed and pushed: '{commit_msg}' to {branch}")
        return True
    except Exception as e:
        log(f"Error during commit/push: {e}")
        return False

def print_status():
    now = datetime.now(TZ)
    state = load_state()
    today_str = now.strftime("%Y-%m-%d")
    
    print(f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    if state.get("date") != today_str:
        print(f"No plan generated yet for today ({today_str}). Run with --run to initialize.")
        return

    planned = state.get("planned_times", [])
    executed = set(state.get("executed_times", []))
    print(f"Plan for {today_str}: {len(planned)} total commits planned, {len(executed)} executed.")
    for i, t_str in enumerate(planned, 1):
        status = "[DONE]" if t_str in executed else "[PENDING]"
        t = datetime.fromisoformat(t_str)
        print(f"  {i}. {t.strftime('%H:%M:%S')} {status}")

def run_scheduler(force=False, dry_run=False):
    now = datetime.now(TZ)
    today_str = now.strftime("%Y-%m-%d")
    state = load_state()

    if state.get("date") != today_str:
        planned = generate_daily_plan(now)
        state = {
            "date": today_str,
            "planned_times": planned,
            "executed_times": []
        }
        save_state(state)
        log(f"Generated new plan for {today_str}: {len(planned)} commits planned.")

    if force:
        log("Forcing commit right now...")
        if make_commit(now, dry_run=dry_run):
            if not dry_run:
                iso_now = now.isoformat()
                state["executed_times"].append(iso_now)
                save_state(state)
        return

    planned_times = state.get("planned_times", [])
    executed_times = set(state.get("executed_times", []))

    # Find pending commits that are due (planned time <= now)
    due = [t_str for t_str in planned_times if datetime.fromisoformat(t_str) <= now and t_str not in executed_times]

    if not due:
        # Check upcoming
        upcoming = [t_str for t_str in planned_times if t_str not in executed_times]
        if upcoming:
            next_due = datetime.fromisoformat(upcoming[0])
            log(f"No commits currently due. Next commit scheduled for {next_due.strftime('%H:%M:%S %Z')}.")
        else:
            log("All planned commits for today have been executed.")
        return

    # To avoid bursting if the computer was asleep all day, execute one due commit per run
    target_iso = due[0]
    log(f"Commit due (scheduled for {datetime.fromisoformat(target_iso).strftime('%H:%M:%S')}). Executing...")
    if make_commit(now, dry_run=dry_run):
        if not dry_run:
            state["executed_times"].append(target_iso)
            save_state(state)

def main():
    parser = argparse.ArgumentParser(description="Git Autocommit Scheduler")
    parser.add_argument("--status", action="store_true", help="Show today's plan and status")
    parser.add_argument("--force", action="store_true", help="Force an immediate commit and push")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without committing or pushing")
    parser.add_argument("--run", action="store_true", default=True, help="Run normal scheduler tick")
    args = parser.parse_args()

    if args.status:
        print_status()
    else:
        run_scheduler(force=args.force, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
