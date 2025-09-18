import cv2
import mediapipe as mp
import pyautogui
import time
import math
import threading
import platform

# ================== BACKENDS DE MOUSE ==================
HAS_PDI = False
try:
    import pydirectinput as pdi
    pdi.PAUSE = 0
    pdi.FAILSAFE = True
    HAS_PDI = True
except Exception:
    pass

# --- RAW relativo no Windows (melhor para jogos/360) ---
IS_WINDOWS = platform.system().lower().startswith("win")
RAW_OK = False
if IS_WINDOWS:
    try:
        import ctypes
        from ctypes import wintypes

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG),
                        ("dy", wintypes.LONG),
                        ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD),
                        ("mi", MOUSEINPUT)]

        SendInput = ctypes.windll.user32.SendInput
        INPUT_MOUSE = 0
        MOUSEEVENTF_MOVE = 0x0001

        def raw_move_rel(dx, dy):
            inp = INPUT()
            inp.type = INPUT_MOUSE
            inp.mi = MOUSEINPUT(int(dx), int(dy), 0, MOUSEEVENTF_MOVE, 0, None)
            SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

        RAW_OK = True
    except Exception:
        RAW_OK = False

# ---------------- HOTKEYS GLOBAIS ----------------
HAS_GLOBAL_KEYS = False
try:
    import keyboard  # pip install keyboard
    HAS_GLOBAL_KEYS = True
except Exception:
    print("[AVISO] 'keyboard' indisponível. F1/F2/F3/F4 só funcionam na janela do app.")

# ========== SEGURANÇA ==========
pyautogui.FAILSAFE = True  # (0,0) aborta

# ========== TELA ==========
SCREEN_W, SCREEN_H = pyautogui.size()

# ========== PRESETS ==========
PRESETS = [
    {"name":"Precisao (mira)",   "deadzone_deg":4.0, "gain_yaw":7.0,  "gain_pitch":6.5, "gain_power":1.25,
     "max_speed_px":20, "ema_alpha":0.12, "vel_ema_alpha":0.30,
     "edge_margin":25, "edge_accel_max":4.0, "edge_accel_rate":2.5, "edge_decay_rate":5.0,
     "yaw_strong_deg":10.0, "yaw_strong_rate":2.0},
    {"name":"Equilibrio (geral)","deadzone_deg":3.0, "gain_yaw":9.0,  "gain_pitch":8.0, "gain_power":1.35,
     "max_speed_px":25, "ema_alpha":0.15, "vel_ema_alpha":0.25,
     "edge_margin":25, "edge_accel_max":6.0, "edge_accel_rate":3.0, "edge_decay_rate":4.0,
     "yaw_strong_deg":8.0,  "yaw_strong_rate":2.5},
    {"name":"Rapido (explorar)", "deadzone_deg":2.0, "gain_yaw":13.0, "gain_pitch":11.0,"gain_power":1.35,
     "max_speed_px":40, "ema_alpha":0.20, "vel_ema_alpha":0.20,
     "edge_margin":28, "edge_accel_max":8.0, "edge_accel_rate":5.0, "edge_decay_rate":3.0,
     "yaw_strong_deg":6.0,  "yaw_strong_rate":4.0},
    {"name":"Personalizado",     "deadzone_deg":3.5, "gain_yaw":10.0, "gain_pitch":8.5, "gain_power":1.30,
     "max_speed_px":30, "ema_alpha":0.16, "vel_ema_alpha":0.25,
     "edge_margin":25, "edge_accel_max":6.0, "edge_accel_rate":3.5, "edge_decay_rate":4.0,
     "yaw_strong_deg":7.0,  "yaw_strong_rate":3.0},
]
current_preset = 1

def load_preset(i):
    p = PRESETS[i]
    return (p["deadzone_deg"], p["gain_yaw"], p["gain_pitch"], p["gain_power"], p["max_speed_px"],
            p["ema_alpha"], p["vel_ema_alpha"], p["edge_margin"],
            p["edge_accel_max"], p["edge_accel_rate"], p["edge_decay_rate"],
            p["yaw_strong_deg"], p["yaw_strong_rate"])

