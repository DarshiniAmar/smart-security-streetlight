# SMART SECURITY STREET LIGHT - AI DECISION ENGINE

# Sensor Inputs
sos_pressed = True
person_detected = True 
motion_detected = True 
sound_detected = False

# Calculate Risk Score
risk_score = 0

if sos_pressed:
    risk_score += 40

if person_detected:
    risk_score += 30

if motion_detected:
    risk_score += 15

if sound_detected:
    risk_score += 15

print("\n===== SMART SECURITY STREET LIGHT =====")

print("SOS Button Pressed :", sos_pressed)
print("Person Detected    :", person_detected)
print("Motion Detected    :", motion_detected)
print("Sound Detected     :", sound_detected)

print("\nRisk Score =", risk_score)

# Decision Making
if risk_score >= 70:
    print("HIGH PRIORITY ALERT")
    print("Alert Sent To Police Control Room")
    print("Camera Activated")
    print("Microphone Channel Opened")

elif risk_score >= 40:
    print("MEDIUM PRIORITY ALERT")
    print("Officer Verification Required")

else:
    print("LOW PRIORITY ALERT")
    print("Situation Logged")

print("\n======================================")