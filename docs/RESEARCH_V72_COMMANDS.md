# Research V72 Commands

Run the cost-delay execution contract audit for the V69/V71 fixed-flow BTCUSDC candidate:

```bash
make btcusdc-fixed-flow-cost-delay-contract-v72
```

Run the focused test target:

```bash
make test-btcusdc-v72
```

The audit keeps the V68 fixed candidate and V69 locked excluded-hour gate unchanged. It uses the V71 dense delayed ledgers and scans extra cost against maximum allowed entry delay to identify whether a bounded execution contract survives conservative cost stress.
