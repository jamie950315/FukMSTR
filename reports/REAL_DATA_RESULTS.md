# Real data experiment results

## Dataset

Source: public Tardis.dev Deribit `BTC-PERPETUAL` `incremental_book_L2` sample for 2020-04-01.

Converted local dataset:

- Output book CSV used in runs: `data/real_tardis/book_depth10_500ms_10000.csv`
- Standard packaged copy: `data/real_tardis/book_depth10_500ms.csv`
- Top depth: 10
- Sampling interval: 500 ms
- Raw incremental rows consumed: 1,423,349
- Snapshots written: 10,000
- First timestamp: `2020-04-01T00:00:00.245000Z`
- Last timestamp: `2020-04-01T01:24:57.338000Z`
- Trade file: none. Trade-derived features are set to zero by the existing pipeline.

The raw 152 MB gzip file is intentionally not packaged. Recreate it with:

```bash
lob-microprice-lab fetch-tardis-sample --out data/real_tardis --depth 10 --sample-ms 500 --max-snapshots 10000
```

## Commands used

```bash
lob-microprice-lab convert-tardis-l2 \
  --input data/real_tardis/tardis_deribit_BTC-PERPETUAL_2020-04-01_incremental_book_L2.csv.gz \
  --out data/real_tardis/book_depth10_500ms_10000.csv \
  --depth 10 \
  --sample-ms 500 \
  --max-snapshots 10000

lob-microprice-lab tune \
  --book data/real_tardis/book_depth10_500ms_10000.csv \
  --config configs/example.yaml \
  --out runs/real_tardis_tuning \
  --horizons-sec 1,2,5 \
  --thresholds-bps 0.25,0.5,1 \
  --models logistic \
  --edge-thresholds 0.05,0.10 \
  --clean

lob-microprice-lab tune \
  --book data/real_tardis/book_depth10_500ms_10000.csv \
  --config configs/example.yaml \
  --out runs/real_tardis_tuning_edge_extreme \
  --horizons-sec 5 \
  --thresholds-bps 0.25,0.5,1,2 \
  --models logistic \
  --edge-thresholds 0.5,0.7,0.9 \
  --clean

lob-microprice-lab tune \
  --book data/real_tardis/book_depth10_500ms_10000.csv \
  --config configs/example.yaml \
  --out runs/real_tardis_tuning_h10 \
  --horizons-sec 10 \
  --thresholds-bps 0.5,1,2,3 \
  --models logistic \
  --edge-thresholds 0.5,0.7,0.9 \
  --clean
```

## Top trials by predictability rank score

|   combined_rank | search_set          |   horizon_sec |   threshold_bps |   edge_threshold |   accuracy |   balanced_accuracy |   macro_f1 |   majority_accuracy_valid |   trades |   hit_rate |   mean_net_pnl_bps |   total_net_pnl_bps |
|----------------:|:--------------------|--------------:|----------------:|-----------------:|-----------:|--------------------:|-----------:|--------------------------:|---------:|-----------:|-------------------:|--------------------:|
|               1 | fast_predictability |             1 |            1    |             0.1  |   0.578667 |            0.575549 |   0.363929 |                  0.921333 |     2624 |  0.0750762 |         -1.25282   |         -3287.4     |
|               2 | fast_predictability |             1 |            1    |             0.05 |   0.578667 |            0.575549 |   0.363929 |                  0.921333 |     2830 |  0.0699647 |         -1.28035   |         -3623.39    |
|               3 | fast_predictability |             1 |            0.25 |             0.1  |   0.544667 |            0.55725  |   0.372729 |                  0.892667 |     2647 |  0.0740461 |         -1.26096   |         -3337.77    |
|               4 | fast_predictability |             1 |            0.25 |             0.05 |   0.544667 |            0.55725  |   0.372729 |                  0.892667 |     2836 |  0.0719323 |         -1.26822   |         -3596.66    |
|               5 | fast_predictability |             1 |            0.5  |             0.1  |   0.543667 |            0.556877 |   0.371925 |                  0.892667 |     2649 |  0.0739902 |         -1.26114   |         -3340.77    |
|               6 | fast_predictability |             1 |            0.5  |             0.05 |   0.543667 |            0.556877 |   0.371925 |                  0.892667 |     2836 |  0.0719323 |         -1.26822   |         -3596.66    |
|               7 | five_sec_edge       |             5 |            1    |             0.5  |   0.437771 |            0.51494  |   0.411846 |                  0.694361 |      513 |  0.378168  |          0.018138  |             9.30479 |
|               8 | five_sec_edge       |             5 |            1    |             0.9  |   0.437771 |            0.51494  |   0.411846 |                  0.694361 |        0 |  0         |          0         |             0       |
|               9 | five_sec_edge       |             5 |            1    |             0.7  |   0.437771 |            0.51494  |   0.411846 |                  0.694361 |       75 |  0.48      |         -0.0952843 |            -7.14632 |
|              10 | fast_predictability |             2 |            1    |             0.1  |   0.502167 |            0.539175 |   0.375084 |                  0.854285 |     2566 |  0.128995  |         -1.08579   |         -2786.13    |
|              11 | fast_predictability |             2 |            1    |             0.05 |   0.502167 |            0.539175 |   0.375084 |                  0.854285 |     2775 |  0.125045  |         -1.10212   |         -3058.38    |
|              12 | fast_predictability |             5 |            1    |             0.1  |   0.437771 |            0.51494  |   0.411846 |                  0.694361 |     2517 |  0.247517  |         -0.707272  |         -1780.2     |
|              13 | fast_predictability |             5 |            1    |             0.05 |   0.437771 |            0.51494  |   0.411846 |                  0.694361 |     2763 |  0.234528  |         -0.780173  |         -2155.62    |
|              14 | five_sec_edge       |             5 |            0.5  |             0.7  |   0.410744 |            0.493649 |   0.403528 |                  0.635636 |       57 |  0.403509  |          0.33521   |            19.107   |
|              15 | five_sec_edge       |             5 |            0.25 |             0.7  |   0.410077 |            0.491675 |   0.402827 |                  0.635302 |       56 |  0.392857  |          0.339671  |            19.0216  |

