#!/usr/bin/env python3
import time
import signal
import sys
import subprocess

import pigpio

# --------------------
# CONFIGURATION
# --------------------

PWM_PIN = 12          # BCM pin (GPIO12, physical pin 32)
PWM_FREQ = 25000      # Hz, hardware PWM

# Old behaviour: start at ~65°C, modest speeds
TEMP_POINTS  = [65.0, 68.0, 75.0]
SPEED_POINTS = [ 0.0, 20.0, 40.0]

CHECK_INTERVAL      = 2.0    # seconds between temp checks
MIN_DUTY_PERCENT    = 10.0   # below this, treat as OFF
BOOST_DUTY_PERCENT  = 40.0   # boost duty when starting from 0
BOOST_SECONDS       = 1.0    # how long to boost
DOWN_DELAY_SECONDS  = 30.0   # minimum time before reducing speed

# --------------------
# Globals
# --------------------

running       = True
current_speed = 0.0   # percent
last_change   = 0.0   # time.time() of last change
boost_until   = 0.0   # time until which boost is held

# --------------------
# Helpers
# --------------------

def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} {msg}", flush=True)

def read_cpu_temp_c() -> float:
    """Read CPU temperature in °C."""
    # Try /sys first
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            milli = int(f.read().strip())
        return milli / 1000.0
    except Exception:
        pass

    # Fallback to vcgencmd
    try:
        out = subprocess.check_output(
            ["vcgencmd", "measure_temp"], text=True
        ).strip()
        # format: temp=47.8'C
        v = out.split("=")[1].split("'")[0]
        return float(v)
    except Exception as e:
        log(f"ERROR reading temperature: {e}")
        return 0.0

def interp_speed(temp_c: float) -> float:
    """Piecewise-linear interpolation between TEMP_POINTS and SPEED_POINTS."""
    xs = TEMP_POINTS
    ys = SPEED_POINTS

    if temp_c <= xs[0]:
        return ys[0]
    if temp_c >= xs[-1]:
        return ys[-1]

    for i in range(len(xs) - 1):
        if xs[i] <= temp_c <= xs[i + 1]:
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[i], ys[i + 1]
            frac = (temp_c - x0) / (x1 - x0)
            return y0 + frac * (y1 - y0)

    return ys[-1]

# --------------------
# Fan control
# --------------------

def set_speed(pi: pigpio.pi, target_speed: float, temp_c: float,
              force: bool = False) -> None:
    """
    Set fan speed (percent). Applies hysteresis and boost.
    target_speed: desired speed in percent (0..100).
    temp_c: current CPU temperature (for logging).
    force: if True, bypass hysteresis (used on shutdown).
    """
    global current_speed, last_change, boost_until

    now = time.time()

    # Treat tiny targets as "off"
    if target_speed is not None and target_speed < MIN_DUTY_PERCENT:
        target_speed = 0.0

    # Hysteresis for downward changes
    if not force:
        if target_speed < current_speed:
            if now - last_change < DOWN_DELAY_SECONDS:
                # Too soon to reduce speed; keep current
                return

    # If currently stopped and we want to start: apply boost
    if current_speed <= 0.1 and target_speed > 0.0 and not force:
        boost_until = now + BOOST_SECONDS
        duty = max(BOOST_DUTY_PERCENT, target_speed, MIN_DUTY_PERCENT)
        pi.hardware_PWM(PWM_PIN, PWM_FREQ, int(duty * 10000))
        current_speed = duty
        last_change = now
        log(
            f"Fan BOOST → {duty:.1f}% "
            f"(target {target_speed:.1f}%) at {temp_c:.1f}°C"
        )
        return

    # If we are still in boost phase, keep boost until boost_until
    if boost_until > 0 and now < boost_until and not force:
        return
    else:
        boost_until = 0.0

    # Normal mode
    if target_speed <= 0.0:
        # Turn off
        if current_speed != 0.0:
            log(f"Fan OFF at {temp_c:.1f}°C")
        pi.hardware_PWM(PWM_PIN, PWM_FREQ, 0)
        current_speed = 0.0
    else:
        duty = max(target_speed, MIN_DUTY_PERCENT)
        pwm_val = int(duty * 10000)
        pi.hardware_PWM(PWM_PIN, PWM_FREQ, pwm_val)
        if abs(duty - current_speed) >= 1.0:
            log(
                f"Fan set → {duty:.1f}% "
                f"(target {target_speed:.1f}%) at {temp_c:.1f}°C"
            )
        current_speed = duty

    last_change = now

# --------------------
# Signal handler
# --------------------

def handle_signal(signum, frame):
    global running
    log(f"Received signal {signum}, stopping fan controller")
    running = False

# --------------------
# Main
# --------------------

def main():
    global running

    # Connect to pigpio
    pi = pigpio.pi()
    if not pi.connected:
        log("ERROR: Cannot connect to pigpio daemon. Is pigpiod running?")
        sys.exit(1)

    # Initialise pin
    pi.set_mode(PWM_PIN, pigpio.OUTPUT)
    pi.hardware_PWM(PWM_PIN, PWM_FREQ, 0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    log("Fan controller started")

    try:
        while running:
            temp = read_cpu_temp_c()
            target = interp_speed(temp)
            set_speed(pi, target_speed=target, temp_c=temp)
            time.sleep(CHECK_INTERVAL)
    finally:
        # Ensure the fan is stopped and pigpio is released
        try:
            set_speed(pi, target_speed=0.0, temp_c=read_cpu_temp_c(), force=True)
        except Exception:
            pi.hardware_PWM(PWM_PIN, PWM_FREQ, 0)
        pi.stop()
        log("Fan controller stopped")

if __name__ == "__main__":
    main()
