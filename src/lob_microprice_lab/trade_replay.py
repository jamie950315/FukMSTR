from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


def build_trade_replay_payload(
    account_path: pd.DataFrame | str | Path,
    *,
    start: str,
    end: str,
    initial_balance_usdc: float = 10_000.0,
    title: str = "BTCUSDC V142 Replay",
    signal_reference: pd.DataFrame | str | Path | None = None,
    account_return_col: str = "account_return_pct",
    account_pnl_col: str = "account_pnl_bps",
) -> dict[str, Any]:
    frame = _read_account_path(
        account_path,
        account_return_col=account_return_col,
        account_pnl_col=account_pnl_col,
    )
    frame = _fill_missing_signal(frame, signal_reference)
    start_ts = _utc_timestamp(start)
    date_only_end = _is_date_only(end)
    filter_end_ts = _date_only_next_day(end) if date_only_end else _utc_timestamp(end)
    display_end_ts = filter_end_ts - pd.Timedelta(microseconds=1) if date_only_end else filter_end_ts
    if date_only_end:
        frame = frame.loc[(frame["timestamp"] >= start_ts) & (frame["timestamp"] < filter_end_ts)].copy()
    else:
        frame = frame.loc[(frame["timestamp"] >= start_ts) & (frame["timestamp"] <= filter_end_ts)].copy()
    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    frame = _prepare_replay_metrics(
        frame,
        account_return_col=account_return_col,
        account_pnl_col=account_pnl_col,
    )

    trades: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = [
        {
            "type": "boundary",
            "timestamp": start_ts.isoformat(),
            "label": "Start",
            "balance_usdc": float(initial_balance_usdc),
            "equity_return_pct": 0.0,
            "drawdown_pct": 0.0,
            "visible_trade_count": 0,
        }
    ]
    previous_balance = float(initial_balance_usdc)
    previous_return_pct = 0.0
    for index, row in frame.iterrows():
        equity_return_pct = _as_float(row.get("_replay_equity_return_pct"), previous_return_pct)
        balance_usdc = float(initial_balance_usdc) * (1.0 + equity_return_pct / 100.0)
        profit_pct = _as_float(row.get("_replay_account_return_pct"), equity_return_pct - previous_return_pct)
        leverage = _as_float(row.get("account_leverage"), 0.0)
        position_weight = _as_float(row.get("position_weight"), 1.0)
        amount_usdc = max(previous_balance, 0.0) * leverage * position_weight
        trade = {
            "index": int(index),
            "timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
            "source": _as_text(row.get("source", "")),
            "leg": _as_text(row.get("leg", "")),
            "side": _side_label(row.get("signal")),
            "side_source": _as_text(row.get("side_source", "")),
            "amount_usdc": amount_usdc,
            "leverage": leverage,
            "position_weight": position_weight,
            "profit_pct": profit_pct,
            "profit_usdc": balance_usdc - previous_balance,
            "result": "win" if profit_pct > 0.0 else "loss" if profit_pct < 0.0 else "flat",
            "balance_usdc": balance_usdc,
            "equity_return_pct": equity_return_pct,
            "drawdown_pct": _as_float(row.get("_replay_drawdown_pct"), 0.0),
            "direction_probability": _optional_float(row.get("direction_probability")),
            "high_confidence_rescue_5x": bool(row.get("high_confidence_rescue_5x", False)),
            "account_pnl_bps": _as_float(row.get("_replay_account_pnl_bps"), 0.0),
            "raw_net_pnl_bps": _as_float(row.get("net_pnl_bps"), 0.0),
            "indicator_key": _as_text(row.get("indicator_key", "")),
        }
        trades.append(trade)
        timeline.append(
            {
                "type": "trade",
                "timestamp": trade["timestamp"],
                "label": f"Trade {len(trades)}",
                "balance_usdc": balance_usdc,
                "equity_return_pct": equity_return_pct,
                "drawdown_pct": trade["drawdown_pct"],
                "trade_index": len(trades) - 1,
                "visible_trade_count": len(trades),
                "result": trade["result"],
            }
        )
        previous_balance = balance_usdc
        previous_return_pct = equity_return_pct

    timeline.append(
        {
            "type": "boundary",
            "timestamp": display_end_ts.isoformat(),
            "label": "End",
            "balance_usdc": previous_balance,
            "equity_return_pct": previous_return_pct,
            "drawdown_pct": timeline[-1]["drawdown_pct"] if timeline else 0.0,
            "visible_trade_count": len(trades),
        }
    )
    monthly_returns: dict[str, float] = {}
    if trades:
        trade_frame = pd.DataFrame(trades)
        trade_frame["month"] = pd.to_datetime(trade_frame["timestamp"], utc=True).dt.strftime("%Y-%m")
        for month, month_frame in trade_frame.groupby("month", sort=True):
            first = month_frame.iloc[0]
            last = month_frame.iloc[-1]
            opening_balance = float(first["balance_usdc"]) - float(first["profit_usdc"])
            closing_balance = float(last["balance_usdc"])
            monthly_returns[str(month)] = (closing_balance / opening_balance - 1.0) * 100.0 if opening_balance else 0.0
    final_balance = float(timeline[-1]["balance_usdc"])
    return {
        "title": title,
        "period": {"start": start_ts.isoformat(), "end": display_end_ts.isoformat()},
        "initial_balance_usdc": float(initial_balance_usdc),
        "summary": {
            "trade_count": len(trades),
            "final_balance_usdc": final_balance,
            "total_return_usdc": final_balance - float(initial_balance_usdc),
            "total_return_pct": (final_balance / float(initial_balance_usdc) - 1.0) * 100.0,
            "max_drawdown_pct": min([float(row["drawdown_pct"]) for row in timeline] or [0.0]),
            "win_rate": sum(1 for row in trades if row["result"] == "win") / len(trades) if trades else 0.0,
        },
        "timeline": timeline,
        "trades": trades,
        "monthly_returns_pct": monthly_returns,
    }


