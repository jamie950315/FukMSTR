# Research V74 Commands

Run the combined execution-contract and monthly-cooldown audit:

```bash
make btcusdc-fixed-flow-combined-contract-v74
```

Run the focused test target:

```bash
make test-btcusdc-v74
```

The audit fixes the V72 execution contract and V73 monthly cooldown policy before evaluation: signal-hour gate, maximum 60-minute entry delay, 16 bps extra cost per trade, and a one-negative-month trigger with a two-month cooldown.
