from ultralytics import YOLO
import cv2
import time

# Load model
model = YOLO("yolov8n.pt")
cap = cv2.VideoCapture(0)

# System state
false_alarm_count = 0
cooldown = False
cooldown_start = 0
COOLDOWN_TIME = 60

print("\n===== SMART STREET LIGHT SYSTEM =====")
print("Press 's' = SOS trigger")
print("Press 'q' = Quit\n")


# Decision Engine
def decide(person, motion, sound):
    if person:
        if motion and sound:
            return "CRITICAL ALERT", "Police notified immediately"
        elif motion:
            return "HIGH PRIORITY ALERT", "Officer monitoring required"
        else:
            return "VERIFICATION REQUIRED", "Voice check initiated"
    else:
        return "POSSIBLE FALSE ALARM", "Logged for review"


while True:

    ret, frame = cap.read()
    if not ret:
        break

    results = model(frame, verbose=False)

    person_detected = any(
        model.names[int(box.cls[0])] == "person"
        for r in results for box in r.boxes
    )

    motion_detected = person_detected  # simplified motion logic
    sound_detected = False             # placeholder

    key = cv2.waitKey(1) & 0xFF
    now = time.time()

    # Exit
    if key == ord('q'):
        break

    # Cooldown check
    if cooldown and (now - cooldown_start < COOLDOWN_TIME):
        cv2.imshow("Smart Street Light", results[0].plot())
        continue
    else:
        cooldown = False

    # SOS trigger (instant press)
    if key == ord('s'):

        print("\n🚨 SOS TRIGGERED")

        status, action = decide(person_detected, motion_detected, sound_detected)

        print("Person :", person_detected)
        print("Motion :", motion_detected)
        print("Sound  :", sound_detected)
        print("STATUS :", status)
        print("ACTION :", action)

        # False alarm tracking
        if not person_detected:
            false_alarm_count += 1
            print("False Alarms:", false_alarm_count)

            if false_alarm_count >= 3:
                print("⚠ INSPECTION REQUEST GENERATED")

        # Start cooldown
        cooldown = True
        cooldown_start = now

    cv2.imshow("Smart Street Light AI", results[0].plot())

# Cleanup
cap.release()
cv2.destroyAllWindows()

print("\nSYSTEM STOPPED")
print("Total False Alarms:", false_alarm_count)