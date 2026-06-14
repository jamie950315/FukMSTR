# Research V69 Fixed Flow Hour Gate Results

## Decision

- Passed: `True`
- Failed checks: ``
- Excluded hours: `14,16,20,12,5,23`

## Aggregate

- Trades: `184`
- Total net pnl: `4187.522330` bps
- Account return: `335.001786%`
- Mean net pnl: `22.758274` bps
- Win rate: `0.538043`
- Holdout total net pnl: `1158.060172` bps
- Holdout positive fold rate: `1.000000`

## Hour Gate

The excluded hours are selected from design folds 1-4 only. Holdout folds 5-7 are not used to choose the hours.

```json
{
  "excluded_hours": [
    14,
    16,
    20,
    12,
    5,
    23
  ],
  "selected_exclusion_count": 6,
  "design_trades": 104,
  "design_total_net_pnl_bps": 3029.4621580954317,
  "design_positive_fold_rate": 0.75,
  "design_worst_fold_net_pnl_bps": -233.75885037254855,
  "design_passed": true,
  "attempts": [
    {
      "excluded_hours": [],
      "selected_exclusion_count": 0,
      "design_trades": 141,
      "design_total_net_pnl_bps": -1232.794156355656,
      "design_positive_fold_rate": 0.5,
      "design_worst_fold_net_pnl_bps": -1172.013307621272,
      "design_passed": false
    },
    {
      "excluded_hours": [
        14
      ],
      "selected_exclusion_count": 1,
      "design_trades": 128,
      "design_total_net_pnl_bps": -21.044296297836354,
      "design_positive_fold_rate": 0.75,
      "design_worst_fold_net_pnl_bps": -1172.013307621272,
      "design_passed": false
    },
    {
      "excluded_hours": [
        14,
        16
      ],
      "selected_exclusion_count": 2,
      "design_trades": 121,
      "design_total_net_pnl_bps": 779.544926012541,
      "design_positive_fold_rate": 0.75,
      "design_worst_fold_net_pnl_bps": -839.1674851091002,
      "design_passed": false
    },
    {
      "excluded_hours": [
        14,
        16,
        20
      ],
      "selected_exclusion_count": 3,
      "design_trades": 116,
      "design_total_net_pnl_bps": 1441.4384162852616,
      "design_positive_fold_rate": 0.75,
      "design_worst_fold_net_pnl_bps": -716.9781126535627,
      "design_passed": false
    },
    {
      "excluded_hours": [
        14,
        16,
        20,
        12
      ],
      "selected_exclusion_count": 4,
      "design_trades": 112,
      "design_total_net_pnl_bps": 2016.6957051464872,
      "design_positive_fold_rate": 0.75,
      "design_worst_fold_net_pnl_bps": -677.1555088433139,
      "design_passed": false
    },
    {
      "excluded_hours": [
        14,
        16,
        20,
        12,
        5
      ],
      "selected_exclusion_count": 5,
      "design_trades": 108,
      "design_total_net_pnl_bps": 2586.065499624666,
      "design_positive_fold_rate": 0.75,
      "design_worst_fold_net_pnl_bps": -677.1555088433139,
      "design_passed": false
    },
    {
      "excluded_hours": [
        14,
        16,
        20,
        12,
        5,
        23
      ],
      "selected_exclusion_count": 6,
      "design_trades": 104,
      "design_total_net_pnl_bps": 3029.4621580954317,
      "design_positive_fold_rate": 0.75,
      "design_worst_fold_net_pnl_bps": -233.75885037254855,
      "design_passed": true
    }
  ]
}
```

## Fold Summary

fold,trades,total_net_pnl_bps,mean_net_pnl_bps,account_return_pct,win_rate,is_design,is_holdout
1,31,-233.75885037254844,-7.540608076533821,-18.700708029803874,0.4838709677419355,True,False
2,25,993.7416330884453,39.74966532353781,79.49933064707562,0.52,True,False
3,26,1665.2111929259052,64.04658434330405,133.2168954340724,0.6153846153846154,True,False
4,22,604.2681824536294,27.466735566074064,48.34145459629035,0.6818181818181818,True,False
5,31,756.3132140959526,24.39720045470815,60.50505712767621,0.5806451612903226,False,True
6,26,31.5445784767478,1.2132530183364538,2.5235662781398243,0.46153846153846156,False,True
7,23,370.20237933442536,16.095755623235885,29.616190346754028,0.43478260869565216,False,True

## Delay Summary

entry_delay_minutes,trades,total_net_pnl_bps,mean_net_pnl_bps,account_return_pct,win_rate
0,184,4187.522330002557,22.758273532622592,335.0017864002046,0.5380434782608695
1,183,4110.409753562065,22.46125548394571,328.83278028496517,0.5355191256830601
2,183,4295.113687395176,23.470566597787847,343.6090949916141,0.5409836065573771
5,185,4430.770162814235,23.950108988185054,354.4616130251388,0.5405405405405406
10,188,4036.1013229986816,21.468624058503625,322.88810583989454,0.5478723404255319

## Extra Cost Summary

extra_cost_bps,trades,total_net_pnl_bps,mean_net_pnl_bps,account_return_pct,win_rate
0.0,184,4187.522330002557,22.758273532622592,335.0017864002046,0.5380434782608695
4.0,184,3451.5223300025573,18.758273532622592,276.1217864002046,0.532608695652174
8.0,184,2715.5223300025573,14.758273532622594,217.24178640020457,0.5108695652173914
16.0,184,1243.5223300025564,6.758273532622589,99.48178640020451,0.4891304347826087

## Interpretation

V69 is a design-only hour-gated fixed-policy audit on true BTCUSDC public aggTrade flow bars. It is positive after fees, positive across all holdout folds, positive under tested entry delays, and positive under the tested extra-cost stresses. This is a research candidate, not a live-profit guarantee.
