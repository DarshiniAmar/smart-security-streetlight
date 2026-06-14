"""
============================================================
 SMART SECURITY STREETLIGHT — Field Unit
============================================================
 Simulated keys (laptop mode):
   S        → SOS button (hold 3 sec to activate)
   F        → Faint detection (person collapses after SOS)
   M        → Microphone toggle (sound anomaly simulation)
   C        → Clear / area safe
   Q        → Quit

 Sends real-time data to Police Control Room via HTTP/SocketIO
============================================================
"""

import cv2
import time
import threading
import json
import base64
import numpy as np
import requests
from pynput import keyboard as kb

# ─── Try importing YOLO; fall back to mock if not installed ───────────────────
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
    model = YOLO("yolov8n.pt")
    print("[YOLO] Model loaded.")
except Exception:
    YOLO_AVAILABLE = False
    print("[YOLO] Not available — using motion-only detection.")

# =============================================================
# CONFIGURATION
# =============================================================

STREETLIGHT_ID    = "SL-04"
ZONE              = "Zone B - Park Road"
CONTROL_ROOM_URL  = "http://127.0.0.1:5000"

SOS_HOLD_SECONDS  = 3        # hold duration to activate SOS
COOLDOWN_SECONDS  = 60       # lockout after each SOS
FALSE_ALARM_LIMIT = 3        # auto-flag after N false alarms
FAINT_TIMEOUT     = 10       # seconds of no motion after SOS = faint assumed
DOUBLE_SOS_WINDOW = 5        # two SOS presses within N sec = double SOS

# =============================================================
# SHARED STATE  (written by threads, read by main loop)
# =============================================================

state = {
    # key hold tracking
    "s_held":           False,
    "s_hold_start":     None,
    "sos_fired":        False,

    # sensor flags
    "sound_active":     False,
    "faint_mode":       False,
    "area_clear":       False,

    # system
    "cooldown":         False,
    "cooldown_start":   0.0,
    "false_count":      0,
    "last_sos_time":    0.0,
    "alert_level":      "MONITORING",
    "risk_score":       0,
    "person_count":     0,
    "motion_detected":  False,
    "last_motion_time": 0.0,
}

lock = threading.Lock()

# =============================================================
# KEYBOARD LISTENER  (background thread via pynput)
# =============================================================

def on_press(key):
    with lock:
        try:
            ch = key.char.lower()
            if ch == 's' and not state["s_held"]:
                state["s_held"]       = True
                state["s_hold_start"] = time.time()
                state["area_clear"]   = False
            elif ch == 'm':
                state["sound_active"] = not state["sound_active"]
                print(f"[MIC] Sound anomaly: {'ON' if state['sound_active'] else 'OFF'}")
            elif ch == 'f':
                state["faint_mode"] = True
                print("[FAINT] Faint key pressed — person may be unconscious")
            elif ch == 'c':
                state["area_clear"]   = True
                state["faint_mode"]   = False
                state["sound_active"] = False
                print("[CLEAR] Area marked safe")
        except AttributeError:
            pass

def on_release(key):
    with lock:
        try:
            if key.char.lower() == 's':
                state["s_held"]       = False
                state["s_hold_start"] = None
                state["sos_fired"]    = False   # allow next hold to fire
        except AttributeError:
            pass

listener = kb.Listener(on_press=on_press, on_release=on_release)
listener.start()

# =============================================================
# RISK ENGINE
# =============================================================

def calculate_risk(person_count, motion, sos, double_sos, sound, faint):
    score = 0
    if sos:          score += 35
    if faint:        score += 30   # unconscious person = high priority
    if sound:        score += 15
    if person_count > 0: score += 20
    if motion:       score += 10
    if person_count >= 3: score += 10
    if double_sos:   score += 25
    return min(score, 100)

def get_alert_level(score, faint, double_sos):
    if double_sos or (faint and score >= 60):
        return "CRITICAL EMERGENCY"
    if score >= 80:  return "CRITICAL ALERT"
    if score >= 60:  return "HIGH ALERT"
    if score >= 40:  return "MEDIUM ALERT"
    return "LOW / FALSE ALARM"

