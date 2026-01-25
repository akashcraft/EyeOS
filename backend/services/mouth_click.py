def mouth_gesture_clicker(
    camera_index=0,
    arm_mouth_open_ratio=0.25,
    close_ratio=0.015,
    cooldown_sec=0.35,
    double_click_window=1.8,
    right_click_hold_sec=0.7,
    show_debug=False
):
    import cv2
    import mediapipe as mp
    import pyautogui
    import time

    mp_face = mp.solutions.face_mesh
    face_mesh = mp_face.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )

    cap = cv2.VideoCapture(camera_index)

    mouth_is_open = False
    open_start_time = 0.0
    right_click_fired = False

    last_action_time = 0.0
    last_open_event_time = 0.0

    last_action_label = "NONE"
    last_action_label_time = 0.0

    def dbg_print(msg):
        if show_debug:
            print(msg)

    def lm_xy(lm, w, h):
        return int(lm.x * w), int(lm.y * h)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = face_mesh.process(rgb)

        now = time.time()
        status_text = "No face"

        if res.multi_face_landmarks:
            face = res.multi_face_landmarks[0].landmark

            left_corner = face[61]
            right_corner = face[291]
            upper_lip = face[13]
            lower_lip = face[14]

            mouth_open = abs(lower_lip.y - upper_lip.y)
            mouth_width = abs(right_corner.x - left_corner.x) + 1e-6
            open_ratio = mouth_open / mouth_width

            if not mouth_is_open and open_ratio > arm_mouth_open_ratio:
                mouth_is_open = True
                open_start_time = now
                right_click_fired = False
                status_text = "OPEN"

                if (now - last_action_time) > cooldown_sec:
                    if (now - last_open_event_time) <= double_click_window:
                        pyautogui.doubleClick()
                        last_action_label = "DOUBLE CLICK"
                        last_action_label_time = now
                        dbg_print(f"[{time.strftime('%H:%M:%S')}] DOUBLE CLICK")
                        status_text = last_action_label
                        last_action_time = now
                        last_open_event_time = 0.0
                    else:
                        last_open_event_time = now

            elif mouth_is_open:
                if (not right_click_fired
                        and (now - open_start_time) >= right_click_hold_sec
                        and (now - last_action_time) > cooldown_sec):
                    pyautogui.rightClick()
                    last_action_label = "RIGHT CLICK"
                    last_action_label_time = now
                    dbg_print(f"[{time.strftime('%H:%M:%S')}] RIGHT CLICK")
                    status_text = last_action_label
                    last_action_time = now
                    right_click_fired = True

                if open_ratio < close_ratio:
                    mouth_is_open = False
                    status_text = "CLOSED"

                    if (not right_click_fired
                            and (now - last_action_time) > cooldown_sec
                            and last_open_event_time != 0.0):
                        pyautogui.leftClick()
                        last_action_label = "LEFT CLICK"
                        last_action_label_time = now
                        dbg_print(f"[{time.strftime('%H:%M:%S')}] LEFT CLICK")
                        status_text = last_action_label
                        last_action_time = now

        if show_debug:
            cv2.putText(frame, f"Last: {last_action_label}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            if last_action_label_time > 0:
                cv2.putText(frame, f"{now - last_action_label_time:.2f}s ago", (10, 85),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            if res.multi_face_landmarks:
                lc = lm_xy(left_corner, w, h)
                rc = lm_xy(right_corner, w, h)
                ul = lm_xy(upper_lip, w, h)
                ll = lm_xy(lower_lip, w, h)

                cv2.circle(frame, lc, 3, (0, 255, 0), -1)
                cv2.circle(frame, rc, 3, (0, 255, 0), -1)
                cv2.circle(frame, ul, 3, (255, 255, 0), -1)
                cv2.circle(frame, ll, 3, (255, 255, 0), -1)
                cv2.line(frame, lc, rc, (0, 255, 0), 1)

                cv2.putText(frame, f"open_ratio={open_ratio:.3f}", (10, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                if mouth_is_open:
                    cv2.putText(frame, f"open_for={now - open_start_time:.2f}s", (10, 135),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            cv2.putText(frame, status_text, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)

            cv2.imshow("Mouth Clicker (ESC to quit)", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break

    cap.release()
    if show_debug:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    mouth_gesture_clicker(show_debug=True)