## Top trials by mean net PnL per event trade

| search_set    |   horizon_sec |   threshold_bps |   edge_threshold |   accuracy |   balanced_accuracy |   macro_f1 |   trades |   hit_rate |   mean_net_pnl_bps |   total_net_pnl_bps |
|:--------------|--------------:|----------------:|-----------------:|-----------:|--------------------:|-----------:|---------:|-----------:|-------------------:|--------------------:|
| ten_sec_edge  |            10 |            1    |              0.7 |   0.398798 |            0.464763 |   0.400051 |       49 |   0.714286 |           1.03788  |            50.8562  |
| ten_sec_edge  |            10 |            2    |              0.5 |   0.353039 |            0.440472 |   0.352547 |      356 |   0.58427  |           0.730688 |           260.125   |
| ten_sec_edge  |            10 |            1    |              0.5 |   0.398798 |            0.464763 |   0.400051 |      404 |   0.584158 |           0.649928 |           262.571   |
| ten_sec_edge  |            10 |            0.5  |              0.5 |   0.400468 |            0.447578 |   0.396537 |      410 |   0.580488 |           0.496059 |           203.384   |
| ten_sec_edge  |            10 |            3    |              0.5 |   0.38143  |            0.416378 |   0.347691 |      340 |   0.573529 |           0.400031 |           136.011   |
| five_sec_edge |             5 |            0.25 |              0.7 |   0.410077 |            0.491675 |   0.402827 |       56 |   0.392857 |           0.339671 |            19.0216  |
| five_sec_edge |             5 |            0.5  |              0.7 |   0.410744 |            0.493649 |   0.403528 |       57 |   0.403509 |           0.33521  |            19.107   |
| ten_sec_edge  |            10 |            3    |              0.7 |   0.38143  |            0.416378 |   0.347691 |       43 |   0.674419 |           0.196509 |             8.44988 |
| ten_sec_edge  |            10 |            0.5  |              0.7 |   0.400468 |            0.447578 |   0.396537 |       75 |   0.573333 |           0.167863 |            12.5897  |
| five_sec_edge |             5 |            2    |              0.7 |   0.437104 |            0.484671 |   0.36795  |       77 |   0.519481 |           0.126035 |             9.70469 |

## Top trials by total net PnL

| search_set    |   horizon_sec |   threshold_bps |   edge_threshold |   accuracy |   balanced_accuracy |   macro_f1 |   trades |   hit_rate |   mean_net_pnl_bps |   total_net_pnl_bps |
|:--------------|--------------:|----------------:|-----------------:|-----------:|--------------------:|-----------:|---------:|-----------:|-------------------:|--------------------:|
| ten_sec_edge  |            10 |            1    |              0.5 |   0.398798 |            0.464763 |   0.400051 |      404 |   0.584158 |           0.649928 |           262.571   |
| ten_sec_edge  |            10 |            2    |              0.5 |   0.353039 |            0.440472 |   0.352547 |      356 |   0.58427  |           0.730688 |           260.125   |
| ten_sec_edge  |            10 |            0.5  |              0.5 |   0.400468 |            0.447578 |   0.396537 |      410 |   0.580488 |           0.496059 |           203.384   |
| ten_sec_edge  |            10 |            3    |              0.5 |   0.38143  |            0.416378 |   0.347691 |      340 |   0.573529 |           0.400031 |           136.011   |
| ten_sec_edge  |            10 |            1    |              0.7 |   0.398798 |            0.464763 |   0.400051 |       49 |   0.714286 |           1.03788  |            50.8562  |
| five_sec_edge |             5 |            0.5  |              0.7 |   0.410744 |            0.493649 |   0.403528 |       57 |   0.403509 |           0.33521  |            19.107   |
| five_sec_edge |             5 |            0.25 |              0.7 |   0.410077 |            0.491675 |   0.402827 |       56 |   0.392857 |           0.339671 |            19.0216  |
| ten_sec_edge  |            10 |            0.5  |              0.7 |   0.400468 |            0.447578 |   0.396537 |       75 |   0.573333 |           0.167863 |            12.5897  |
| five_sec_edge |             5 |            2    |              0.7 |   0.437104 |            0.484671 |   0.36795  |       77 |   0.519481 |           0.126035 |             9.70469 |
| five_sec_edge |             5 |            1    |              0.5 |   0.437771 |            0.51494  |   0.411846 |      513 |   0.378168 |           0.018138 |             9.30479 |

## Interpretation

The strongest direction-classification signal in this subset is the 1 second / 1 bps logistic model, with balanced accuracy around 0.576. Raw accuracy is lower than a majority-flat baseline because the classifier uses balanced class weights and deliberately predicts rare up/down moves instead of always predicting flat.

The cost-aware search shows that high probability-edge gating is essential. Low edge thresholds create many trades and negative event PnL after the configured 1.5 bps cost. A 10 second / 1 bps label with 0.5 edge threshold produced the highest total net PnL in this sample, while a 10 second / 1 bps label with 0.7 edge threshold produced the highest mean net PnL per trade.

These results are evidence of weak short-horizon signal in the selected historical sample. They are not evidence of deployable profitability because the backtest still ignores queue position, partial fills, latency, market impact, and exchange matching details.
