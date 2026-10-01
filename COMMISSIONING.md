# First live commissioning — 2026-10-01

Operator-reported successful package-level `python3 -m lab_power_control idn`
execution using `--hardware` and the local connection profile:

- Rigol DP832 over USB/VISA: identity verified; CH1, CH2, and CH3 observed OFF.
- Siglent SDL1030X-E over Ethernet TCP: identity verified; input observed OFF.
- The log confirmed identity verification before state queries, with no
  configuration writes and no ON/OFF writes.

The site-specific profile `connections_live.json` is ignored and must not be
staged or committed. This note intentionally omits endpoint and profile values.
The commissioning confirms the live `idn` path only. New status configuration and
measurement queries were developed and tested offline; no hardware was contacted
as part of that work.


## Successful live status commissioning — 2026-10-01

The operator reports successful live package-level `status` commissioning:

- Rigol DP832 over USB/VISA: CH1–CH3 OFF, 0 V, and configured current limits of 3 A.
- Siglent SDL1030X-E over Ethernet TCP: input OFF, static mode CP, and zero measured power.

The SDL CC preset is stored configuration, inactive unless CC mode is selected;
non-CC status now labels it `stored_cc_current_setpoint`. No mode or instrument
state was changed during this follow-up development. Validation used offline tests
only; the live observations above were supplied by the operator. No endpoint
addresses or VISA resource strings are recorded here.
