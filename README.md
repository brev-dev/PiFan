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

## License

MIT