def write_trade_replay_page(
    *,
    account_path: pd.DataFrame | str | Path,
    out: str | Path,
    start: str,
    end: str,
    initial_balance_usdc: float = 10_000.0,
    title: str = "BTCUSDC V142 Replay",
    signal_reference: pd.DataFrame | str | Path | None = None,
    account_return_col: str = "account_return_pct",
    account_pnl_col: str = "account_pnl_bps",
) -> dict[str, str]:
    payload = build_trade_replay_payload(
        account_path,
        start=start,
        end=end,
        initial_balance_usdc=initial_balance_usdc,
        title=title,
        signal_reference=signal_reference,
        account_return_col=account_return_col,
        account_pnl_col=account_pnl_col,
    )
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data_path = out_path.with_name("replay_data.json")
    data_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    out_path.write_text(_render_replay_html(payload), encoding="utf-8")
    return {"html": str(out_path), "data_json": str(data_path)}


def _read_account_path(
    account_path: pd.DataFrame | str | Path,
    *,
    account_return_col: str = "account_return_pct",
    account_pnl_col: str = "account_pnl_bps",
) -> pd.DataFrame:
    frame = account_path.copy() if isinstance(account_path, pd.DataFrame) else pd.read_csv(account_path)
    if "timestamp" not in frame.columns:
        raise ValueError("account path must contain timestamp")
    required = {"account_leverage", account_return_col}
    if account_return_col == "account_return_pct":
        required.update({"equity_return_pct", "drawdown_pct"})
    if account_pnl_col:
        required.add(account_pnl_col)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"account path missing required columns: {', '.join(missing)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame


def _prepare_replay_metrics(
    frame: pd.DataFrame,
    *,
    account_return_col: str,
    account_pnl_col: str,
) -> pd.DataFrame:
    out = frame.copy()
    returns = pd.to_numeric(out[account_return_col], errors="coerce").fillna(0.0)
    out["_replay_account_return_pct"] = returns
    if account_return_col == "account_return_pct":
        out["_replay_equity_return_pct"] = pd.to_numeric(out["equity_return_pct"], errors="coerce").fillna(returns.cumsum())
        out["_replay_drawdown_pct"] = pd.to_numeric(out["drawdown_pct"], errors="coerce").fillna(0.0)
    else:
        equity = returns.cumsum()
        out["_replay_equity_return_pct"] = equity
        out["_replay_drawdown_pct"] = equity - equity.cummax()
    if account_pnl_col and account_pnl_col in out.columns:
        out["_replay_account_pnl_bps"] = pd.to_numeric(out[account_pnl_col], errors="coerce").fillna(0.0)
    else:
        out["_replay_account_pnl_bps"] = returns * 100.0
    return out


