from ultralytics import YOLO
import cv2

model = YOLO("yolov8n.pt")

cap = cv2.VideoCapture(0)

light_on = False

while True:
    ret, frame = cap.read()

    results = model(frame)

    person_detected = False

    for r in results:
        for box in r.boxes:
            cls = int(box.cls[0])

            if model.names[cls] == "person":
                person_detected = True

    if person_detected and not light_on:
        print("Person Detected")
        print("Street Light ON")
        light_on = True

    elif not person_detected and light_on:
        print("No Person Detected")
        print("Street Light OFF")
        light_on = False

    cv2.imshow("Smart Street Light AI", results[0].plot())

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()