(deadzone_deg, gain_yaw, gain_pitch, gain_power, max_speed_px,
 ema_alpha, vel_ema_alpha, edge_margin,
 edge_accel_max, edge_accel_rate, edge_decay_rate,
 yaw_strong_deg, yaw_strong_rate) = load_preset(current_preset)

# ========== FLAGS ==========
CALIBRATION_TIME = 1.5
MIRROR_YAW = True
MIRROR_ROLL = True
MIRROR_PITCH = False
INVERT_Y = True
EDGE_ACCEL_ENABLED = True  # F2 alterna

# ========== MEDIAPIPE ==========
mp_face_mesh = mp.solutions.face_mesh

# ========= ESTADO =========
control_enabled = False
neutral_yaw = neutral_pitch = neutral_roll = 0.0
ema_yaw = ema_pitch = ema_roll = 0.0
vx_ema = vy_ema = 0.0

# Boost estilo “stick” (apenas X)
edge_boost_x = 0.0
_last_time = time.time()

# Hotkeys debounce + recalib
_last_f1 = _last_f2 = _last_f3 = _last_f4 = 0.0
_DEBOUNCE = 0.25
recalib_request = False

# ========== UTIL ==========
def clamp(v, lo, hi): return max(lo, min(hi, v))
def radians_to_degrees(rad): return rad * 180.0 / math.pi

def vec_angle_deg(p1, p2):
    dx = p2[0] - p1[0]; dy = p2[1] - p1[1]
    return radians_to_degrees(math.atan2(dy, dx))

def ema_func(prev, new, alpha): return alpha * new + (1 - alpha) * prev

def apply_deadzone_and_gain(delta_deg, dz, g, p):
    sign = 1 if delta_deg >= 0 else -1
    mag = abs(delta_deg)
    if mag <= dz: return 0.0
    adj = (mag - dz)
    speed = (adj ** p) * g
    return sign * speed

def get_yaw_pitch_roll(landmarks, w, h):
    idx_left_eye_outer = 33
    idx_right_eye_outer = 263
    idx_nose_tip = 1
    idx_nose_bottom = 2
    idx_forehead = 10

    def denorm(i): return (landmarks[i].x * w, landmarks[i].y * h)

    le = denorm(idx_left_eye_outer)
    re = denorm(idx_right_eye_outer)
    nose = denorm(idx_nose_tip)
    nose_b = denorm(idx_nose_bottom)
    forehead = denorm(idx_forehead)

    eye_center = ((le[0] + re[0]) * 0.5, (le[1] + re[1]) * 0.5)

    # roll (HUD)
    roll = vec_angle_deg(le, re)
    if roll > 90: roll -= 180
    if roll < -90: roll += 180

    # yaw
    yaw = (nose[0] - eye_center[0]) / max(1, (re[0] - le[0]))
    yaw_deg = yaw * 35.0

    # pitch (positiva = cabeça para BAIXO)
    ref = max(1, abs(eye_center[1] - nose_b[1]))
    pitch = ((nose_b[1] - forehead[1]) / ref) - 0.6
    pitch_deg = pitch * 40.0

    return yaw_deg, pitch_deg, roll

# --------- BACKEND UNIFICADO ---------
def backend_name():
    if RAW_OK: return "RAW_WIN"
    if HAS_PDI: return "PyDirectInput"
    return "PyAutoGUI"

def mouse_move_rel(dx, dy):
    if RAW_OK:
        raw_move_rel(dx, dy)
    elif HAS_PDI:
        pdi.moveRel(int(dx), int(dy), duration=0)
    else:
        pyautogui.moveRel(int(dx), int(dy), duration=0)

