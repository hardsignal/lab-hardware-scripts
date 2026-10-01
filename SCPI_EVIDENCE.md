# SCPI evidence for v0.1

Retrieved 2026-10-01. Page numbers below are one-based PDF pages.
Commands use SCPI short forms; `n` is 1, 2, or 3. Numeric arguments are
finite decimal strings with nine fractional digits. No arbitrary passthrough API.

## Rigol

Source: [DP800 Programming Guide, June 2021](https://beyondmeasure.rigoltech.com/acton/attachment/1579/f-03a1/1/-/-/-/-/DP800%20Programming%20Guide.pdf).
SHA-256: `5b8870e0e017523297c66b1bbd5aa97cc84298e779759069892d73d6745a98bc`.

| Implemented commands | Evidence |
| --- | --- |
| `*IDN?` | PDF 48, IEEE488.2 identity |
| `:INST:NSEL n` | PDF 56, printed 2-32, channel selection |
| `:SOURn:CURR value`, `:SOURn:CURR?` | PDF 107, printed 2-83, immediate current |
| `:SOURn:VOLT value`, `:SOURn:VOLT?` | PDF 114, printed 2-90, immediate voltage |
| `:OUTP CHn,ON`, `:OUTP CHn,OFF`, `:OUTP? CHn` | PDF 87–88, printed 2-63/64 |
| `:MEAS:VOLT? CHn`, `:MEAS:CURR? CHn` | PDF 59–60, printed 2-35/36 |
| `:MEAS:POWE? CHn` | PDF 59, printed 2-35, `:MEASure:POWEr[:DC]? [CH1\|CH2\|CH3]` |

Channel suffixes are explicit even after selection. Output queries return ON/OFF.
Current configuration controls the source current limit, not a separate OCP trip.

## Siglent

Source: [SDL1000X Programming Guide, official download](https://siglentna.com/download/8968/).
SHA-256: `bd3ec6896e35b1a59da11f9adef408fb4dd308d0e83724bd740d276ac92d1ba3`.
The vendor document index lists this guide under SDL1000X/X-E.

| Implemented commands | Evidence |
| --- | --- |
| `*IDN?` | PDF 15, common commands |
| `:SOUR:INP ON`, `:SOUR:INP OFF`, `:SOUR:INP?` | PDF 18, source input |
| `:SOUR:SHOR OFF`, `:SOUR:SHOR?` | PDF 18, short state |
| `:SOUR:FUNC CURR`, `:SOUR:FUNC?` | PDF 19, static mode |
| `:SOUR:CURR value`, `:SOUR:CURR?` | PDF 19–20, static CC setting |
| `:SOUR:EXT:INPUT OFF`, `:SOUR:EXT:INPUT?` | PDF 57, external input |
| `:MEAS:VOLT?`, `:MEAS:CURR?`, `:MEAS:POW?` | PDF 17, measurement subsystem |

Short mode is only disabled; fault injection is not implemented.

## Repository inspection and unverified details

Existing `siglent_dp832_test.py` demonstrates USB VISA for DP832 and Ethernet
VISA INSTR for SDL, and sends `*IDN?`. It was read, never imported or run.
`test_hardware.py` invokes external instrument commands; it is excluded by
`pyproject.toml`'s `testpaths = ["tests"]`.
Repository reconciliation consolidated the scaffold mock into `io_transport.py`,
exceptions into `errors.py`, and package data into `pyproject.toml`. Discovery
backends were not retained. The historical `config.py` was already absent.
Nearby home-directory SDL scripts contain abbreviated commands but do not prove
successful device operation; they were not executed or changed.

No unverified SCPI commands were added. The operator reports successful live
identity and startup state validation on 2026-10-01 for DP832 USB/VISA and SDL
Ethernet TCP; see [COMMISSIONING.md](COMMISSIONING.md). Endpoints remain explicit
local-profile settings, with no default host, port, or USB resource. This validates
the commissioned transports and initial OFF observations. The operator subsequently
reported successful live status readbacks, documented in COMMISSIONING.md. These
observations do not validate DP832 LAN availability, saved timer/trigger/tracking
states, or control behavior.



## Transport configuration update

The command dialect is unchanged by transport selection. DP832 initial commissioning
uses USB; its permanent planned backend is raw TCP after LAN licence activation.
Both adapters remain available through `connections.py`, with no driver changes.
SDL remains TCP. Host, USB resource, and TCP port have no live/default values.
Offline tests verify identical DP832 command streams across injected USB/TCP
factories and configuration-only CLI migration. These offline tests do not establish live
DP832 LAN availability. SDL TCP was subsequently verified by the operator.


## Startup state use

The documented `*IDN?` and output/input state queries now form session startup.
Strict identity verification precedes the state queries. Startup reports ON/OFF
without changing it; configuration and explicit shutdown are separate operations.
OFF commands are gated on positive identity in the current session. No new SCPI
syntax was introduced by reconciliation.


## Read-only status evidence and exact query sequence

Rechecked 2026-10-01 against the vendor PDFs with the SHA-256 values above.
No hardware was contacted for status development. `status` first uses the existing
startup sequence: DP832 `*IDN?`, then `:OUTP? CH1`, `:OUTP? CH2`, `:OUTP? CH3`;
SDL `*IDN?`, then `:SOUR:INP?`. Each identity must pass before that instrument's
state queries; both must pass before status dispatch.

After startup, status issues:

1. DP832 `:OUTP? CH1`, `:OUTP? CH2`, `:OUTP? CH3`.
2. For each n=1,2,3, in order: `:SOURn:VOLT?`, `:SOURn:CURR?`,
   `:MEAS:VOLT? CHn`, `:MEAS:CURR? CHn`, `:MEAS:POWE? CHn`.
3. SDL `:SOUR:INP?`, `:SOUR:FUNC?`, `:SOUR:CURR?`,
   `:MEAS:VOLT?`, `:MEAS:CURR?`, `:MEAS:POW?`.

Provenance is the command tables above. DP800 PDF 59 explicitly provides the
power query and channel parameter, so no channel-selection write is needed.
PDF 107/114 explicitly address configured current/voltage by source suffix.
The measurement queries return numeric A/V/W values; source queries return numeric
configured values. Status uses those readbacks rather than computing power.

SDL PDF 19 identifies `:SOUR:FUNC?` as the static-operation mode query, with
CC/CV/CP/CR/LED configuration. PDF 20 identifies `:SOUR:CURR?` as the stored static
CC preset query. Neither query syntax requires a mode-selection command or states
that the query changes mode. Status reads the stored CC preset in any reported
static mode and labels it separately from measurements. In CC the field is
`cc_current_setpoint`; otherwise it is `stored_cc_current_setpoint`, inactive
unless CC mode is selected. Status does not select a mode. It does not infer the
active transient/list/battery/test function from static configuration. The operator subsequently reported successful CP-mode status commissioning;
readback support across other firmware/modes remains to be validated separately; an
invalid reply aborts observation without attempting mode changes or fallback writes.

No unverified configuration queries are included. Physical state is queried twice
(startup and status); identity is queried once per instrument. No state-changing
SCPI command, `transport.write`, error-queue clear, reset, or shutdown is used.