# =============================================================
# MOTION DETECTION  (frame-difference method)
# =============================================================

prev_gray = [None]   # list so inner function can mutate

def detect_motion(frame):
    gray = cv2.GaussianBlur(
        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)

    if prev_gray[0] is None:
        prev_gray[0] = gray
        return False, frame

    diff    = cv2.absdiff(prev_gray[0], gray)
    thresh  = cv2.dilate(
        cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1],
        None, iterations=2)
    cnts, _ = cv2.findContours(
        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    motion = False
    for c in cnts:
        if cv2.contourArea(c) > 800:
            motion = True
            x, y, w, h = cv2.boundingRect(c)
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 255), 1)

    prev_gray[0] = gray
    return motion, frame

# =============================================================
# YOLO DETECTION
# =============================================================

TRACK_CLASSES = {"person", "knife", "cell phone", "backpack", "handbag"}

def run_yolo(frame):
    """Returns (person_count, annotated_frame, detected_objects)."""
    if not YOLO_AVAILABLE:
        return 0, frame, []

    results      = model(frame, verbose=False)
    person_count = 0
    objects      = []

    for r in results:
        for box in r.boxes:
            cls_name = model.names[int(box.cls[0])]
            if cls_name in TRACK_CLASSES:
                objects.append(cls_name)
                if cls_name == "person":
                    person_count += 1

    annotated = results[0].plot()
    return person_count, annotated, objects

# =============================================================
# DATA SENDER  (posts JSON + JPEG frame to control room)
# =============================================================

def send_to_control_room(frame, payload):
    try:
        _, buf   = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        img_b64  = base64.b64encode(buf).decode("utf-8")
        payload["frame"] = img_b64
        requests.post(
            f"{CONTROL_ROOM_URL}/alert",
            json=payload,
            timeout=2
        )
    except Exception as e:
        print(f"[NET] Control room unreachable: {e}")

# =============================================================
# EVENT LOGGER
# =============================================================

def log_event(alert_level, risk_score, persons, faint, sound):
    line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"{STREETLIGHT_ID} | {ZONE} | {alert_level} | "
            f"Risk:{risk_score} | Persons:{persons} | "
            f"Faint:{faint} | Sound:{sound}\n")
    with open("event_log.txt", "a") as f:
        f.write(line)
    print("[LOG]", line.strip())

# =============================================================
# HUD DRAWING
# =============================================================

