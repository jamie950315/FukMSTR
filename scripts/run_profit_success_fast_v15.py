from __future__ import annotations

import json

from lob_microprice_lab.kline_guard import KlineGuardSpec
from lob_microprice_lab.profit_success_fast import run_profit_success_fast


def main() -> int:
    res = run_profit_success_fast(
        base_ensemble_dir="runs/research_v09_ensemble_h90_5fold_stationary",
        kline_ensemble_dir="runs/research_v13_kline_h90_5fold_stationary_v12folds",
        out_dir="runs/local_v15_profit_success_fast_alpha0125",
        horizon_sec=90,
        cost_bps=1.5,
        latency_sec=0.5,
        selected_spec=KlineGuardSpec(
            edge_threshold=0.1,
            kline_alpha=0.125,
            ofi_col="ofi_sum_l5_norm",
            ofi_quantile=0.9,
            kline_col="kline_15s_rv_6_bps",
            kline_quantile=0.0,
        ),
        shift_null_runs=40,
        clean=True,
    )
    print(json.dumps({"gate_passed": res["aggregate"]["gate"]["passed"], "aggregate": res["aggregate"], "out_dir": res["out_dir"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
