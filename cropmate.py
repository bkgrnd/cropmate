import sys
import os
import json
import time
import threading

from minescript import (
    echo,
    execute,
    player,
    player_press_left,
    player_press_right,
    player_press_attack,
    EventQueue,
    EventType,
)

REWARPS_FILE      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cropmate_rewarps.json")
DROP_THRESHOLD    = 0.5    # Y drop to detect end of row
WAIT_AFTER_DROP   = 1.0    # seconds to wait between rows
REWARP_DELAY      = 1.0    # seconds to wait before firing rewarp
POLL_INTERVAL     = 0.05   # position check frequency
REWARP_TOLERANCE  = 0.5    # max coord delta to trigger rewarp

KEY_GRAVE = 96  # ` to toggle pause
KEY_Q     = 81
MOD_CTRL  = 2

_paused = threading.Event()
_quit   = threading.Event()


def release_all():
    player_press_left(False)
    player_press_right(False)
    player_press_attack(False)


def load_rewarps():
    if not os.path.exists(REWARPS_FILE):
        return []
    try:
        with open(REWARPS_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_rewarps(points):
    with open(REWARPS_FILE, "w") as f:
        json.dump(points, f, indent=2)


def add_rewarp_point():
    pos = player().position
    px, pz = round(pos[0], 2), round(pos[2], 2)
    points = load_rewarps()
    label = f"Point {len(points) + 1}"
    points.append({"x": px, "z": pz, "label": label})
    save_rewarps(points)
    echo(f"§a[CropMate] Rewarp added: {label} at X:{px} Z:{pz}")


def list_rewarps():
    points = load_rewarps()
    if not points:
        echo("§e[CropMate] No rewarp points saved.")
        return
    for i, p in enumerate(points, 1):
        echo(f"§7{i}. {p['label']} — X:{p['x']} Z:{p['z']}")


def clear_rewarps():
    save_rewarps([])
    echo("§c[CropMate] Rewarp points cleared.")


def check_rewarps(px, pz, triggered_set):
    points = load_rewarps()
    now_inside = set()
    for i, p in enumerate(points):
        if abs(px - p["x"]) <= REWARP_TOLERANCE and abs(pz - p["z"]) <= REWARP_TOLERANCE:
            now_inside.add(i)
            if i not in triggered_set:
                time.sleep(REWARP_DELAY)
                # re-check position after delay to confirm we're still at the rewarp point
                pos = player().position
                if abs(pos[0] - p["x"]) <= REWARP_TOLERANCE and abs(pos[2] - p["z"]) <= REWARP_TOLERANCE:
                    echo(f"§b[CropMate] Rewarp! ({p['label']})")
                    execute("warp garden")
    return now_inside


def sleep_interruptible(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _quit.is_set():
            return True
        time.sleep(POLL_INTERVAL)
    return False


def wait_for_elevation_drop(last_y):
    while True:
        if _quit.is_set():
            return last_y, True
        if _paused.is_set():
            release_all()
            while _paused.is_set():
                if _quit.is_set():
                    return last_y, True
                time.sleep(POLL_INTERVAL)
            return player().position[1], False
        current_y = player().position[1]
        if last_y - current_y > DROP_THRESHOLD:
            return current_y, False
        last_y = current_y
        time.sleep(POLL_INTERVAL)


def key_listener_thread():
    with EventQueue() as eq:
        eq.register_key_listener()
        while not _quit.is_set():
            try:
                event = eq.get(timeout=0.2)
            except Exception:
                continue
            if event is None or event.type != EventType.KEY or event.action != 1:
                continue
            if event.key == KEY_GRAVE:
                if _paused.is_set():
                    _paused.clear()
                    echo("§a[CropMate] Resumed")
                else:
                    _paused.set()
                    echo("§e[CropMate] Paused")
            elif event.key == KEY_Q and (event.modifiers & MOD_CTRL):
                _quit.set()


def run_macro(macro_num):
    if macro_num == 1:
        first_label, second_label = "A", "D"
        def press_first(on):  player_press_left(on);  player_press_right(not on)
        def press_second(on): player_press_right(on); player_press_left(not on)
    else:
        first_label, second_label = "D", "A"
        def press_first(on):  player_press_right(on); player_press_left(not on)
        def press_second(on): player_press_left(on);  player_press_right(not on)

    echo(f"§a[CropMate] Macro {macro_num} ({first_label}→{second_label})  ` = pause  Ctrl+Q = quit")

    triggered_set = set()
    last_y = player().position[1]
    player_press_attack(True)

    while not _quit.is_set():
        if _paused.is_set():
            time.sleep(POLL_INTERVAL)
            continue

        press_first(True)
        last_y, quit_now = wait_for_elevation_drop(last_y)
        press_first(False)
        if quit_now: break
        if _paused.is_set(): continue
        if sleep_interruptible(WAIT_AFTER_DROP): break
        if _paused.is_set(): continue
        pos = player().position
        triggered_set = check_rewarps(pos[0], pos[2], triggered_set)
        last_y = pos[1]

        if _paused.is_set(): continue

        press_second(True)
        last_y, quit_now = wait_for_elevation_drop(last_y)
        press_second(False)
        if quit_now: break
        if _paused.is_set(): continue
        if sleep_interruptible(WAIT_AFTER_DROP): break
        if _paused.is_set(): continue
        pos = player().position
        triggered_set = check_rewarps(pos[0], pos[2], triggered_set)
        last_y = pos[1]


def main():
    args = sys.argv[1:]
    if not args:
        return

    cmd = args[0].lower()

    if cmd == "addrewarp":    add_rewarp_point(); return
    if cmd == "listrewarp":   list_rewarps();     return
    if cmd == "clearrewarp":  clear_rewarps();    return
    if cmd not in ("1", "2"): return

    listener = threading.Thread(target=key_listener_thread, daemon=True)
    listener.start()

    try:
        run_macro(int(cmd))
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        _quit.set()
        release_all()
        echo("§c[CropMate] Stopped.")
        listener.join(timeout=1.0)


main()