def draw_hud(frame, person_count, motion, sound, faint,
             alert_level, risk_score, cooldown_remaining,
             false_count, hold_progress, ctrl_status):

    h, w = frame.shape[:2]

    # ── alert colour bar at top ──
    if "CRITICAL" in alert_level:
        bar_col = (30, 30, 180)
    elif "HIGH" in alert_level:
        bar_col = (20, 100, 200)
    elif "MEDIUM" in alert_level:
        bar_col = (20, 160, 200)
    else:
        bar_col = (40, 120, 40)

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 48), bar_col, -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    cv2.putText(frame, f"SMART STREETLIGHT — {STREETLIGHT_ID} | {ZONE}",
                (8, 18), cv2.FONT_HERSHEY_DUPLEX, 0.5, (255,255,255), 1)
    cv2.putText(frame, alert_level,
                (8, 40), cv2.FONT_HERSHEY_DUPLEX, 0.65, (255,255,255), 1)
    cv2.putText(frame, f"RISK: {risk_score}/100",
                (w - 160, 40), cv2.FONT_HERSHEY_DUPLEX, 0.65, (255,255,255), 1)

    # ── left info panel ──
    info = [
        (f"Persons   : {person_count}",  (0, 220, 0)   if person_count else (200,200,200)),
        (f"Motion    : {'YES' if motion else 'NO'}",
                                          (0,220,220)   if motion else (200,200,200)),
        (f"Sound     : {'YES' if sound else 'NO'}",
                                          (0,180,255)   if sound else (200,200,200)),
        (f"Faint     : {'YES' if faint else 'NO'}",
                                          (80, 80,255)  if faint else (200,200,200)),
        (f"False Alms: {false_count}/{FALSE_ALARM_LIMIT}",
                                          (255,220,0)   if false_count else (200,200,200)),
        (f"Cooldown  : {cooldown_remaining}s",
                                          (255,255,255)),
        (f"Control Rm: {ctrl_status}",    (100,180,255)),
    ]
    for i, (txt, col) in enumerate(info):
        cv2.putText(frame, txt, (8, 75 + i * 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 1)

    # ── SOS progress bar at bottom ──
    bx1, by1, bx2, by2 = 8, h-36, w-8, h-14
    cv2.rectangle(frame, (bx1, by1), (bx2, by2), (50,50,50), -1)
    if hold_progress > 0:
        fill = int((bx2 - bx1) * hold_progress)
        g    = int(255 * (1 - hold_progress))
        r    = int(255 * hold_progress)
        cv2.rectangle(frame, (bx1, by1), (bx1 + fill, by2), (0, g, r), -1)
        bar_txt = (f"SOS HOLD: {hold_progress * SOS_HOLD_SECONDS:.1f}s / {SOS_HOLD_SECONDS}s"
                   if hold_progress < 1.0 else ">>> SOS ACTIVATING <<<")
    elif cooldown_remaining > 0:
        bar_txt = f"COOLDOWN ACTIVE — {cooldown_remaining}s remaining"
    else:
        bar_txt = "Keys:  [S] Hold SOS  |  [M] Sound  |  [F] Faint  |  [C] Clear  |  [Q] Quit"

    cv2.putText(frame, bar_txt, (bx1 + 4, by1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (210,210,210), 1)

    return frame

# =============================================================
# MAIN LOOP
# =============================================================

def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Cannot open camera.")
        return

    print("\n" + "="*52)
    print("  SMART SECURITY STREETLIGHT — FIELD UNIT")
    print(f"  Unit: {STREETLIGHT_ID}  |  Zone: {ZONE}")
    print("="*52)
    print(f"  [S] Hold {SOS_HOLD_SECONDS}s  → SOS alert")
    print("  [M]       → Toggle sound anomaly")
    print("  [F]       → Simulate faint / unconscious")
    print("  [C]       → Mark area clear")
    print("  [Q]       → Quit")
    print("="*52 + "\n")

    sos_fired_this_hold = False

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        now = time.time()

        # quit key via OpenCV
        if cv2.waitKey(1) & 0xFF in (ord('q'), ord('Q')):
            break

        # ── Read shared state safely ──
        with lock:
            s_held       = state["s_held"]
            s_hold_start = state["s_hold_start"]
            sound        = state["sound_active"]
            faint        = state["faint_mode"]
            area_clear   = state["area_clear"]
            cooldown     = state["cooldown"]
            cooldown_s   = state["cooldown_start"]
            false_count  = state["false_count"]
            last_sos     = state["last_sos_time"]

        # ── Cooldown timer ──
        cooldown_remaining = 0
        if cooldown:
            elapsed = now - cooldown_s
            if elapsed >= COOLDOWN_SECONDS:
                with lock:
                    state["cooldown"] = False
                    state["sos_fired"] = False
                cooldown = False
                sos_fired_this_hold = False
                print("[SYSTEM] Cooldown expired — ready.")
            else:
                cooldown_remaining = int(COOLDOWN_SECONDS - elapsed)

        # ── YOLO ──
        person_count, frame, objects = run_yolo(frame)

        # ── Motion detection ──
        motion, frame = detect_motion(frame)
        if motion:
            with lock:
                state["last_motion_time"] = now

        # ── Faint scenario: SOS fired but no motion for FAINT_TIMEOUT seconds ──
        with lock:
            last_motion = state["last_motion_time"]
            sos_active  = state["sos_fired"]

        if sos_active and not motion and (now - last_motion) > FAINT_TIMEOUT:
            with lock:
                if not state["faint_mode"]:
                    state["faint_mode"] = True
                    print("[AUTO-FAINT] No motion detected after SOS — assuming unconscious!")

        # ── SOS hold logic ──
        hold_progress = 0.0

        if s_held and s_hold_start is not None:
            hold_time     = now - s_hold_start
            hold_progress = min(hold_time / SOS_HOLD_SECONDS, 1.0)

            if (hold_time >= SOS_HOLD_SECONDS
                    and not cooldown
                    and not sos_fired_this_hold):

                sos_fired_this_hold = True

                with lock:
                    state["sos_fired"]    = True
                    state["last_motion_time"] = now

                double_sos  = (now - last_sos) <= DOUBLE_SOS_WINDOW
                risk_score  = calculate_risk(
                    person_count, motion, True, double_sos, sound, faint)
                alert_level = get_alert_level(risk_score, faint, double_sos)

                with lock:
                    state["last_sos_time"] = now
                    state["alert_level"]   = alert_level
                    state["risk_score"]    = risk_score
                    state["cooldown"]      = True
                    state["cooldown_start"]= now

                    # false alarm: no person and no motion
                    if not person_count and not motion:
                        state["false_count"] += 1
                        false_count = state["false_count"]
                        print(f"[WARN] False alarm #{false_count}")
                        if false_count >= FALSE_ALARM_LIMIT:
                            print("[ALERT] *** INSPECTION REQUEST GENERATED ***")

                cooldown           = True
                cooldown_remaining = COOLDOWN_SECONDS

                print(f"\n{'='*50}")
                print(f"  SOS ACTIVATED — {STREETLIGHT_ID}")
                print(f"  Alert Level  : {alert_level}")
                print(f"  Risk Score   : {risk_score}/100")
                print(f"  Persons      : {person_count}")
                print(f"  Objects      : {objects}")
                print(f"  Motion       : {motion}")
                print(f"  Sound        : {sound}")
                print(f"  Faint        : {faint}")
                print(f"  Double SOS   : {double_sos}")
                print(f"{'='*50}\n")

                log_event(alert_level, risk_score, person_count, faint, sound)

                # send to control room
                payload = {
                    "unit":         STREETLIGHT_ID,
                    "zone":         ZONE,
                    "timestamp":    time.strftime("%Y-%m-%d %H:%M:%S"),
                    "alert_level":  alert_level,
                    "risk_score":   risk_score,
                    "person_count": person_count,
                    "objects":      objects,
                    "motion":       motion,
                    "sound":        sound,
                    "faint":        faint,
                    "double_sos":   double_sos,
                }
                threading.Thread(
                    target=send_to_control_room,
                    args=(frame.copy(), payload),
                    daemon=True
                ).start()

        else:
            if not s_held:
                sos_fired_this_hold = False

        # ── Area clear reset ──
        if area_clear:
            with lock:
                state["alert_level"]  = "MONITORING"
                state["risk_score"]   = 0
                state["area_clear"]   = False

        # ── Build HUD ──
        with lock:
            alert_level = state["alert_level"]
            risk_score  = state["risk_score"]
            false_count = state["false_count"]
            faint       = state["faint_mode"]

        # Control room status string
        if false_count >= FALSE_ALARM_LIMIT:
            ctrl_status = "Inspection Required"
        elif "CRITICAL" in alert_level:
            ctrl_status = "Dispatching Units"
        elif "HIGH" in alert_level:
            ctrl_status = "Officer Monitoring"
        elif cooldown:
            ctrl_status = f"Cooldown ({cooldown_remaining}s)"
        else:
            ctrl_status = "Monitoring"

        frame = draw_hud(
            frame, person_count, motion, sound, faint,
            alert_level, risk_score, cooldown_remaining,
            false_count, hold_progress, ctrl_status
        )

        cv2.imshow("Smart Security Streetlight — Field Unit", frame)

    # ── Cleanup ──
    listener.stop()
    cap.release()
    cv2.destroyAllWindows()
    print("\n[SYSTEM] Unit stopped.")
    print(f"Total false alarms logged: {false_count}")


if __name__ == "__main__":
    main()