def _is_date_only(value: str) -> bool:
    text = str(value).strip()
    if len(text) != 10:
        return False
    try:
        parsed = pd.Timestamp(text)
    except ValueError:
        return False
    return parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0 and parsed.microsecond == 0


def _utc_timestamp(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def _date_only_next_day(value: str) -> pd.Timestamp:
    return _utc_timestamp(value) + pd.Timedelta(days=1)


def _fill_missing_signal(frame: pd.DataFrame, signal_reference: pd.DataFrame | str | Path | None) -> pd.DataFrame:
    out = frame.copy()
    if "signal" not in out.columns:
        out["signal"] = pd.NA
    out["signal"] = pd.to_numeric(out["signal"], errors="coerce")
    out["side_source"] = pd.Series(pd.NA, index=out.index, dtype="object")
    out.loc[out["signal"].notna(), "side_source"] = "account_path"
    if signal_reference is None:
        return out

    reference = signal_reference.copy() if isinstance(signal_reference, pd.DataFrame) else pd.read_csv(signal_reference, usecols=["timestamp", "signal"])
    if "timestamp" not in reference.columns or "signal" not in reference.columns:
        raise ValueError("signal reference must contain timestamp and signal columns")
    reference = reference[["timestamp", "signal"]].copy()
    reference["timestamp"] = pd.to_datetime(reference["timestamp"], utc=True)
    reference["_signal_reference_fill"] = pd.to_numeric(reference["signal"], errors="coerce")
    reference = reference.dropna(subset=["timestamp", "_signal_reference_fill"]).drop_duplicates("timestamp", keep="first")
    out = out.merge(reference[["timestamp", "_signal_reference_fill"]], on="timestamp", how="left")
    fill_mask = out["signal"].isna() & out["_signal_reference_fill"].notna()
    out.loc[fill_mask, "signal"] = out.loc[fill_mask, "_signal_reference_fill"]
    out.loc[fill_mask, "side_source"] = "signal_reference"
    return out.drop(columns=["_signal_reference_fill"])


def _as_float(value: object, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    return out if math.isfinite(out) else float(default)


def _optional_float(value: object) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _as_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _side_label(value: object) -> str:
    side = _as_float(value, 0.0)
    if side > 0:
        return "long"
    if side < 0:
        return "short"
    return "n/a"


def _render_replay_html(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(str(payload["title"]))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  color-scheme: light;
  --ink: #18202b;
  --muted: #6b7280;
  --line: #cdd5df;
  --panel: #f7f8fa;
  --paper: #ffffff;
  --gain: #087f5b;
  --loss: #b42318;
  --accent: #2457a7;
  --amber: #a65f00;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: #eef1f4;
  color: var(--ink);
  font-family: "Avenir Next", "Trebuchet MS", sans-serif;
}}
.shell {{
  max-width: 1320px;
  margin: 0 auto;
  padding: 22px;
}}
header {{
  display: grid;
  grid-template-columns: minmax(260px, 1fr) auto;
  gap: 18px;
  align-items: end;
  border-bottom: 2px solid var(--ink);
  padding-bottom: 14px;
}}
h1 {{
  margin: 0;
  font-size: 30px;
  letter-spacing: 0;
  line-height: 1.05;
}}
.subhead {{ margin-top: 8px; color: var(--muted); font-size: 13px; }}
.controls {{
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}}
button, select {{
  min-height: 36px;
  border: 1px solid var(--ink);
  background: var(--paper);
  color: var(--ink);
  padding: 7px 11px;
  font: inherit;
  border-radius: 5px;
}}
button {{ cursor: pointer; min-width: 92px; }}
button:hover, select:hover {{ background: #e7edf7; }}
.metrics {{
  display: grid;
  grid-template-columns: repeat(4, minmax(160px, 1fr));
  gap: 10px;
  margin: 16px 0 14px;
}}
.metric {{
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px;
}}
.metric .label {{
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .06em;
}}
.metric .value {{
  margin-top: 6px;
  font-size: 22px;
  font-weight: 700;
  white-space: nowrap;
}}
.metric .delta {{ margin-top: 4px; font-size: 12px; color: var(--muted); }}
.board {{
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 14px;
}}
#balanceChart {{
  width: 100%;
  height: 430px;
  display: block;
}}
.timelineControl {{
  display: grid;
  grid-template-columns: minmax(160px, auto) 1fr minmax(150px, auto);
  gap: 12px;
  align-items: center;
  margin-top: 10px;
}}
input[type="range"] {{ width: 100%; }}
.readout {{
  color: var(--muted);
  font-size: 12px;
  text-align: right;
  font-family: "SFMono-Regular", "IBM Plex Mono", monospace;
}}
.logs {{
  margin-top: 16px;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 6px;
  overflow: hidden;
}}
.logsHeader {{
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
  background: #f5f6f8;
}}
.logsHeader h2 {{ margin: 0; font-size: 17px; }}
.tableWrap {{
  max-height: 430px;
  overflow: auto;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}}
th, td {{
  border-bottom: 1px solid #e5e9ef;
  padding: 8px 9px;
  text-align: right;
  white-space: nowrap;
}}
th {{
  position: sticky;
  top: 0;
  z-index: 1;
  text-align: right;
  background: #f5f6f8;
  color: #384454;
}}
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align: left; }}
.win {{ color: var(--gain); font-weight: 700; }}
.loss {{ color: var(--loss); font-weight: 700; }}
.flat {{ color: var(--amber); font-weight: 700; }}
.empty {{ padding: 18px; color: var(--muted); }}
@media (max-width: 860px) {{
  header {{ grid-template-columns: 1fr; }}
  .controls {{ justify-content: flex-start; }}
  .metrics {{ grid-template-columns: repeat(2, minmax(140px, 1fr)); }}
  .timelineControl {{ grid-template-columns: 1fr; }}
  .readout {{ text-align: left; }}
}}
</style>
</head>
<body>
<div class="shell">
  <header>
    <div>
      <h1>{title}</h1>
      <div class="subhead" id="periodLabel"></div>
    </div>
    <div class="controls">
      <button id="playPause" type="button">Play</button>
      <select id="speedSelect" aria-label="Playback speed">
        <option value="1">1x</option>
        <option value="5">5x</option>
        <option value="20" selected>20x</option>
        <option value="60">60x</option>
        <option value="200">200x</option>
      </select>
    </div>
  </header>

  <section class="metrics" aria-label="Replay metrics">
    <div class="metric"><div class="label">Balance</div><div class="value" id="balanceValue"></div><div class="delta" id="tradeCountValue"></div></div>
    <div class="metric"><div class="label">Since Start</div><div class="value" id="sinceStartValue"></div><div class="delta" id="sinceStartPct"></div></div>
    <div class="metric"><div class="label">Since This Month</div><div class="value" id="sinceMonthValue"></div><div class="delta" id="sinceMonthPct"></div></div>
    <div class="metric"><div class="label">Drawdown</div><div class="value" id="drawdownValue"></div><div class="delta" id="currentTimeValue"></div></div>
  </section>

  <section class="board">
    <canvas id="balanceChart" width="1200" height="430" aria-label="Balance chart"></canvas>
    <div class="timelineControl">
      <div id="pointLabel"></div>
      <input id="timeSlider" type="range" min="0" max="0" value="0">
      <div class="readout" id="axisReadout"></div>
    </div>
  </section>

  <section class="logs">
    <div class="logsHeader">
      <h2>History Trading Logs</h2>
      <div class="readout" id="logCount"></div>
    </div>
    <div class="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Source</th>
            <th>Leg</th>
            <th>Side</th>
            <th>Side Source</th>
            <th>Amount</th>
            <th>Leverage</th>
            <th>Profit %</th>
            <th>Profit</th>
            <th>Balance</th>
            <th>Win/Loss</th>
          </tr>
        </thead>
        <tbody id="logBody"></tbody>
      </table>
    </div>
  </section>
