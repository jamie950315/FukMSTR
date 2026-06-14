# Research V71 Commands

Run the dense entry-delay stress audit for the V69 fixed-flow hour-gated BTCUSDC candidate:

```bash
make btcusdc-fixed-flow-dense-delay-stress-v71
```

Run the focused test target:

```bash
make test-btcusdc-v71
```

The audit keeps the V68 fixed candidate and V69 locked excluded-hour gate unchanged. It rebuilds delayed ledgers for entry delays from 0 through 120 minutes at one-minute resolution, then evaluates both signal-hour and delayed-entry-hour gate application.