# ---------- EDGE/STICK ACCEL X ----------
def apply_stick_accel_x(vx, yaw_deg):
    """
    Aceleração “estilo controle”:
    - Se o ponteiro encosta na borda OU se yaw fica forte e sustentado,
      aumenta o boost; do contrário, decai.
    - Apenas eixo X.
    """
    global edge_boost_x, _last_time
    now = time.time()
    dt = max(1e-3, now - _last_time)
    _last_time = now

    # Sinal de “empurrando” pela borda (quando o ponteiro prende)
    try:
        x, _ = pyautogui.position()
    except Exception:
        x = SCREEN_W // 2

    pushing_left  = (x <= edge_margin) and (vx < 0)
    pushing_right = (x >= SCREEN_W - edge_margin) and (vx > 0)

    # Sinal de “analógico no talo” (yaw forte e sustentado)
    strong_push = abs(yaw_deg) >= yaw_strong_deg

    if EDGE_ACCEL_ENABLED and (pushing_left or pushing_right or strong_push):
        # taxa de crescimento: soma efeito borda + yaw forte
        rate = edge_accel_rate + (yaw_strong_rate if strong_push else 0.0)
        edge_boost_x = min(edge_accel_max, edge_boost_x + rate * dt)
    else:
        edge_boost_x = max(0.0, edge_boost_x - edge_decay_rate * dt)

    return vx * (1.0 + edge_boost_x)

# ------------- MOVIMENTO -------------
def move_mouse_from_angles(yaw_deg, pitch_deg):
    global vx_ema, vy_ema

    vx = apply_deadzone_and_gain(yaw_deg, deadzone_deg, gain_yaw, gain_power)
    vy = apply_deadzone_and_gain(pitch_deg, deadzone_deg, gain_pitch, gain_power)

    if INVERT_Y: vy = -vy

    # limite base
    vx = clamp(vx, -max_speed_px, max_speed_px)
    vy = clamp(vy, -max_speed_px, max_speed_px)

    # “stick accel” no X
    vx = apply_stick_accel_x(vx, yaw_deg)

    # suavização na velocidade
    vx_ema = ema_func(vx_ema, vx, vel_ema_alpha)
    vy_ema = ema_func(vy_ema, vy, vel_ema_alpha)

    if vx_ema != 0.0 or vy_ema != 0.0:
        mouse_move_rel(vx_ema, vy_ema)

