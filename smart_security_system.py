# SMART SECURITY STREET LIGHT SYSTEM
# AI Decision Engine

false_alarm_count = 0

print("\n===== SMART SECURITY STREET LIGHT SYSTEM =====\n")

# -------------------------
# 5-SECOND SOS VALIDATION
# -------------------------

hold_time = int(input("How many seconds was SOS held? : "))

if hold_time < 5:
    print("\nSOS REJECTED")
    print("Reason : Button must be held for at least 5 seconds")
    exit()

print("\nSOS ACTIVATED")

# -------------------------
# SENSOR INPUTS
# -------------------------

person_detected = input("Person Detected by AI Camera? (yes/no): ").lower()
motion_detected = input("Motion Detected? (yes/no): ").lower()
sound_detected = input("Unusual Sound Detected? (yes/no): ").lower()

print("\n========== ANALYSIS REPORT ==========\n")

# -------------------------
# DECISION ENGINE
# -------------------------

if person_detected == "yes":

    # CRITICAL
    if motion_detected == "yes" and sound_detected == "yes":

        print("STATUS   : CRITICAL ALERT")
        print("ACTION   : Immediate Control Room Notification")
        print("ACTION   : Camera Feed Activated")
        print("ACTION   : Two-Way Communication Enabled")

    # HIGH
    elif motion_detected == "yes":

        print("STATUS   : HIGH PRIORITY ALERT")
        print("ACTION   : Officer Monitoring Required")

    # VERIFICATION
    elif motion_detected == "no" and sound_detected == "no":

        print("STATUS   : VERIFICATION REQUIRED")
        print("REASON   : Person visible but no motion or sound")
        print("ACTION   : Officer initiates voice communication")
        print("POSSIBLE : Medical emergency / accidental SOS")

    else:

        print("STATUS   : HIGH PRIORITY ALERT")
        print("ACTION   : Officer Monitoring Required")

else:

    if motion_detected == "no" and sound_detected == "no":

        false_alarm_count += 1

        print("STATUS   : POSSIBLE FALSE ALARM")
        print("ACTION   : Event Logged")

        print("False Alarm Count :", false_alarm_count)

        if false_alarm_count >= 3:
            print("ACTION   : Inspection Request Generated")

    else:

        print("STATUS   : MEDIUM PRIORITY ALERT")
        print("ACTION   : Officer Verification Required")

print("\n60-SECOND COOLDOWN INITIATED")
print("\n====================================")