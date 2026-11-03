#!/usr/bin/env python3
"""
Backfills missing git commits between Oct 10, 2026 and Nov 1, 2026.
Matches the existing repository style:
- Author: connelldan <danielcconnell@gmail.com>
- Message: Auto-commit: <Date>
- File: .last_commit_timestamp
"""

import os
import sys
import random
import subprocess
from datetime import datetime, timedelta
import zoneinfo

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
TZ = zoneinfo.ZoneInfo("America/Denver")

def format_date_str(dt: datetime) -> str:
    # Matches macOS 'date' output: e.g. 'Sat Oct 10 14:23:18 MDT 2026'
    day_str = f"{dt.day:2d}"
    return f"{dt.strftime('%a %b')} {day_str} {dt.strftime('%H:%M:%S %Z %Y')}"

def run_git_cmd(cmd, env_vars=None):
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)
    res = subprocess.run(cmd, cwd=REPO_DIR, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nStderr: {res.stderr}")
    return res.stdout.strip()

def generate_schedule(start_date: datetime, end_date: datetime):
    # Fixed seed for reproducibility and natural distribution
    rng = random.Random(1337)
    schedule = []
    
    cur = start_date
    while cur <= end_date:
        weekday = cur.weekday()
        if weekday in (5, 6): # Weekend
            count = rng.choices([0, 1, 2, 3], weights=[0.25, 0.35, 0.25, 0.15])[0]
        else: # Weekday
            count = rng.choices([1, 2, 3, 4, 5, 6], weights=[0.10, 0.25, 0.30, 0.20, 0.10, 0.05])[0]
        
        if count > 0:
            # Generate random minute offsets between 08:30 (510 min) and 22:30 (1350 min)
            possible_minutes = sorted(rng.sample(range(510, 1350), count))
            for m in possible_minutes:
                hour = m // 60
                minute = m % 60
                second = rng.randint(0, 59)
                commit_dt = cur.replace(hour=hour, minute=minute, second=second, microsecond=0)
                schedule.append(commit_dt)
                
        cur += timedelta(days=1)
    return schedule

def main():
    dry_run = "--dry-run" in sys.argv
    start_date = datetime(2026, 10, 10, tzinfo=TZ)
    end_date = datetime(2026, 11, 1, tzinfo=TZ)
    
    schedule = generate_schedule(start_date, end_date)
    print(f"Total commits scheduled: {len(schedule)}")
    
    timestamp_file = os.path.join(REPO_DIR, ".last_commit_timestamp")
    
    for i, commit_dt in enumerate(schedule, 1):
        date_str = format_date_str(commit_dt)
        git_iso_date = commit_dt.strftime("%Y-%m-%d %H:%M:%S %z")
        commit_msg = f"Auto-commit: {date_str}"
        
        if dry_run:
            print(f"[{i}/{len(schedule)}] DRY RUN: {commit_msg} (GIT_DATE={git_iso_date})")
        else:
            with open(timestamp_file, "w") as f:
                f.write(f"Timestamp: {date_str}\n")
            
            run_git_cmd(["git", "add", ".last_commit_timestamp"])
            env_vars = {
                "GIT_AUTHOR_DATE": git_iso_date,
                "GIT_COMMITTER_DATE": git_iso_date,
            }
            run_git_cmd(["git", "commit", "-m", commit_msg], env_vars=env_vars)
            if i % 10 == 0 or i == len(schedule):
                print(f"Committed [{i}/{len(schedule)}]: {commit_msg}")

    if not dry_run:
        print("\nBackfill complete! Ready to push.")

if __name__ == "__main__":
    main()