</div>
<script>
const replayData = {data};
const timeline = replayData.timeline;
const trades = replayData.trades;
const initialBalance = replayData.initial_balance_usdc;
const chart = document.getElementById("balanceChart");
const ctx = chart.getContext("2d");
const slider = document.getElementById("timeSlider");
const playPause = document.getElementById("playPause");
const speedSelect = document.getElementById("speedSelect");
let currentIndex = 0;
let timer = null;

slider.max = String(Math.max(0, timeline.length - 1));
document.getElementById("periodLabel").textContent = `${{fmtDate(replayData.period.start)}} to ${{fmtDate(replayData.period.end)}}`;

function money(value) {{
  return new Intl.NumberFormat("en-US", {{ style: "currency", currency: "USD", maximumFractionDigits: 2 }}).format(value);
}}
function pct(value) {{
  const sign = value > 0 ? "+" : "";
  return `${{sign}}${{value.toFixed(2)}}%`;
}}
function fmtDate(value) {{
  return new Date(value).toISOString().replace("T", " ").slice(0, 16) + " UTC";
}}
function monthKey(value) {{
  return new Date(value).toISOString().slice(0, 7);
}}
function resizeCanvas() {{
  const rect = chart.getBoundingClientRect();
  const scale = window.devicePixelRatio || 1;
  chart.width = Math.max(640, Math.floor(rect.width * scale));
  chart.height = Math.floor(430 * scale);
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
}}
function visiblePoints() {{
  return timeline.slice(0, currentIndex + 1);
}}
function currentTradeRows() {{
  const visibleCount = timeline[currentIndex].visible_trade_count || 0;
  return trades.slice(0, visibleCount);
}}
function monthBaseBalance(rows, current) {{
  const key = monthKey(current.timestamp);
  const first = rows.find(row => monthKey(row.timestamp) === key);
  return first ? first.balance_usdc - first.profit_usdc : initialBalance;
}}
function updateMetrics() {{
  const current = timeline[currentIndex];
  const rows = currentTradeRows();
  const balance = current.balance_usdc;
  const sinceStart = balance - initialBalance;
  const sinceStartPct = (balance / initialBalance - 1) * 100;
  const monthBase = monthBaseBalance(rows, current);
  const sinceMonth = balance - monthBase;
  const sinceMonthPct = monthBase ? (balance / monthBase - 1) * 100 : 0;
  document.getElementById("balanceValue").textContent = money(balance);
  document.getElementById("tradeCountValue").textContent = `${{rows.length}} / ${{trades.length}} trades`;
  document.getElementById("sinceStartValue").textContent = money(sinceStart);
  document.getElementById("sinceStartPct").textContent = pct(sinceStartPct);
  document.getElementById("sinceMonthValue").textContent = money(sinceMonth);
  document.getElementById("sinceMonthPct").textContent = pct(sinceMonthPct);
  document.getElementById("drawdownValue").textContent = pct(current.drawdown_pct);
  document.getElementById("currentTimeValue").textContent = fmtDate(current.timestamp);
  document.getElementById("pointLabel").textContent = current.label;
  document.getElementById("axisReadout").textContent = `Y-axis money: ${{money(Math.min(...visiblePoints().map(p => p.balance_usdc)))}} to ${{money(Math.max(...visiblePoints().map(p => p.balance_usdc)))}}`;
}}
function drawChart() {{
  resizeCanvas();
  const width = chart.getBoundingClientRect().width;
  const height = 430;
  const padL = 76, padR = 22, padT = 22, padB = 42;
  const points = visiblePoints();
  const values = points.map(p => p.balance_usdc);
  let minY = Math.min(...values);
  let maxY = Math.max(...values);
  const padding = Math.max(50, (maxY - minY) * 0.08);
  minY -= padding;
  maxY += padding;
  if (maxY === minY) {{ maxY += 1; minY -= 1; }}
  const startMs = new Date(points[0].timestamp).getTime();
  const endMs = new Date(points[points.length - 1].timestamp).getTime();
  const span = Math.max(1, endMs - startMs);
  const x = p => padL + (width - padL - padR) * ((new Date(p.timestamp).getTime() - startMs) / span);
  const y = p => padT + (height - padT - padB) * (1 - ((p.balance_usdc - minY) / (maxY - minY)));
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#d9dee6";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#657182";
  ctx.font = "12px SFMono-Regular, monospace";
  for (let i = 0; i <= 4; i++) {{
    const yy = padT + (height - padT - padB) * (i / 4);
    const value = maxY - (maxY - minY) * (i / 4);
    ctx.beginPath();
    ctx.moveTo(padL, yy);
    ctx.lineTo(width - padR, yy);
    ctx.stroke();
    ctx.fillText(money(value), 8, yy + 4);
  }}
  ctx.strokeStyle = "#18202b";
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  ctx.moveTo(padL, padT);
  ctx.lineTo(padL, height - padB);
  ctx.lineTo(width - padR, height - padB);
  ctx.stroke();
  if (points.length > 1) {{
    ctx.strokeStyle = "#2457a7";
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    points.forEach((p, i) => {{
      if (i === 0) ctx.moveTo(x(p), y(p));
      else ctx.lineTo(x(p), y(p));
    }});
    ctx.stroke();
  }}
  const current = points[points.length - 1];
  ctx.fillStyle = current.balance_usdc >= initialBalance ? "#087f5b" : "#b42318";
  ctx.beginPath();
  ctx.arc(x(current), y(current), 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#657182";
  ctx.fillText(fmtDate(points[0].timestamp).slice(0, 10), padL, height - 14);
  ctx.textAlign = "right";
  ctx.fillText(fmtDate(current.timestamp).slice(0, 10), width - padR, height - 14);
  ctx.textAlign = "left";
}}
function renderLogs() {{
  const rows = currentTradeRows().slice().reverse();
  const body = document.getElementById("logBody");
  document.getElementById("logCount").textContent = `${{rows.length}} visible trades`;
  if (!rows.length) {{
    body.innerHTML = `<tr><td class="empty" colspan="11">No trades reached yet.</td></tr>`;
    return;
  }}
  body.innerHTML = rows.map(row => `
    <tr>
      <td>${{fmtDate(row.timestamp)}}</td>
      <td>${{escapeHtml(row.source)}}</td>
      <td>${{escapeHtml(row.leg)}}</td>
      <td>${{escapeHtml(row.side)}}</td>
      <td>${{escapeHtml(row.side_source)}}</td>
      <td>${{money(row.amount_usdc)}}</td>
      <td>${{row.leverage.toFixed(2)}}x</td>
      <td class="${{row.result}}">${{pct(row.profit_pct)}}</td>
      <td class="${{row.profit_usdc >= 0 ? "win" : "loss"}}">${{money(row.profit_usdc)}}</td>
      <td>${{money(row.balance_usdc)}}</td>
      <td class="${{row.result}}">${{row.result.toUpperCase()}}</td>
    </tr>
  `).join("");
}}
function escapeHtml(value) {{
  return String(value).replace(/[&<>"']/g, c => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[c]));
}}
function render() {{
  slider.value = String(currentIndex);
  updateMetrics();
  drawChart();
  renderLogs();
}}
function step() {{
  if (currentIndex >= timeline.length - 1) {{
    pause();
    return;
  }}
  currentIndex += 1;
  render();
}}
function play() {{
  pause();
  playPause.textContent = "Pause";
  const speed = Number(speedSelect.value);
  timer = window.setInterval(step, Math.max(20, 700 / speed));
}}
function pause() {{
  if (timer) window.clearInterval(timer);
  timer = null;
  playPause.textContent = "Play";
}}
playPause.addEventListener("click", () => timer ? pause() : play());
speedSelect.addEventListener("change", () => {{ if (timer) play(); }});
slider.addEventListener("input", event => {{
  currentIndex = Number(event.target.value);
  render();
}});
window.addEventListener("resize", drawChart);
render();
</script>
</body>
</html>
"""
