# Research V207 BTCUSDC Real-Trade CLI Preflight

## Decision

- Status: `real_money_cli_blocked`
- Allow real-money launch: `False`
- Failed checks: `readiness_gate_passed`
- Message: Do not launch real-money trading. CLI preflight checks failed.

## What Changed

V207 adds a `real-trade-btcusdc` CLI command.

The command does not place exchange orders. It only runs the same real-money launch preflight rules and returns a non-zero exit code when launch is blocked.

## Gate Checks

| Check | Current Result |
|---|---:|
| V204 readiness gate passed | False |
| Explicit real-money arm supplied | True |
| Runtime source clean | True |
| Real-money launch allowed | False |

## Iteration Metrics

| Metric | V207 |
|---|---:|
| Strategy thresholds changed | No |
| Entry/exit logic changed | No |
| Leverage logic changed | No |
| Places live orders | No |
| Adds guarded real-money CLI entry | Yes |
| Allows real-money launch now | No |

## Interpretation

V207 makes the safety gate harder to bypass by giving real-money operation a dedicated CLI entry that refuses to proceed unless preflight passes.

This remains blocked for real-money use because V204 is still not ready.