# ------------- HUD -------------
def draw_hud(img, enabled, yaw, pitch, roll, show_cross=False):
    h, w = img.shape[:2]
    status = "ON" if enabled else "OFF"
    color = (0, 200, 0) if enabled else (0, 0, 200)
    try:
        cv2.rectangle(img, (10, 10), (760, 230), (20, 20, 20), -1)
        cv2.putText(img, f"Head Mouse: {status} | Backend: {backend_name()}",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.putText(img, "Hotkeys: F1=On/Off  F2=EdgeAccel  F3=Preset+  Shift+F3=Preset-  F4=Recalibrar  ESC=Sair(janela)",
                    (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200,220,255), 1)
        cv2.putText(img, f"Preset: {PRESETS[current_preset]['name']}", (20, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)
        cv2.putText(img, f"Deadzone:{deadzone_deg:.1f}  Gain(Y/P):{gain_yaw:.1f}/{gain_pitch:.1f}  Power:{gain_power:.2f}  MaxSpd:{max_speed_px}",
                    (20, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,255,200), 1)
        cv2.putText(img, f"Smoothing: angleEMA:{ema_alpha:.2f}  velEMA:{vel_ema_alpha:.2f}",
                    (20, 135), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,255,200), 1)
        cv2.putText(img, f"EdgeAccelX: {EDGE_ACCEL_ENABLED}  margin:{edge_margin}px  max:{edge_accel_max}x  "
                         f"rate:{edge_accel_rate}/s  decay:{edge_decay_rate}/s  boost:{edge_boost_x:.2f}x",
                    (20, 155), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200,220,255), 1)
        cv2.putText(img, f"Yaw:{yaw:+.1f}  Pitch:{pitch:+.1f}  (InvertY:{INVERT_Y}, MirrorY/R:{MIRROR_YAW}/{MIRROR_ROLL})",
                    (20, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)

        if show_cross:
            cx, cy = w // 2, h // 2
            cv2.line(img, (0, cy), (w, cy), (0, 255, 0), 2)
            cv2.line(img, (cx, 0), (cx, h), (0, 255, 0), 2)
            cv2.putText(img, "Olhe para o CENTRO para recalibrar...", (20, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
    except Exception:
        pass  # não deixa a UI derrubar o app

# ------------- PRESETS -------------
def apply_preset(idx, silent=False):
    global current_preset
    global deadzone_deg, gain_yaw, gain_pitch, gain_power, max_speed_px
    global ema_alpha, vel_ema_alpha
    global edge_margin, edge_accel_max, edge_accel_rate, edge_decay_rate
    global yaw_strong_deg, yaw_strong_rate
    global vx_ema, vy_ema, edge_boost_x

    current_preset = int(idx) % len(PRESETS)
    (deadzone_deg, gain_yaw, gain_pitch, gain_power, max_speed_px,
     ema_alpha, vel_ema_alpha, edge_margin,
     edge_accel_max, edge_accel_rate, edge_decay_rate,
     yaw_strong_deg, yaw_strong_rate) = load_preset(current_preset)

    vx_ema = vy_ema = 0.0
    edge_boost_x = 0.0
    if not silent:
        print(f"[Preset] {PRESETS[current_preset]['name']} aplicado.")

# ======== HOTKEY CALLBACKS ========
_last_f1 = _last_f2 = _last_f3 = _last_f4 = 0.0
_DEBOUNCE = 0.25
def _debounce(ts_attr):
    now = time.time()
    if now - ts_attr[0] >= _DEBOUNCE:
        ts_attr[0] = now
        return True
    return False

def toggle_control():
    global control_enabled, _last_f1
    if _debounce([_last_f1]):  # truque simples p/ debounce
        control_enabled = not control_enabled
        _last_f1 = time.time()
        print(f"[F1] Controle: {'ON' if control_enabled else 'OFF'}")

def toggle_edgeaccel():
    global EDGE_ACCEL_ENABLED, _last_f2, edge_boost_x
    if _debounce([_last_f2]):
        EDGE_ACCEL_ENABLED = not EDGE_ACCEL_ENABLED
        edge_boost_x = 0.0
        _last_f2 = time.time()
        print(f"[F2] EdgeAccelX: {'ON' if EDGE_ACCEL_ENABLED else 'OFF'}")

def next_preset():
    global _last_f3
    if _debounce([_last_f3]):
        apply_preset(current_preset + 1)
        _last_f3 = time.time()

def prev_preset():
    global _last_f3
    if _debounce([_last_f3]):
        apply_preset(current_preset - 1)
        _last_f3 = time.time()

recalib_request = False
def request_recalibrate():
    global recalib_request, _last_f4
    if _debounce([_last_f4]):
        recalib_request = True
        _last_f4 = time.time()
        print("[F4] Recalibracao solicitada.")

def setup_global_hotkeys():
    if not HAS_GLOBAL_KEYS:
        return
    try:
        keyboard.add_hotkey('f1', toggle_control)
        keyboard.add_hotkey('f2', toggle_edgeaccel)
        keyboard.add_hotkey('f3', next_preset)
        keyboard.add_hotkey('shift+f3', prev_preset)
        keyboard.add_hotkey('f4', request_recalibrate)
        print("[OK] Hotkeys globais registradas.")
    except Exception as e:
        print(f"[AVISO] Hotkeys globais falharam: {e}")

# ------------- MAIN -------------
def main():
    global neutral_yaw, neutral_pitch, neutral_roll
    global ema_yaw, ema_pitch, ema_roll
    global vx_ema, vy_ema, edge_boost_x, recalib_request

    apply_preset(current_preset, silent=True)

    if HAS_GLOBAL_KEYS:
        threading.Thread(target=setup_global_hotkeys, daemon=True).start()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Erro: Não foi possível abrir a webcam.")
        return

    with mp_face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.6
    ) as face_mesh:

        # Calibração inicial com cruz
        print("Calibrando... Olhe para o centro.")
        calib_samples = []
        start = time.time()
        while time.time() - start < CALIBRATION_TIME:
            ok, frame = cap.read()
            if not ok: continue
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = face_mesh.process(frame_rgb)
            if res.multi_face_landmarks:
                lm = res.multi_face_landmarks[0].landmark
                h, w = frame.shape[:2]
                yaw, pitch, roll = get_yaw_pitch_roll(lm, w, h)
                calib_samples.append((yaw, pitch, roll))
            view = cv2.flip(frame, 1)
            draw_hud(view, False, 0, 0, 0, show_cross=True)
            try:
                cv2.imshow("Head Mouse", view)
            except Exception:
                pass
            if cv2.waitKey(1) & 0xFF == 27:
                cap.release(); cv2.destroyAllWindows(); return

        if calib_samples:
            neutral_yaw   = sum(s[0] for s in calib_samples) / len(calib_samples)
            neutral_pitch = sum(s[1] for s in calib_samples) / len(calib_samples)
            neutral_roll  = sum(s[2] for s in calib_samples) / len(calib_samples)
        ema_yaw = ema_pitch = ema_roll = 0.0
        vx_ema = vy_ema = 0.0
        edge_boost_x = 0.0

        print(f"Pronto. Backend: {backend_name()} | F1: On/Off | F2: EdgeAccel | F3/Shift+F3: Presets | F4: Recalibrar | ESC sai.")

        last_key_inwin = 0.0
        while True:
            ok, frame = cap.read()
            if not ok: continue

            # Recalibrar sob demanda
            if recalib_request:
                recalib_request = False
                samples = []
                t0 = time.time()
                while time.time() - t0 < CALIBRATION_TIME:
                    ok2, f2 = cap.read()
                    if not ok2: continue
                    rgb2 = cv2.cvtColor(f2, cv2.COLOR_BGR2RGB)
                    res2 = face_mesh.process(rgb2)
                    if res2.multi_face_landmarks:
                        lm2 = res2.multi_face_landmarks[0].landmark
                        hh, ww = f2.shape[:2]
                        y2, p2, r2 = get_yaw_pitch_roll(lm2, ww, hh)
                        samples.append((y2, p2, r2))
                    view2 = cv2.flip(f2, 1)
                    draw_hud(view2, False, 0, 0, 0, show_cross=True)
                    try:
                        cv2.imshow("Head Mouse", view2)
                    except Exception:
                        pass
                    if cv2.waitKey(1) & 0xFF == 27:
                        cap.release(); cv2.destroyAllWindows(); return
                if samples:
                    neutral_yaw   = sum(s[0] for s in samples) / len(samples)
                    neutral_pitch = sum(s[1] for s in samples) / len(samples)
                    neutral_roll  = sum(s[2] for s in samples) / len(samples)
                ema_yaw = ema_pitch = ema_roll = 0.0
                vx_ema = vy_ema = 0.0
                edge_boost_x = 0.0
                continue

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(frame_rgb)

            yaw = pitch = roll = 0.0
            if results.multi_face_landmarks:
                lm = results.multi_face_landmarks[0].landmark
                h, w = frame.shape[:2]
                yaw_deg, pitch_deg, roll_deg = get_yaw_pitch_roll(lm, w, h)

                if MIRROR_YAW:   yaw_deg  = -yaw_deg
                if MIRROR_ROLL:  roll_deg = -roll_deg
                if MIRROR_PITCH: pitch_deg = -pitch_deg

                yaw_deg   -= neutral_yaw
                pitch_deg -= neutral_pitch

                ema_yaw   = ema_func(ema_yaw, yaw_deg, ema_alpha)
                ema_pitch = ema_func(ema_pitch, pitch_deg, ema_alpha)

                yaw, pitch = ema_yaw, ema_pitch

                if control_enabled:
                    move_mouse_from_angles(yaw, pitch)

            view = cv2.flip(frame, 1)
            draw_hud(view, control_enabled, yaw, pitch, roll, show_cross=False)
            try:
                cv2.imshow("Head Mouse", view)
            except Exception:
                pass

            k = cv2.waitKey(1) & 0xFF
            if k == 27:
                break
            if not HAS_GLOBAL_KEYS:
                # fallback local
                if k == ord('q') and time.time() - last_key_inwin > _DEBOUNCE:
                    toggle_control(); last_key_inwin = time.time()
                if k == ord('e') and time.time() - last_key_inwin > _DEBOUNCE:
                    toggle_edgeaccel(); last_key_inwin = time.time()
                if k == ord('r') and time.time() - last_key_inwin > _DEBOUNCE:
                    next_preset(); last_key_inwin = time.time()
                if k == ord('c') and time.time() - last_key_inwin > _DEBOUNCE:
                    request_recalibrate(); last_key_inwin = time.time()

        if HAS_GLOBAL_KEYS:
            try: keyboard.unhook_all_hotkeys()
            except Exception: pass

        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
