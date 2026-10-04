# Start the firewall and the station by themselves at boot

Two systemd services for the Raspberry Pi, so that powering the Pi up is enough: the firewall
(C2) is on and the station is listening before anyone logs in.

| Service | Runs as | What it does |
|---|---|---|
| `chemshield-firewall.service` | root, once per boot | `boot_firewall.sh`: applies the C2 firewall (the same rules as `gateway/firewall/c2_network.sh fw`) right away, again when `wlan0` is connected, again 8 s later, and for two more minutes whenever NetworkManager turns IP forwarding back on. If the Wi-Fi never connects the rules stay on anyway |
| `chemshield-station.service` | the Pi's user | `python -m hmi.station --ph-source uno` from the repository folder, restarted if it stops. It does not start unless `hmi/secrets/operator.key` exists |

Not automated, on purpose: the Pi's clock. In the demo network the Pi has no internet time and the
gateway rejects anything more than 2 s off its clock, so run `python -m hmi.clock_sync` from the
laptop after every boot (`evidence/SETUP.md`, D3).

## Install, check, remove (on the Pi, from the repository folder)

```bash
sudo bash gateway/systemd/install.sh            # fills in the repository path and your user, checks the files
                                                # with systemd-analyze, enables both services and starts them
bash gateway/systemd/install.sh status          # enabled? running? IP forwarding 0? INPUT policy DROP? ports 22 and 8000?
sudo bash gateway/systemd/install.sh remove     # back to starting by hand (the firewall rules stay until a reboot)
```

## Day to day

| You want | Command |
|---|---|
| Follow the station's messages | `journalctl -u chemshield-station -f` |
| Restart the station (a new log folder and audit chain) | `sudo systemctl restart chemshield-station` |
| Stop it, for `make upload` or `uno_tool.py cal` (they need the serial port) | `sudo systemctl stop chemshield-station`, and `sudo systemctl start chemshield-station` afterwards |
| Run the station by hand instead | `sudo systemctl stop chemshield-station`, then the command in `evidence/SETUP.md`, D2 |

The firewall allows SSH and the station on the Pi's Wi-Fi only, so an Ethernet cable will not reach
the Pi while it is on.

## Tests

`python -m pytest gateway/tests/test_systemd_autostart.py` renders the two units in a dry run and
runs the boot script against stubs (no host firewall is touched). `install.sh` also runs
`systemd-analyze verify` on the Pi before it enables anything.
