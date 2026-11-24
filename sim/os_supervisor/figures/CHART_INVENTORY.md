# OS Supervisor Stateflow chart inventory

Source: `os_supervisor_chart.slx`, read from the copied model using `sfroot` and `find` (Stateflow API).

## States and entry actions

### INIT

```text
INIT
entry:
state_id=0; reason=0; epoch=nowMs;
hasHB=false; hasResult=false; healthy=false; healthySince=-1;
leds(1)=0; leds(2)=0; leds(3)=0;
```

### FRESH

```text
FRESH
entry:
state_id=1; reason=1;
leds(1)=1; leds(2)=0; leds(3)=0;
```

### FAILSAFE

```text
FAILSAFE
entry:
state_id=3;
leds(1)=0; leds(2)=0; leds(3)=1;
```

### HOLD

```text
HOLD
entry:
state_id=2; reason=9;
leds(1)=0; leds(2)=1; leds(3)=0;
```

## Transitions

- `FAILSAFE` -> `INIT`: `[u(5)>0 && healthy && healthySince>=0 && nowMs-healthySince>=lim(4)]`
- `INIT` -> `FRESH`: `[healthy && lastHB>epoch && lastResult>epoch]`
- `HOLD` -> `FRESH`: `[healthy]`
- `FRESH` -> `HOLD`: `[hasResult && sourceAge>=lim(2)]`
- `INIT` -> `FAILSAFE`: `[sourceExpired]{reason=10;}`
- `FRESH` -> `FAILSAFE`: `[hbExpired]{reason=3;}`
- `FRESH` -> `FAILSAFE`: `[sourceExpired]{reason=10;}`
- `HOLD` -> `FAILSAFE`: `[hbExpired]{reason=3;}`
- `HOLD` -> `FAILSAFE`: `[sourceExpired]{reason=10;}`
- Default chart entry -> `INIT`: implicit default transition (no guard or action label).

## Chart interface

| Name | Scope | Type | Size |
|---|---|---|---|
| `u` | Input | `double` | `'[5 1]'` |
| `lim` | Input | `double` | `'[6 1]'` |
| `state_id` | Output | `double` | `'1'` |
| `reason` | Output | `double` | `'1'` |
| `leds` | Output | `double` | `'[4 1]'` |
| `ages_ms` | Output | `double` | `'[2 1]'` |

Both `u` and `lim` are typed `double` vectors. `u` carries current time, heartbeat time, result time, age-at-send, and the activity flag. `lim` carries six timeout/threshold parameters (ms): `lim(1)` heartbeat timeout = 100; `lim(2)` stale source HOLD threshold = 200; `lim(3)` source expiry = 500; `lim(4)` recovery qualification = 1000; `lim(5)` clock/age allowance = 5; `lim(6)` activity indication duration = 20. Values are read from model-workspace variable `limits` = `[100 200 500 1000 5 20]`.
