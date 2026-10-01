# Hardsignal Labs power/load control v0.1

Sequential Python 3.11+ SCPI control for a Rigol DP832 source and Siglent
SDL1030X-E electronic load. Development and tests use injected mocks only.
The legacy hardware scripts are preserved; `.gitignore` excludes the local
`connections_live.json` profile. Do not run the legacy hardware
scripts as tests; the configured test suite is under `tests/`.

The DP832 is the controlled source and authoritative target-side voltage/current
limiting layer. The SDL is a controlled load/discharge device, **not primary target
protection**. Software checks do not establish safe wiring or replace physical
protection. No sweeps, fault injection, Husky control, automatic experiment
sequences, automatic enable, discovery, or concurrent control are implemented.

## Connection status

| Instrument/backend | Status |
| --- | --- |
| DP832 USB VISA/USBTMC | Identity and startup OFF states verified live on 2026-10-01; retained for fallback/debug use. |
| DP832 raw TCP SCPI | Implemented/configurable permanent backend, pending LAN licence activation and live validation. |
| SDL raw TCP SCPI | Identity and startup OFF state verified live on 2026-10-01. |

A TCP endpoint requires an explicit host and port. No live addresses or default
TCP ports are supplied. Raw TCP is newline-framed SCPI, not VXI-11. No automatic
USB/TCP fallback occurs; changing backend is an explicit configuration choice.

## CLI

Run from this repository; offline use requires no VISA dependency:

```sh
python3 -m lab_power_control idn --dry-run
python3 -m lab_power_control status --dry-run
python3 -m lab_power_control rigol --channel 1 --voltage 3.30 --current-limit 0.20 --dry-run
python3 -m lab_power_control siglent --mode cc --current 0.05 --dry-run
python3 -m lab_power_control all-off --dry-run
```

Every command requires exactly one of `--dry-run` or `--hardware`. There is no
CLI ON command, discovery command, or arbitrary SCPI passthrough. Missing mode
selection is an error. Hardware mode also requires `--connections PATH` containing
both endpoints. Both instruments are opened and verified before command dispatch;
a startup failure aborts dispatch, including an `all-off` CLI request. Only an
already-identified driver can be explicitly shut down through the library.

All commands accept:

- `--config PATH`: target safety policy JSON; otherwise built-in SafetyPolicy defaults.
- `--connections PATH`: connection profile JSON, required in hardware mode.
- `--log PATH`: append/flush timestamped JSONL; otherwise logs go to stderr.

JSON results go to stdout and include `dry_run` and `startup_state`. Startup state
records contain identities and observed ON/OFF states for DP832 CH1–CH3 and SDL
input. ON is reported explicitly; it is not a reason to silently turn hardware OFF.
The `idn` and `status` commands observe state without changing it, including at session exit.
The `rigol` and `siglent` commands explicitly configure settings while leaving the
selected output/input OFF. After any attempted control write, session cleanup
attempts to turn both identified instruments OFF. `all-off` explicitly requests OFF.

Dry-run creates mocks, never hardware transports, even when a connection profile
is supplied. Mock measurements are zero and marked simulated; they are not a
connected-circuit model. Supplying `--log` can write a file even in dry-run mode.

## Read-only status

```sh
python3 -m lab_power_control status --dry-run
# For separately authorized live use:
python3 -m lab_power_control status --hardware --connections /path/to/connections.json
```

`status` uses the same identity-first startup and closes without shutdown writes.
It emits identities plus CH1–CH3 output states, voltage setpoints (V), current
limits (A), and measured voltage/current/power (V/A/W). All physical channels are
observed even when the control policy permits only CH1; observation does not
change or enforce configuration limits. SDL reports input state, `static_mode`,
`cc_current_setpoint` (A) when static mode is CC, and measured V/A/W. In all
other static modes the field is `stored_cc_current_setpoint` (A): this stored
preset is inactive unless CC mode is selected. Status never selects CC.
Static-mode configuration is not proof of the currently active test function. Readings are sequential, not atomic.

Exact queries (no other SCPI commands):

