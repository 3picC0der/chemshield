# Setup, start-up, reset and the demo

Everything needed to build the rig, start it yourself, put it back to a clean state, and run the PPR demo. Commands are in the order you run them, each with a line saying what it does.

| Part | What it covers | When |
|---|---|---|
| [A. Set up the Raspberry Pi](#a-set-up-the-raspberry-pi) | Flash the SD card, install the software, wire the Uno, calibrate the probe | Once |
| [B. Set up the Mac](#b-set-up-the-mac) | Software and keys on the laptop | Once |
| [C. The two network modes](#c-the-two-network-modes) | Phone hotspot for work, the Pi's own Wi-Fi for the demo and the C2 test | Once to switch it on, then it follows the Pi |
| [D. Start the system](#d-start-the-system) | Power on, connect the Mac, start the station and the HMI | Every time |
| [E. Reset and rerun](#e-reset-and-rerun) | Repeat INT-Spec 1; switch to another scenario; save the logs | Between runs |
| [F. The demo scenario](#f-the-demo-scenario) | A numbered script: "dose X mL, then see Y" | At the PPR |
| [G. The HMI alone on one laptop](#g-the-hmi-alone-on-one-laptop) | Usability study (Spec 5) and rehearsals; no Pi | Whenever |
| [H. When something goes wrong](#h-when-something-goes-wrong) | Symptoms and fixes | As needed |

**The pieces.** A laptop runs the HMI (the screen). A Raspberry Pi 5 runs the **station**: the gateway, Model A, the recovery planner and the audit log. An Arduino Uno on the Pi's USB reads the pH probe and lights the "dose now" light. Doses are added by hand with syringes. See [EVIDENCE_EXPLAINED.md](EVIDENCE_EXPLAINED.md#the-system-in-one-page) for the picture.

**Safe handling.** Wear gloves and goggles whenever you handle the reagents. The CHE approval covers only the listed solutions: 0.5 M and 0.005 M NaOH, 0.5 M and 0.005 M HCl, and the 0.05 M HCl used by hand.

**Never put these in git or in a chat:** the operator key (`hmi/secrets/operator.key`, git-ignored), the Pi's Wi-Fi password, any SSH private key. This repository is public.

---

## A. Set up the Raspberry Pi

**You need:** Raspberry Pi 5 with its 27 W USB-C power supply; a microSD card (16 GB or more) and a reader; the Arduino Uno R3 and its USB cable; the pH probe and its board (BNC plug); a jumper wire for the E-stop; an LED with a 220 Ω to 1 kΩ resistor (optional, the Uno's built-in "L" light works without it); the laptop; a phone for a hotspot.

### A1. Write the SD card (on the Mac)

1. Install **Raspberry Pi Imager** from raspberrypi.com/software and open it.
2. Choose the device **Raspberry Pi 5**, the system **Raspberry Pi OS (64-bit)** (the Lite version is enough; we used Debian 13 "trixie", Python 3.13), and your microSD card.
3. In the customisation steps set:
   - **Hostname**: anything (for example `chemshield`). You will reach the Pi by its IP address.
   - **Username** `chemshield` and a password (only used at the Pi's own keyboard; SSH passwords are switched off below).
   - **Wi-Fi**: the name and password of your phone's hotspot, and your country.
   - **Remote access**: turn SSH on and choose **public-key authentication only**. Paste your public key. To copy yours: `cat ~/.ssh/id_ed25519_second.pub | pbcopy`. (No key yet? `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_second` makes one. Use a key that is yours personally, not one that belongs to an employer.)
   - **Raspberry Pi Connect**: leave off.
4. Write the card, eject it, put it in the Pi.

### A2. First boot

1. Plug the Pi's **own USB-C supply into a wall socket**. Do not power it from the laptop: a laptop port cannot give it enough current and it misbehaves. A red light comes on, then a green light flickers while it boots. Wait about 2 minutes.
2. Switch the phone's **Personal Hotspot** on (Settings, Personal Hotspot, Allow Others to Join) and leave that screen open. The Pi joins by itself.
3. Join the Mac to the same hotspot, then find the Pi's address: `arp -a` (look for a `172.20.10.x` entry other than your own), or `nmap -sn 172.20.10.0/28`. The first device after the phone is usually `172.20.10.2`.

### A3. Log in over SSH (on the Mac)

```bash
KEY=$HOME/.ssh/id_ed25519_second
ssh -i $KEY -o IdentitiesOnly=yes chemshield@172.20.10.2     # use the address you found
```

`-i` picks your personal key and `IdentitiesOnly=yes` stops ssh from offering any other key. Answer `yes` to the first-connection question. You are now typing on the Pi.

### A4. Install the software (on the Pi)

```bash
sudo apt-get update                                  # refresh the package list
sudo apt-get install -y git iptables                 # git to fetch the code, iptables for the firewall
git clone https://github.com/3picC0der/chemshield.git   # the project
cd chemshield
python3 -m venv .venv                                # a private Python environment
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt pytest     # the libraries (a few minutes)
```

Check it and fit Model A to this Pi:

```bash
.venv/bin/python -m pytest hmi/tests gateway/tests sim/tests model_a/tests -q   # all tests should pass
.venv/bin/python -W ignore -m model_a.train          # retrain Model A here so its file matches this Pi's scikit-learn
```

`pytest` runs the project's automatic tests (72 passed on the Mac, in about 40 s). `model_a.train` rebuilds `model_a/artifacts/model_a.joblib` from the dataset in the repository; it makes `git` see that file as modified, which is harmless (see H for updating the code later).

### A5. Give the Pi and the Mac the same operator key (on the Mac)

The laptop signs every request with this key and the Pi only accepts requests signed with it.

```bash
cd <your repo folder on the Mac>
.venv/bin/python -m hmi.keygen                       # makes hmi/secrets/operator.key (once; git-ignored)
ssh -i $KEY -o IdentitiesOnly=yes chemshield@172.20.10.2 'mkdir -p ~/chemshield/hmi/secrets && chmod 700 ~/chemshield/hmi/secrets'
scp -i $KEY -o IdentitiesOnly=yes hmi/secrets/operator.key chemshield@172.20.10.2:chemshield/hmi/secrets/operator.key
ssh -i $KEY -o IdentitiesOnly=yes chemshield@172.20.10.2 'chmod 600 ~/chemshield/hmi/secrets/operator.key'
```

The four lines: make the key; make the folder on the Pi; copy the key; lock its permissions. If the station later prints "using the built-in demo key", the key is missing or different on one side.

### A6. Wire the Uno

| From | To |
|---|---|
| pH board **V+** | Uno **5V** |
| pH board **G** (next to V+) | Uno **GND** |
| pH board **Po** | Uno **A0** (leave **To** and **Do** empty) |
| Uno **D8** | resistor, then the LED's long leg; the LED's short leg to **GND** (optional) |
| Uno **D2** | a plain wire to **GND** (this is the E-stop: wire in = released, wire pulled out = E-STOP pressed) |
| Probe | BNC plug on the pH board |
| Uno USB | a USB port on the Pi (it also powers the Uno) |

Never use D0 or D1 (they carry the USB data). The Uno's built-in "L" light (pin 13) copies the dose light, so the rig works before the LED is wired. With D2 left open the Uno reads the E-stop as pressed and refuses every dose.

| The light | Meaning |
|---|---|
| Steady on | A dose was approved: add it now, then press DOSE ADDED |
| Slow blink | RECOVERY: an unsafe event was confirmed, operator doses are locked |
| Fast blink | HALTED or the E-stop is pressed |
| Off | Normal, or the Pi has been silent for 2 s |

### A7. Put the program on the Uno (on the Pi)

```bash
sudo apt-get install -y --no-install-recommends arduino-mk arduino-core-avr gcc-avr avr-libc avrdude   # the AVR compiler and uploader
cd ~/chemshield/firmware/uno/chemshield_uno
make            # compiles the sketch (about 10 KB of the Uno's 32 KB)
make upload     # sends it to the Uno over USB (the station must not be running; with auto-start: sudo systemctl stop chemshield-station first)
cd ~/chemshield
.venv/bin/python firmware/uno/uno_tool.py watch      # prints the pH and volts every second; Ctrl+C to stop
```

`watch` should print `PH,x.xx` lines. A warning "A0 at rail" means the probe plug or one of the three board wires is loose.

### A8. Calibrate the probe (on the Pi, station stopped)

With auto-start installed (D6), run `sudo systemctl stop chemshield-station` first and `sudo systemctl start chemshield-station` afterwards. Do this every morning and again just before the demo. Rinse the probe in distilled water and blot it between buffers; use the value printed on each bottle.

```bash
cd ~/chemshield
.venv/bin/python firmware/uno/uno_tool.py cal 7.00     # probe in the pH 7 buffer: waits until steady, then stores the point
.venv/bin/python firmware/uno/uno_tool.py cal 4.00     # probe in the pH 4 buffer
.venv/bin/python firmware/uno/uno_tool.py show         # prints the stored points and the slope (about 160 to 180 mV per pH unit)
.venv/bin/python firmware/uno/uno_tool.py watch        # back in the pH 7 buffer: the reading should be 7.0 within 0.1
```

The Uno keeps up to three points (4, 7, 10) in its memory and fits a line through them; it survives unplugging. The planner assumes the probe is right within 0.03 pH, and 0.1 to 0.2 pH of error can make it overshoot. (`uno_tool.py clear` erases the stored points if one went wrong.)

---

## B. Set up the Mac

```bash
git clone https://github.com/3picC0der/chemshield.git     # the project (Belal's Mac has it in ~/Development/Personal/chemshield-rig)
cd chemshield
python3.12 -m venv .venv                                  # Python 3.12 or newer
.venv/bin/pip install -r requirements.txt pytest          # libraries
brew install nmap                                         # the port scanner the C2 check uses
.venv/bin/python -m pytest hmi/tests gateway/tests sim/tests model_a/tests -q    # the tests should pass here too
```

Copy `hmi/secrets/operator.key` into this folder if the key was made on another machine (step A5 makes it here).

**Tidy variables used below.** Set them once in each terminal (change the first line to your own folder; on a fresh clone the Python is `.venv/bin/python`):

```bash
cd ~/Development/Personal/chemshield-rig        # your repo folder on the Mac; it must hold hmi/secrets/operator.key
PY=../chemshield/.venv/bin/python               # Belal's Mac keeps the environment in the sibling folder; otherwise PY=.venv/bin/python
KEY=$HOME/.ssh/id_ed25519_second                # your personal SSH key
PI=10.42.0.1                                    # the Pi on its own Wi-Fi (on the phone hotspot it is the 172.20.10.x address)
```

---

## C. The two network modes

| | Work mode (phone hotspot) | Demo mode (the Pi's own Wi-Fi) |
|---|---|---|
| Who makes the Wi-Fi | Your phone | The Pi: network `ChemShield-Lab` |
| Internet on the Mac | Yes | **No** |
| Pi's address | `172.20.10.x` (changes) | `10.42.0.1` (fixed) |
| Firewall | Off unless you run `fw` | **On**: only SSH (22) and the station (8000) get in |
| Use it for | Installing, `git pull`, working with Claude | The demo and the C2 test (ICS-AT-01) |

The Pi remembers both. By design, at every power-up it joins your phone if the hotspot is on and near, and otherwise starts its own Wi-Fi (see the note in D1 about the first cold start).

### C1. Switch the demo network on (once)

On the Pi (over SSH, with the station already running so that port 8000 is open). Choose a Wi-Fi password of 8 or more characters and **write it on a card**; do not put it in the repository.

```bash
cd ~/chemshield
nohup sudo bash gateway/firewall/c2_network.sh on '<choose-a-password>' >/dev/null 2>&1 &
exit
```

What the script does, in order: removes any old hotspot profile; starts a Wi-Fi hotspot named `ChemShield-Lab` on the Pi's `wlan0`; applies the firewall (`gateway/firewall/raspberry_pi_firewall_template.sh`: IP forwarding off, forwarding between networks dropped, incoming connections dropped except SSH, the station's port and DHCP); gives the hotspot the lowest priority and your phone's profile a higher one, so the phone wins when it is around; waits 8 s and applies the firewall again, because NetworkManager can switch forwarding back on when the Wi-Fi starts. It records what it did in `~/c2_evidence.txt`. `nohup ... &` and `exit` are there because your SSH session drops when the Wi-Fi changes.

Wait a minute, then on the Mac join the Wi-Fi **ChemShield-Lab** with that password. The Mac now has no internet. Check:

```bash
ssh -i $KEY -o IdentitiesOnly=yes chemshield@10.42.0.1 'cd ~/chemshield && bash gateway/firewall/c2_network.sh status'
```

You should see `wlan0` connected to `chemshield-ap`, `net.ipv4.ip_forward = 0`, and a list of INPUT rules ending in a `DROP` policy.

### C2. Go back to the phone hotspot

Switch the phone's hotspot on, then (over SSH on the Pi's Wi-Fi):

```bash
cd ~/chemshield
nohup sudo bash gateway/firewall/c2_network.sh off >/dev/null 2>&1 &
exit
```

`off` opens the firewall again, stops the Pi's hotspot and reconnects the Pi to your phone. Rejoin the Mac to the phone's hotspot and find the Pi's new address (A2).

### C3. Forgot the demo Wi-Fi password?

Over SSH on the Pi: `sudo nmcli -s -g 802-11-wireless-security.psk connection show chemshield-ap` prints it. Or run C1 again with a new one.

---

## D. Start the system

The same five steps every time the rig is powered up. In demo mode the Pi is `10.42.0.1`. With auto-start installed (D6) the Pi does D2 by itself.

### D1. Power on and connect

1. Plug the Pi into the wall socket and wait about 2 minutes. If the phone hotspot is on and near, switch it off so that the Pi starts `ChemShield-Lab`.
2. Join the Mac to **ChemShield-Lab**. *Not yet checked after a full power cycle:* the Pi is set up to start this network by itself (C1), but the first cold start since then has not been tried. If the network has not appeared after 3 minutes, switch the phone hotspot on, let the Pi join it (A2), SSH in over the phone's network and run C1 again.
3. Check the Uno is plugged into the Pi and the probe is in the pH 7 buffer or the tank.

### D2. On the Pi: firewall and station

*Skip this step if auto-start is installed (D6): the Pi did it at boot.*

```bash
ssh -i $KEY -o IdentitiesOnly=yes chemshield@10.42.0.1      # log in (from the Mac)
cd ~/chemshield
sudo bash gateway/firewall/c2_network.sh fw                 # firewall back on: the rules are lost at every reboot
nohup .venv/bin/python -W ignore -m hmi.station --ph-source uno > ~/station.log 2>&1 < /dev/null &    # start the station
sleep 10; head -4 ~/station.log                             # confirm it started
exit
```

- `c2_network.sh fw` re-applies the firewall and turns IP forwarding off. Run it after **every** power-up.
- `hmi.station --ph-source uno` is the station: gateway, Model A, planner, audit log, and the link to the Uno. `uno` means the real probe (`sim` is a simulated tank). It listens on port 8000 and finds the Uno at `/dev/ttyACM0` by itself.
- `nohup ... &` keeps it running after you log out; its messages go to `~/station.log`. Its evidence goes to `~/chemshield/hmi/logs/<date-time>-uno/` (`audit.jsonl`, the hash-chained log, and `model_a_decisions.csv`).
- The log's first lines should read: `ChemShield station: pH source PROBE, chemistry PLACEHOLDER, key from ...operator.key`. A "demo key" warning means the operator key is missing on the Pi (A5).

### D3. On the Mac: set the Pi's clock

```bash
$PY -m hmi.clock_sync --pi chemshield@$PI --station http://$PI:8000 \
    --ssh-option=-i$KEY --ssh-option=-oIdentitiesOnly=yes --ssh-option=-oBatchMode=yes
```

The laptop stamps every request with its own clock and the gateway rejects anything more than 2 s away from the Pi's clock (`Stale`). In demo mode the Pi has no internet time, so after each boot its clock can be hours off. This command sets it from the laptop over SSH, then checks the station's clock. It should print `... is +NN ms from this laptop: OK` twice. `$PY -m hmi.clock_sync --check --station http://$PI:8000` only checks.

### D4. On the Mac: start the HMI

```bash
$PY -m hmi --station http://$PI:8000 --operator "Belal"
```

This starts the HMI server on your laptop only (`127.0.0.1:8080`) and opens it in the browser. It signs every request with the operator key and forwards it to the Pi. Leave the terminal open; Ctrl+C stops it.

### D5. Check the screen before you begin

| Look at | It should show |
|---|---|
| Banner | NORMAL |
| Tank pH | A number updating every second, tagged **PROBE** (not SIMULATED) |
| Safety state | Command path: gateway only (signed) · Uno link: talking · Mixing lockout: clear · Model A: on · Audit chain: intact · E-stop: released |
| The Uno | Light off (steady on means a dose is pending) |

In the pH 7 buffer the reading should be 7.0 within 0.1. If not, calibrate (A8, with the station stopped).

**To stop everything.** HMI: Ctrl+C in its terminal. Station: over SSH, `pkill -f hmi.station` (with auto-start: `sudo systemctl stop chemshield-station`). Pi: `sudo shutdown now`, then wait for the green light to stop flashing before unplugging it.

### D6. Start by itself at power-up (optional)

*Status: the files are in the repository and tested against stubs. They are **not installed on the Pi yet**; until they are, do D2 by hand.* Install them once, with the Pi on the phone hotspot and the Mac on it too:

```bash
ssh -i $KEY -o IdentitiesOnly=yes chemshield@<pi-address>        # the phone-hotspot address (A2)
cd ~/chemshield
git fetch origin main && git checkout origin/main -- gateway/systemd gateway/firewall   # the new files (not git pull: the Pi's copy has local changes)
sudo bash gateway/systemd/install.sh                             # install, enable and start both services
bash gateway/systemd/install.sh status                           # check: both enabled and active, IP forwarding 0, INPUT policy DROP, ports 22 and 8000
```

The installer writes `chemshield-firewall.service` and `chemshield-station.service` into `/etc/systemd/system` (filling in the repository path and your user), checks them with `systemd-analyze verify`, stops a station you started by hand, enables both so that they start at every boot, starts them now and prints the status. At every boot the firewall service applies the C2 rules at once, again when the Wi-Fi is up, and keeps IP forwarding at 0 for two more minutes; the station service starts the station with the real probe, restarts it if it stops, and does not start without the operator key. Details: `gateway/systemd/README.md`.

With auto-start the start-up is: power the Pi (D1), set its clock from the Mac (D3), start the HMI (D4), check the screen (D5). The clock cannot be automated: in the demo network the Pi has no internet time, and the gateway rejects anything more than 2 s off.

| You want (on the Pi) | Command |
|---|---|
| See that it is running | `bash gateway/systemd/install.sh status` |
| Follow the station's messages | `journalctl -u chemshield-station -f` |
| Restart the station (new log folder; replaces E1's `pkill`) | `sudo systemctl restart chemshield-station` |
| Stop it for `make upload` or `uno_tool.py cal` (they need the serial port), then start it again | `sudo systemctl stop chemshield-station` … `sudo systemctl start chemshield-station` |
| Go back to starting by hand | `sudo bash gateway/systemd/install.sh remove` |

**Check the first cold start once, after installing** (this also shows that the Pi brings up `ChemShield-Lab` by itself): switch the phone's hotspot off, unplug the Pi, wait 10 s, plug it in, wait 3 minutes, join the Mac to `ChemShield-Lab`, then `curl -s -m 5 http://10.42.0.1:8000/api/state` should print the station's state, and `ssh -i $KEY -o IdentitiesOnly=yes chemshield@10.42.0.1 'bash ~/chemshield/gateway/systemd/install.sh status'` should show both services active, IP forwarding 0 and INPUT policy DROP.

---

## E. Reset and rerun

### E1. Run INT-Spec 1 again (cleanest: one log per run)

Each start of the station opens a new log folder and a new hash chain, which is what you want as evidence for each run.

1. Over SSH on the Pi (type these in the SSH session, not in one `ssh '...'` line):
   ```bash
   pkill -f hmi.station                        # stop the station (the Uno resets and comes back in NORMAL)
   cd ~/chemshield
   nohup .venv/bin/python -W ignore -m hmi.station --ph-source uno > ~/station.log 2>&1 < /dev/null &
   ```
   With auto-start installed (D6) it is one line instead: `sudo systemctl restart chemshield-station`.
2. Reload the HMI page in the browser (no need to restart the HMI).
3. Put the tank back: rinse the probe in distilled water, blot it, and use a **fresh cup of pH 7 buffer**; for the 5 L tank, see the note below.
4. Wait for the banner to say NORMAL with the pH inside 6.0 to 8.5.
5. Do the unsafe dose again (demo step 9), read the timing, then HALT DOSING if you use a cup.
6. Save the run's files (E3).

**Quicker, no restart.** Press HALT DOSING, put the probe back in clean buffer, press RESUME DOSING, and let the pH stay inside 6.0 to 8.5 for 60 s: the event closes by itself (`EVENT_CLOSED` in the audit log) and the banner returns to NORMAL. Cancel any dose the planner proposes meanwhile ("Not added: cancel it"), or untick "Automatic recovery" in the Engineer panel. The log then holds all the runs in one chain.

**The 5 L tank.** Each repeat adds about 60 mL of 0.05 M HCl and 6 to 8 mL of 0.5 M NaOH. After three repeats empty it and make fresh tank liquid (E4).

### E2. Switch to a different scenario

| You want | Do |
|---|---|
| Start the whole demo again from step 1 | E1 steps 1 and 2: the restart clears the counters, the 15 s lockout and any pending dose |
| Leave "operator decision required" (the planner gave up or Model A blocked a recovery dose) | ACKNOWLEDGE, HALT DOSING, RESUME DOSING: the planner tries again. Or restart the station |
| Recover from HALTED (E-stop, USB unplugged, HALT) | Fix the cause (push the D2 wire back in, plug the USB in), then RESUME DOSING |
| A big upset without risking the real tank | Simulation: `$PY -m hmi.demo` on the Mac (the full HMI on a simulated tank, 127.0.0.1:8080), or on the Pi `hmi.station --ph-source sim`. Then `$PY -m hmi.facilitator upset <name>` (or the Engineer panel): `medium_acid` or `medium_base` (60 mL of 0.5 M), `acid_upset_max` or `base_upset_max` (80 mL), `beyond_budget` (110 mL = 55 mmol: the planner must hand over to the operator), `high_level_base` (full tank), or `upset 7` (7 mL of 0.5 M acid, the INT-Spec 1 size). Between scenarios: `$PY -m hmi.facilitator reset` |
| A second, independent simulated HMI next to the real one | `$PY -m hmi.demo --port 8081 --station-port 8001` |
| A fresh day | Calibrate the probe (A8), then D1 to D5 |

### E3. Save the evidence of a run

On the Mac, in the repo folder (change the destination folder to the right one in `evidence/`):

```bash
mkdir -p evidence/09_INT-S1_recovery_mode_within_2s/data/rig_run_NEW
scp -i $KEY -o IdentitiesOnly=yes -r chemshield@$PI:chemshield/hmi/logs/ evidence/09_INT-S1_recovery_mode_within_2s/data/rig_run_NEW/
scp -i $KEY -o IdentitiesOnly=yes chemshield@$PI:c2_evidence.txt evidence/02_C2_gateway_sole_control_path/data/    # the network script's log
$PY -m hmi.verify_log evidence/09_INT-S1_recovery_mode_within_2s/data/rig_run_NEW/logs/<run>/audit.jsonl    # prints CHAIN OK
```

The HMI also downloads files (Engineer panel, "Recovery and exports": INT-S1 timing, pH log, 10-minute hold) and the audit log (CSV or JSONL). Then `git add evidence && git commit && git push`.

### E4. Make the 5 L tank

4.9 L distilled water plus 100 mL of baking-soda stock (4.20 g NaHCO₃ per litre), so 0.420 g in all. It rests near pH 8.3. With the probe in and the HMI open, add 0.05 M HCl in small portions while stirring until the HMI reads 6.8 to 7.2: about 18 mL in total. This is the "nominal" state used in the demo.

---

## F. The demo scenario

About 12 minutes. Each step says what to do (with the amount), what you will see, and what it proves. Open the matching folder in `evidence/` on GitHub as you go (its `TEST_SHEET.md` has the spec, procedure and result).

**Before the reviewers arrive** (15 minutes): D1 to D5; probe calibrated and the reading checked in pH 7 buffer (A8); the 5 L tank at pH 7 (E4) with the probe in and a stirrer or spoon ready; on the table, the four labelled bottles, the 0.05 M HCl, a 20 mL syringe and a 10 mL syringe, distilled water to rinse, gloves and goggles. Second terminal open on the Mac with `PY`, `KEY` and `PI` set (section B). *If you only have a cup of pH 7 buffer instead of the 5 L tank*, steps 1 to 9 work the same; after step 9 press HALT DOSING and skip step 10.

**Showing GitHub at the booth.** While the Mac is on `ChemShield-Lab` it has no internet. Open the evidence pages on a second device (a phone, or another laptop on a normal network), or read them from your local clone in an editor's Markdown preview (the plots show there too). Pages already open in browser tabs on the Mac stay on screen, but their links will not load.

| # | You do | You see | It proves |
|---|---|---|---|
| **1** | Stir the tank, or lift the probe and put it back. | The pH on the HMI, tagged PROBE, moves within a second or two. | The real chain: probe → Uno → Pi → laptop, once a second. |
| **2** | Hold up the four bottles (0.5 M and 0.005 M NaOH, 0.5 M and 0.005 M HCl) and the 0.05 M HCl; open `evidence/01_C1...`. | The strongest is NaOH 0.5 M = **1.96 wt%**, against the 5 wt% limit. | **C1.** |
| **3** | Manual dose: bottle **NaOH 0.5 M bulk (base)**, **10 mL**, press REQUEST DOSE. | Red **Model A block**, with its reason; the Uno's light stays off. Evidence, tab **Model A timing**: class HARMFUL, score about 1.00, about 1 ms. | **Spec 4**: a class and a score in milliseconds (limit 3 s). The dose would push a 5 L tank at pH 7 to about pH 10.4. |
| **4** | Manual dose: **NaOH 0.005 M fine (base)**, **25 mL**. | **Over limit** (`DOSE_LIMIT`, 20 mL cap); the light stays off. | **Spec 2**: dose cap. |
| **5** | Manual dose: **NaOH 0.005 M fine**, **10 mL**. | **Accepted**; the **Dose now** box says "Add 10 mL of NaOH 0.005 M fine now, then stir"; the Uno's light is steady on. Add 10 mL with the syringe, stir, press **DOSE ADDED**: the light goes off. | Only an approved dose lights the light. |
| **6** | At once, request the same 10 mL again. After the countdown ends, request it a third time, then press "Not added: cancel it". | **Mixing lockout** with a 15 s countdown; after it, **Accepted**. | **Spec 2**: at least 15 s between doses. |
| **7** | In a second Mac terminal: `$PY -m hmi.attack_station --station http://$PI:8000 --mode replay-now --n 100` and then `$PY -m hmi.attack_station --station http://$PI:8000 --mode stale --age 5 --n 100`. If a "Dose now" box appears, press "Not added: cancel it". | The script prints `replayed/stale rejected: 100/100 = 100.00%` each time. On the HMI the counters **Replayed** and **Stale** rise by 100 each, and the audit log fills with `REUSED_NONCE` and `STALE_TIMESTAMP`. | **Spec 3.** (The evidence run used 1,000 of each.) |
| **8** | Open the **Engineer and demo panel** at the bottom of the HMI. Under "Security tests" press **Send an unsigned command**, then **Send one signed with a wrong key**. Then in the terminal: `$PY -m hmi.c2_check --pi $PI --ssh-key $KEY --out /tmp/c2_demo` (about 1 minute; explain the network picture while it runs). | **Not authorised** for both buttons (HTTP 401). The check ends with eight `[PASS]` lines and **`C2 PASS: only the gateway path works`**: ports 22 and 8000 only, SSH key-only, forwarding off, nothing reached the Uno. | **C2.** Open `evidence/02_C2...` for the saved runs and the network plot. |
| **9** | Add **0.05 M HCl** straight into the tank with the 20 mL syringe, in 20 mL portions, stirring each time, until the banner turns red: about 55 to 60 mL in total (more if the tank started above pH 7). Do **not** use the HMI for this: it plays the part of a bad command that got past the gateway. | The pH falls on the trend. After three readings below 6.0 the banner turns red, **UNSAFE DOSING EVENT, RECOVERY IN PROGRESS**, and the Uno's light starts a slow blink. Open Evidence, **Recovery-mode timing**: confirmed → RECOVERY in about **1 ms**, Uno confirmed locked in about 8 ms, shown on the HMI in a few hundred ms. | **INT-Spec 1** (limit 2,000 ms). With a cup instead of the tank: read the timing, then press **HALT DOSING**. |
| **10** | Follow each **Dose now** box: add that amount with the syringe, stir, press DOSE ADDED. The next box appears about 15 s later. Keep going until the banner says "pH back in 6.0–8.5". | The banner shows the recovery timer (x / 300 s) and **Event reagent x / 50 mmol** (expect a few mmol, about 5 to 8 mL of 0.5 M NaOH in all, far below 50). The event closes after the pH has stayed inside for 60 s and the banner returns to NORMAL. | **C3** live (limit 50 mmol), **Spec 6** and **INT-Spec 2** live. Then show the 600-event histogram `evidence/03_C3.../plots/`. |
| **11** | Show the pump label and the datasheet page, and the balance runs. | Rated 19 to 65 mL/min. | **Spec 7** (limit 500 mL/min). |
| **12** | Click **Check the hash chain** under the audit log, and switch the log to "rejected only". | **CHAIN OK** with the number of records, and every rejection from steps 3, 4, 6, 7 and 8 listed with its reason. | The audit log: every decision recorded, tamper-evident. |

If a recovery dose is blocked by Model A, the banner says "operator decision required": press ACKNOWLEDGE, then HALT DOSING and RESUME DOSING, and the planner tries again. This happens in about 1 of 60 large simulated upsets.

**If time allows**

| Extra | You do | You see |
|---|---|---|
| **E-stop** | Pull the D2 wire out of the Uno. | HALTED, the light blinks fast, the audit log says "E-STOP pressed on the rig"; every dose is refused. Push the wire back in, press RESUME DOSING. Nothing restarts by itself. |
| **Uno link lost** | Unplug the Uno's USB cable. | HALTED, "Uno link lost", doses refused until you plug it back in and press RESUME DOSING. |
| **Worst case, in simulation** (second HMI, no risk to the tank) | `$PY -m hmi.demo --port 8081 --station-port 8001`, then in its Engineer panel inject `acid_upset_max` (80 mL of 0.5 M). | A full automatic recovery, back inside the band in about 2 minutes, under 50 mmol, with no overshoot. The screen says SIMULATED. |

After the demo, save the run (E3) and shut down (end of D).

---

## G. The HMI alone on one laptop

For the usability study (Spec 5) and for rehearsals. No Pi, no tank: the HMI runs the real gateway, Model A, planner and audit log on a simulated tank. A purple **SIMULATED pH** band stays on the screen.

```bash
git clone https://github.com/3picC0der/chemshield.git
cd chemshield
python3.12 -m venv .venv                       # Python 3.12 or newer; on Windows: py -3 -m venv .venv  (and .venv\Scripts\python for .venv/bin/python)
.venv/bin/pip install -r requirements.txt      # libraries (a few minutes)
.venv/bin/python -m hmi.demo                   # station + HMI on this laptop; opens http://127.0.0.1:8080
```

The facilitator controls the simulation from a second terminal, so the participant never sees them:

```bash
.venv/bin/python -m hmi.facilitator reset                # between participants: fresh tank at pH 7
.venv/bin/python -m hmi.facilitator upset medium_acid    # task 3: an acid upset (recovery starts)
.venv/bin/python -m hmi.facilitator escalate             # task 4: "operator decision required" now
```

The script, the task card and the scoring are in `07_S5_sus_at_least_80/SUS_study_kit.md`; scores are computed with `07_S5_sus_at_least_80/code/sus_score.py`. The study has not been run on Windows by us.

---

## H. When something goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| HMI: `address already in use` (port 8080) | An older HMI is still running on the Mac | `pkill -f "python -m hmi"` in a Mac terminal, then start it again |
| Every dose is rejected as **Stale** | The Pi's clock is off (it has no internet time) | D3 |
| HMI says the station cannot be reached | Mac on the wrong Wi-Fi; station not started; or the firewall script was not run and the Pi is still on the phone's network | Check the Wi-Fi name; `curl -s -m 5 http://$PI:8000/api/state` should print the station's state; redo D2 |
| `ChemShield-Lab` does not appear | The phone hotspot is on and near, so the Pi joined it | Switch the hotspot off and wait 1 to 2 minutes, or redo C1 over the phone's network |
| The banner shows **SIMULATED** on the real rig | The station was started with `--ph-source sim` | Restart it with `--ph-source uno` |
| pH is a fixed number, or jumps, or the Uno warns "A0 at rail" | Loose BNC plug or board wire; probe dry; no calibration | Reseat the plug and the three wires (V+, G, Po); keep the probe wet; calibrate (A8) |
| Every dose is refused and the light blinks fast | E-stop wire (D2) is out, or the dosing is HALTED | Push the wire back in; press RESUME DOSING |
| The Uno's light never comes on for an accepted dose | The Uno is locked (slow blink = RECOVERY) or not running the sketch | Check the light pattern; redo A7 |
| Audit log shows "Uno lost the heartbeat" every few seconds to minutes | Not explained yet; it did not change any test result | Note it; it can briefly turn the light off |
| `git pull` on the Pi refuses ("local changes") | `model_a/artifacts` was retrained on the Pi (A4) | On the Pi: `git fetch origin main && git reset --hard origin/main`, then retrain Model A (A4). `hmi/secrets/` and `hmi/logs/` are git-ignored and stay |
| `address already in use` when you start the station by hand on the Pi | The auto-started station is already running on port 8000 | `sudo systemctl stop chemshield-station` first (or use `sudo systemctl restart chemshield-station` instead of starting it by hand) |
| Model A blocks a correct recovery dose | The probe lags after a large upset and Model A reads that as risk | ACKNOWLEDGE, HALT DOSING, RESUME DOSING (E2) |
| `c2_check` reports an extra open port or `ip_forward=1` | The firewall was not re-applied after a reboot or a Wi-Fi restart | `sudo bash gateway/firewall/c2_network.sh fw` on the Pi, then run the check again |

Everything the station decides is in `~/station.log` and `~/chemshield/hmi/logs/` on the Pi. To read the station's state from the Mac: `curl -s http://$PI:8000/api/state`.
