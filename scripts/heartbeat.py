#!/usr/bin/env python3
"""
EasyWay Quit Smoking Coach - Heartbeat Scheduler
Zero 3rd-party dependencies (Python standard library only).
Evaluates whether a proactive coaching check-in should be triggered.
"""

import argparse
import json
import os
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path


def get_timezone(tz_name: str) -> timezone:
    """Return timezone object with fallback to UTC+8 for Asia/Shanghai."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception:
        if tz_name in ("Asia/Shanghai", "PRC", "Asia/Chongqing", "CST"):
            return timezone(timedelta(hours=8))
        return timezone.utc


def parse_iso(dt_str: str, tz: timezone) -> datetime:
    """Parse ISO8601 string safely into a timezone-aware datetime."""
    if not dt_str:
        return None
    # Handle 'Z' suffix compatibility across Python versions
    clean_str = dt_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


def is_in_quiet_hours(now: datetime, quiet_cfg: dict) -> bool:
    """Check if current time falls within quiet hours (supports overnight spans)."""
    start_str = quiet_cfg.get("start", "23:00")
    end_str = quiet_cfg.get("end", "07:30")
    try:
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        start_t = time(sh, sm)
        end_t = time(eh, em)
        now_t = now.time()

        if start_t <= end_t:
            return start_t <= now_t < end_t
        else:
            # Overnight span, e.g. 23:00 -> 07:30
            return now_t >= start_t or now_t < end_t
    except Exception:
        return False


def calculate_elapsed_text(delta: timedelta) -> str:
    """Format timedelta into natural Chinese duration text."""
    total_seconds = max(0, int(delta.total_seconds()))
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    if days > 0:
        parts = [f"{days}天"]
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        return "".join(parts)
    elif hours > 0:
        if minutes > 0:
            return f"{hours}小时{minutes}分钟"
        return f"{hours}小时"
    else:
        return f"{minutes}分钟"


def determine_stage(total_seconds: int) -> int:
    """
    Determine current Easyway stage:
    Stage 1: 0–24 hours (0–86,400s) -> 小怪兽初饿期
    Stage 2: Days 2–3 (86,400–259,200s) -> 尼古丁清空期
    Stage 3: Days 4–21 (259,200–1,814,400s) -> 心理巩固期
    Stage 4: 21+ days (>= 1,814,400s) -> 自由非吸烟者
    """
    if total_seconds < 86400:
        return 1
    elif total_seconds < 3 * 86400:
        return 2
    elif total_seconds < 21 * 86400:
        return 3
    else:
        return 4


def init_state(target_path: Path, script_dir: Path) -> int:
    """Initialize state.json from template."""
    template_path = script_dir.parent / "templates" / "state.example.json"
    if not template_path.exists():
        print(f"Error: Template not found at {template_path}", file=sys.stderr)
        return 1

    if target_path.exists():
        print(f"State file already exists at {target_path}. Skipping initialization.")
        return 0

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(template_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Set initial start time to now and next check to now + 45min
    tz = get_timezone(data.get("timezone", "Asia/Shanghai"))
    now = datetime.now(tz)
    next_check = now + timedelta(minutes=45)
    data["quit_started_at"] = now.isoformat()
    data["next_check_at"] = next_check.isoformat()

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Initialized state file successfully at: {target_path}")
    return 0


def evaluate_heartbeat(state: dict, now: datetime, state_path: Path) -> dict:
    """
    Evaluate state rules in strict order:
    1. active is true
    2. not in quiet_hours
    3. not in paused_until
    4. unread_streak < 2
    5. now >= next_check_at
    """
    # 1. active check
    if not state.get("active", False):
        return {"should_trigger": False, "reason": "inactive"}

    # 2. quiet_hours check
    quiet_cfg = state.get("quiet_hours", {})
    if is_in_quiet_hours(now, quiet_cfg):
        return {"should_trigger": False, "reason": "quiet_hours"}

    # 3. paused_until check
    tz = now.tzinfo
    paused_until_str = state.get("paused_until")
    if paused_until_str:
        paused_dt = parse_iso(paused_until_str, tz)
        if paused_dt and now < paused_dt:
            return {"should_trigger": False, "reason": f"paused_until_{paused_until_str}"}

    # 4. unread_streak check (backoff if >= 2)
    unread_streak = state.get("unread_streak", 0)
    if unread_streak >= 2:
        return {"should_trigger": False, "reason": f"unread_streak_backoff(streak={unread_streak})"}

    # 5. next_check_at check
    next_check_str = state.get("next_check_at")
    if not next_check_str:
        return {"should_trigger": False, "reason": "not_scheduled"}
    next_check_dt = parse_iso(next_check_str, tz)
    if next_check_dt and now < next_check_dt:
        return {"should_trigger": False, "reason": "not_due_yet"}

    # All checks passed -> trigger check-in
    quit_started_str = state.get("quit_started_at")
    if quit_started_str:
        quit_started_dt = parse_iso(quit_started_str, tz)
        delta = now - quit_started_dt
    else:
        delta = timedelta(seconds=0)

    total_seconds = max(0, int(delta.total_seconds()))
    elapsed_text = calculate_elapsed_text(delta)
    stage = determine_stage(total_seconds)

    return {
        "should_trigger": True,
        "elapsed_text": elapsed_text,
        "stage": stage,
        "state_path": str(state_path)
    }


def main():
    parser = argparse.ArgumentParser(description="EasyWay Quit Smoking Coach Heartbeat Evaluator")
    parser.add_argument("--state-path", type=str, help="Path to state.json (defaults to EASYWAY_STATE_PATH env)")
    parser.add_argument("--init", action="store_true", help="Initialize state file from template")
    parser.add_argument("--dry-run", action="store_true", help="Run heartbeat evaluation in simulation mode")
    parser.add_argument(
        "--mock-scenario",
        choices=["not_due", "quiet", "due"],
        help="Simulate a scenario for --dry-run: 'not_due', 'quiet', or 'due'"
    )
    parser.add_argument("--mock-now", type=str, help="Override current time for testing (ISO format)")

    args = parser.parse_args()
    script_dir = Path(__file__).resolve().parent

    state_path_env = args.state_path or os.environ.get("EASYWAY_STATE_PATH")
    if not state_path_env:
        # If running mock scenario in dry-run, use a virtual default path
        if args.dry_run and args.mock_scenario:
            state_path = script_dir.parent / "templates" / "state.example.json"
        else:
            print("Error: State path not provided. Set EASYWAY_STATE_PATH or pass --state-path.", file=sys.stderr)
            sys.exit(1)
    else:
        state_path = Path(state_path_env).resolve()

    if args.init:
        code = init_state(state_path, script_dir)
        sys.exit(code)

    # Load state
    if not state_path.exists():
        # In dry run with mock scenario, fallback to example template if target doesn't exist
        fallback_template = script_dir.parent / "templates" / "state.example.json"
        if args.dry_run and fallback_template.exists():
            state_path = fallback_template
        else:
            print(f"Error: State file not found at {state_path}", file=sys.stderr)
            sys.exit(1)

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        print(f"Error reading state file {state_path}: {e}", file=sys.stderr)
        sys.exit(1)

    tz = get_timezone(state.get("timezone", "Asia/Shanghai"))
    if args.mock_now:
        now = parse_iso(args.mock_now, tz)
    else:
        now = datetime.now(tz)

    # Apply mock scenario adjustments if specified
    if args.dry_run and args.mock_scenario:
        if args.mock_scenario == "not_due":
            state["active"] = True
            # Quiet hours: set to night so daytime won't hit
            state["quiet_hours"] = {"start": "23:00", "end": "07:30"}
            # Make sure now is daytime (e.g. 15:00) and next_check_at is in the future (+30m)
            now = now.replace(hour=15, minute=0, second=0)
            state["next_check_at"] = (now + timedelta(minutes=30)).isoformat()
            state["unread_streak"] = 0
            state["paused_until"] = None
        elif args.mock_scenario == "quiet":
            state["active"] = True
            # Set now to 02:00 (during default 23:00-07:30 quiet hours)
            now = now.replace(hour=2, minute=0, second=0)
            state["quiet_hours"] = {"start": "23:00", "end": "07:30"}
            state["next_check_at"] = (now - timedelta(minutes=10)).isoformat()
            state["unread_streak"] = 0
            state["paused_until"] = None
        elif args.mock_scenario == "due":
            state["active"] = True
            # Set now to daytime (15:00) outside quiet hours, next_check_at in the past (-5m)
            now = now.replace(hour=15, minute=0, second=0)
            state["quiet_hours"] = {"start": "23:00", "end": "07:30"}
            state["quit_started_at"] = (now - timedelta(hours=3, minutes=20)).isoformat()
            state["next_check_at"] = (now - timedelta(minutes=5)).isoformat()
            state["unread_streak"] = 0
            state["paused_until"] = None

    result = evaluate_heartbeat(state, now, state_path)

    # Output JSON directly to stdout
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