| Instrument | Queries and provenance |
| --- | --- |
| DP832 | `*IDN?`; `:OUTP? CHn`; `:SOURn:VOLT?`; `:SOURn:CURR?`; `:MEAS:VOLT? CHn`; `:MEAS:CURR? CHn`; `:MEAS:POWE? CHn`, for n=1,2,3. DP800 guide PDF pp. 48, 87–88, 114, 107, 60, 59, 59 respectively. |
| SDL1030X-E | `*IDN?`; `:SOUR:INP?`; `:SOUR:FUNC?`; `:SOUR:CURR?`; `:MEAS:VOLT?`; `:MEAS:CURR?`; `:MEAS:POW?`. SDL1000X guide PDF pp. 15, 18, 19, 20, 17, 17, 17 respectively. |

State queries occur at startup and again when collecting status. Both identities
must pass startup before status configuration/measurement queries are dispatched.
The verified vendor sources and hashes are in [SCPI_EVIDENCE.md](SCPI_EVIDENCE.md).
In particular, Rigol uses `POWE`, while Siglent uses `POW`.

There are no `transport.write` calls on this path, including TCP query internals.
Queries necessarily transmit their request bytes; only query commands are sent.
No output/input, mode, range, trigger, protection, or configuration writes occur,
including on read/parse failures. Malformed, nonfinite, or negative numeric
responses and unknown states/modes abort with a nonzero CLI result and no partial
JSON success result. A secondary failure while logging an instrument exception is
attached as a note. Already-ON and already-OFF physical states are preserved.
`Experiment.status()` requires an observation-only session before control activity.

See [COMMISSIONING.md](COMMISSIONING.md) for the operator-reported live `idn`
commissioning results for `idn` and `status`. Development and automated validation
use offline tests only.

## Profiles and transport migration

The sample safety policy is `lab_power_control/config/stm32_safe.json`: CH1,
0–3.3 V, 0.2 A source current limit, 0.1 A load current, and 0.66 W. Built-in defaults
match it. These limits are illustrative, not certification for every STM32 board.
Values must be finite, within configured bounds, and compatible with device/channel
ceilings. Source power is voltage times current limit; load power uses the configured
source voltage ceiling times requested load current. There is no hardware power trip
or continuous monitoring provided by this package.

Copy `config/connections_usb.template.json` from inside the package to a local
profile. Fill the DP832 USB VISA resource and SDL TCP host/port. The templates use
null endpoints deliberately and fail validation until completed. Do not commit a
populated site-specific profile or runtime logs.

After DP832 LAN activation and service validation, replace only the profile's
`rigol` object with the structure in `connections_tcp.template.json`: `backend`
set to `tcp`, explicit `host`, `port`, and `timeout` in seconds. Remove `resource`
or set it to null. The SDL object, safety policy, drivers, logger, and CLI remain
unchanged. Restore the USB object to use USB again. The same command works with
either completed profile:

```sh
python3 -m lab_power_control idn --dry-run --connections /path/to/connections.json
```

For separately authorized live commissioning, replace `--dry-run` with
`--hardware`. No live command was executed during development. Hardware USB
requires the optional `hardware` dependencies declared in `pyproject.toml`, the
PyVISA `@py` backend, libusb/PyUSB, and appropriate Linux USB permissions.

## Exact startup and shutdown behavior

Driver construction performs **no I/O** and starts unverified. Hardware transport
construction may establish a USB/TCP connection. Loading/validating a profile does
not establish a connection.

`connected_session()` opens the explicitly selected transports, then performs for
each instrument, sequentially:

1. Query `*IDN?`.
2. Require exactly four nonempty identity fields; compare vendor/model exactly,
   case-sensitively, after trimming fields. Family/substr matching is not accepted.
3. Query physical switch state: DP832 `:OUTP? CH1`, `CH2`, `CH3`; SDL `:SOUR:INP?`.
4. Normalize valid states to ON/OFF, expose them in `session.startup_state`, and
   emit timestamped `physical_state` and `startup_state` log records.

No configuration, ON, or OFF command is sent during startup. Opening a session
**does not mean hardware is OFF**. An identity mismatch prevents state queries
and writes to that instrument. An unknown/malformed state aborts startup rather
than assuming OFF. Startup failures close opened connections without altering
outputs. Already-ON states remain unchanged in observation-only sessions, including
normal exit and application exceptions before any control write.

An explicit configuration operation first verifies identity and safety limits,
then turns its selected output/input OFF and confirms that state before setting
values. Source current limit is set before voltage; SDL selects static CC and
disables short/external input control. Readbacks must match within 1e-8 absolute
tolerance, with no silent quantization. Library ON methods require an identified,
configured instrument and fresh configuration/safety readbacks; they do not
requery identity on every enable. Only explicit calls can enable hardware.

