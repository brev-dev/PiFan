# PiFan
Raspberry Pi PWM Fan Controller (pigpio, hardware PWM)

- This project provides a small Python daemon (`fan.py`) to control a cooling fan on a Raspberry Pi using **hardware PWM** via [`pigpio`](http://abyz.me.uk/rpi/pigpio/).  

- It was designed for a **Raspberry Pi 3** enclosed in a WD HDD enclosure, but is easily adaptable to other setups.

---

## Features

- Uses **hardware PWM** on `GPIO12` (pin 32) for quiet, smooth control
- Temperature-based fan curve:
  - Off below ~65 °C
  - ~20 % duty around 68 °C
  - ~40 % duty by 75 °C
- **Minimum duty** threshold to avoid stalling (`MIN_DUTY_PERCENT`)
- **Startup boost** when the fan first spins up
- Simple **hysteresis** on speed reduction to prevent “flapping”
- Systemd unit file included (`fan.service`)
- Logs fan events and temperatures to `journalctl`

---

## Hardware Assumptions

Default wiring (can be changed in the script):

- Raspberry Pi 3 Model B (aarch64)
- Fan powered from 5 V via a small transistor or MOSFET board
  - PWM control on **BCM GPIO12** (physical pin 32)
  - Fan GND back to Pi GND (e.g. pin 34)
- Fan expects a 5 V PWM-compatible input (or is driven via a suitable transistor)

If you change the GPIO, update `PWM_PIN` in `fan.py` accordingly.

---

## Temperature Curve

The fan speed is derived from the CPU temperature (°C) via a simple piecewise linear curve:

```python
TEMP_POINTS  = [65.0, 68.0, 75.0]
SPEED_POINTS = [ 0.0, 20.0, 40.0]
```
- ≤65°C → 0% (fan off)
-  68°C → 20%
- ≥75°C → 40%

Additionally:

`MIN_DUTY_PERCENT = 10.0`
Targets below this are treated as “off” (0 %).

`BOOST_DUTY_PERCENT = 40.0` for `BOOST_SECONDS = 1.0`
When starting from 0 %, the fan gets a brief boost to guarantee spin-up.

`DOWN_DELAY_SECONDS = 30.0`
Prevents reducing speed too frequently.

You can adjust these constants at the top of `fan.py` to match your cooling and noise preferences.

## Requirements

- Raspberry Pi (3 in the reference setup)

- `pigpio` built and installed from source:
```
sudo apt install python3-dev python3-setuptools git make gcc
cd /tmp
git clone https://github.com/joan2937/pigpio.git
cd pigpio
make
sudo make install
```

- `pigpiod` daemon running as a systemd service

## Installation

### 1. Install & enable `pigpiod`:

Create `/etc/systemd/system/pigpiod.service`:
```
[Unit]
Description=Pigpio daemon
After=network.target

[Service]
ExecStart=/usr/local/bin/pigpiod
Type=forking

[Install]
WantedBy=multi-user.target
```

Then:
```
sudo systemctl daemon-reload
sudo systemctl enable --now pigpiod
```

### 2. Install `fan.py`:

Copy `fan.py` to:
```
sudo cp fan.py /usr/local/bin/fan.py
sudo chmod +x /usr/local/bin/fan.py
```

### 3. Create `fan.service`:

Create `/etc/systemd/system/fan.service`:
```
[Unit]
Description=PWM fan controller on GPIO12 (pigpio)
After=pigpiod.service
Requires=pigpiod.service

[Service]
Type=simple
ExecStart=/usr/bin/env python3 /usr/local/bin/fan.py
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
```

### 4. Enable and start the fan controller:
```
sudo systemctl daemon-reload
sudo systemctl enable --now fan.service
```
## How It Works

High-level loop in `fan.py`:

1. Read CPU temperature from `/sys/class/thermal/thermal_zone0/temp`,
or fall back to `vcgencmd measure_temp`.

2. Interpolate a target speed using `TEMP_POINTS` / `SPEED_POINTS`.

3. Apply:

    - minimum duty threshold
    - startup boost from 0 % → `BOOST_DUTY_PERCENT`
    - hysteresis for decreasing speeds

4. Drive the fan via `pigpio.hardware_PWM(PWM_PIN, PWM_FREQ, duty * 10000)`.

5. Sleep (`CHECK_INTERVAL`) and repeat.

On shutdown (`SIGTERM`/`SIGINT`), it forces the speed to 0 % and stops `pigpio`.

## Logging & Debugging

The script logs state changes to stdout; under systemd you can see them with:
```
sudo journalctl -u fan.service -f
```

Example log lines:
```
2025-11-23 22:15:10 Fan BOOST → 40.0% (target 18.0%) at 66.2°C
2025-11-23 22:15:40 Fan set → 20.0% (target 18.0%) at 64.8°C
2025-11-23 22:16:20 Fan OFF at 55.9°C
```

To check service status:
```
sudo systemctl status fan.service
```
## Customisation

Key knobs to tune at the top of `fan.py`:
```
PWM_PIN = 12         # change if using a different GPIO
PWM_FREQ = 25000     # PWM frequency (Hz)

TEMP_POINTS  = [65.0, 68.0, 75.0]
SPEED_POINTS = [ 0.0, 20.0, 40.0]

CHECK_INTERVAL      = 2.0
MIN_DUTY_PERCENT    = 10.0
BOOST_DUTY_PERCENT  = 40.0
BOOST_SECONDS       = 1.0
DOWN_DELAY_SECONDS  = 30.0
```

You can:

- Raise/lower temperature thresholds
- Increase `SPEED_POINTS` if you need more airflow
- Increase `DOWN_DELAY_SECONDS` if your system hovers around a threshold

## Safety Notes

- Ensure your fan wiring and any transistor/MOSFET board are rated for the fan’s current.
- Do not drive a 5 V fan directly from a 3.3 V GPIO pin; always use a driver or transistor.
- Test behaviour under load and confirm temperatures remain below Raspberry Pi throttling limits.

# Simple ON/OFF Fan Control (No Python, No PWM)

If your cooling requirements are modest or your fan is not PWM-capable, you can use the Raspberry Pi’s built-in gpio-fan overlay. This provides automatic on/off operation based on CPU temperature without needing any software scripts.

This is the simplest possible method for fan control.

## Features

- Zero CPU overhead
- Uses built-in Raspberry Pi firmware
- No Python or systemd services required
- Fan turns on above a threshold, and off below a lower threshold
- Works with any 5V fan driven via a transistor or MOSFET

## Hardware Requirements

The Pi cannot drive a 5V fan directly from a GPIO pin.

You must use:

- NPN transistor
- OR MOSFET
- OR a small driver board (my setup uses this)

Typical wiring:


| Component              | To                                         |
|------------------------|---------------------------------------------|
| Fan +5V lead           | Pi 5V pin (pin 2 or 4)                      |
| Fan GND                | Pi GND (pin 6) through transistor/MOSFET    |
| Transistor gate/base   | GPIO pin (default: GPIO14, physical pin 8)  |
| Transistor/MOSFET GND  | Pi GND                                      |

You can change the GPIO pin if needed.

## 1. Enable gpio-fan overlay

Edit `/boot/config.txt`:
```
dtoverlay=gpio-fan,gpiopin=14,temp=55000
```

Breakdown:
- `gpiopin=14` → controls your transistor board on GPIO14 (pin 8)
- `temp=55000` → 55.0 °C turn-on temperature

The fan will typically turn off around 50 °C due to built-in hysteresis.

Reboot to apply:
```
sudo reboot
```

## 2. Verify the fan turns on/off

Check CPU temperature:
```
vcgencmd measure_temp
```

Or continuously:
```
watch -n 1 vcgencmd measure_temp
```

The fan will start when temperature > 55°C and stop when it drops ~5°C below that.

## 3. Optional: Change temperature threshold

You can adjust `temp=` as needed:

Example for a cooler system:
```
dtoverlay=gpio-fan,gpiopin=14,temp=60000
```
Example for more aggressive cooling:
```
dtoverlay=gpio-fan,gpiopin=14,temp=50000
```
Values are in millidegrees Celsius.

## 4. Optional: Use a different GPIO pin

If your transistor board uses a different pin:
```
dtoverlay=gpio-fan,gpiopin=18,temp=55000
```

Just ensure the wiring and transistor board match the selected pin.

## 5. Conflicts with Hardware PWM Setup

If you move to the hardware-PWM `fan.py` controller (recommended), you must remove or comment out any `gpio-fan` overlays:
```
# dtoverlay=gpio-fan,gpiopin=14,temp=55000
```

The two systems should not run at the same time.

## When to Use the Simple ON/OFF Method

This is the right option when:
- You want minimal resource usage
- Your fan is old-school 5V and not PWM-capable
- You don’t care about noise or granularity
- You want the most robust “just works” behaviour

Use the PWM Python controller when you want:
- Variable fan speeds
- Much quieter operation
- Temperature ramping
- Logging
- Finer control logic



## License

MIT