Once a control write is attempted, operation errors and context exit attempt safe
shutdown. The coordinated order is SDL input OFF, then DP832 CH1/CH2/CH3 OFF,
even for channels outside normal policy. Every eligible action is attempted after
partial transport or logging failures. OFF writes require positive identification
in the current session. Explicit `Experiment.all_off()` reports unverified
instruments as skipped failures; it never sends them OFF commands. Shutdown
invalidates configuration readiness, so enabling again requires reconfiguration.

Failure of OFF delivery/readback means shutdown is unconfirmed. `ShutdownError`
contains all collected failures. A primary operation/transport exception remains
the surfaced failure; secondary logging/shutdown errors are attached as exception
notes. Logging failure does not prevent eligible emergency OFF writes. The owning
connection context closes every opened handle after cleanup; observation-only
contexts close without sending OFF. `Experiment` alone does not own handles.

## Library API and architecture

```python
import sys
from lab_power_control import SafetyPolicy
from lab_power_control.connections import connected_session
from lab_power_control.logger import JsonlLogger

with connected_session(SafetyPolicy(), JsonlLogger(sys.stderr)) as lab:
    print(lab.startup_state)  # offline by default; no configuration or enabling
    lab.rigol.configure(1, voltage=3.3, current_limit=0.2)
    lab.siglent.configure_cc(0.05)
    lab.all_off()
```

Use `Connections.load_file(path)` and pass `connections=...` to the context. Only
explicit `dry_run=False` selects hardware. Drivers accept an injected Transport,
SafetyPolicy, and logger. Advanced callers owning their own transports can use
`with Experiment(rigol, siglent)` for identity/state startup and activity-dependent
shutdown; those callers must close their transports. Use fresh drivers for a new
session and one exclusive controller/thread per pair.

- `errors.py`: shared InstrumentError, SafetyError, IdentityError, TransportError,
  TransportTimeout, and ShutdownError hierarchy.
- `io_transport.py`: Transport protocol, USB VISA, raw TCP, complete stateful mock.
- `connections.py`: Endpoint/Connections validation, factory, handle ownership.
- `safety.py`: immutable target limits, channel and numerical validation.
- `instrument.py`: identity, physical-state reporting, audit and failure handling.
- `rigol_dp832.py`: configure/readback, individual setters, measure, output_on/off.
- `siglent_sdl1030xe.py`: configure_cc, measure, input_on/off.
- `experiment.py`: startup observations and sequential all_off coordination.
- `logger.py`: JsonlLogger using a caller-owned stream.
- `__main__.py`: CLI; `__init__.py`: public drivers, policy, coordinator, exceptions.
- `pyproject.toml`: sole packaging metadata, dependencies, package data and test paths.

Logs distinguish requested operations, raw replies, validated numeric responses,
startup states, failures, and shutdown attempts/results. Measurement validation
means a finite nonnegative response, not independent physical metrology or a
continuous limit watchdog. Both transports have explicit timeouts; TCP additionally
bounds total response reception and rejects reuse after framing/I/O failure.

## Offline verification and live-validation limits

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t . -v
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
python3 -m flake8 --isolated --select E,F,W --max-line-length 100 lab_power_control tests
python3 -m autopep8 --recursive --diff --max-line-length 100 lab_power_control tests
git diff --check
git status --short
```

Tests inject mock transports/factories and cover startup states, identity gates,
no implicit writes, partial shutdown failures, primary error preservation, USB/TCP
command equivalence, dry-run isolation, and no fallback. Never run the old hardware
scripts as part of this suite. Generated caches are excluded by `.gitignore`.

See [SCPI_EVIDENCE.md](SCPI_EVIDENCE.md) for exact commands, vendor manual references,
and hashes. Before any separate live validation, verify USB setup, actual identity
strings, DP832 LAN activation, TCP service/ports, firmware readbacks, static-CC
behavior, resolution, source timer/tracking/trigger states, external/front-panel
control, and physical OFF behavior with no target attached. Software cleanup cannot
guarantee OFF after cable failure, process termination, or external re-enabling.
Separate battery discharge requires a reviewed voltage policy and cutoff; v0.1
does not automate that sequence.
