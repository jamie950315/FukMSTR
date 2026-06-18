from __future__ import annotations

import json
import math
import os
import base64
import hmac
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd

from .data_schema import parse_timestamp_series


def request_kill_switch(run_dir: str | Path, *, reason: str = "manual_dashboard") -> Path:
    out = Path(run_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "active": True,
        "reason": reason,
        "requested_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "scope": "paper_positions_only",
    }
    path = out / "kill_switch.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def clear_kill_switch(run_dir: str | Path) -> Path:
    out = Path(run_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "active": False,
        "reason": "operator_cleared",
        "requested_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "scope": "paper_positions_only",
    }
    path = out / "kill_switch.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def build_dashboard_state(
    *,
    run_dir: str | Path,
    book_csv: str | Path | None = None,
    symbol: str = "BTCUSDC",
    limit: int = 80,
) -> dict[str, Any]:
    out = Path(run_dir)
    summary = _read_json(out / "summary.json")
    balance = _read_csv_records(out / "balance.csv", limit=limit)
    trades = _read_csv_records(out / "trades.csv", limit=limit)
    rejected = _read_csv_records(out / "rejected_signals.csv", limit=limit)
    positions = _read_csv_records(out / "positions.csv", limit=limit)
    orders = _read_csv_records(out / "order_events.csv", limit=limit)
    decisions = _read_csv_records(out / "decisions.csv", limit=limit)
    market = _market_state(symbol=symbol, balance=balance, book_csv=book_csv)
    return {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "run_dir": str(out),
        "mode": "paper_trading_only",
        "market": market,
        "summary": summary,
        "balance": balance,
        "positions": positions,
        "orders": orders,
        "decisions": decisions,
        "trades": trades,
        "rejected_signals": rejected,
        "kill_switch": _kill_switch_state(out),
        "safety": {
            "live_orders_enabled": False,
            "api_key_required": False,
            "scope": "Public market data plus local paper-trading state. No exchange orders are placed.",
        },
    }


def serve_paper_dashboard(
    *,
    run_dir: str | Path,
    book_csv: str | Path | None = None,
    symbol: str = "BTCUSDC",
    host: str = "127.0.0.1",
    port: int = 8765,
    admin_user: str | None = None,
    admin_password: str | None = None,
    admin_password_sha256: str | None = None,
) -> None:
    server = make_dashboard_server(
        run_dir=run_dir,
        book_csv=book_csv,
        symbol=symbol,
        host=host,
        port=port,
        admin_user=admin_user,
        admin_password=admin_password,
        admin_password_sha256=admin_password_sha256,
    )
    print(f"Paper dashboard: http://{host}:{int(port)}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def make_dashboard_server(
    *,
    run_dir: str | Path,
    book_csv: str | Path | None = None,
    symbol: str = "BTCUSDC",
    host: str = "127.0.0.1",
    port: int = 8765,
    admin_user: str | None = None,
    admin_password: str | None = None,
    admin_password_sha256: str | None = None,
) -> ThreadingHTTPServer:
    run_path = Path(run_dir)
    book_path = None if book_csv is None else Path(book_csv)
    expected_user = admin_user if admin_user is not None else os.environ.get("PAPER_DASHBOARD_ADMIN_USER", "admin")
    expected_password = admin_password if admin_password is not None else os.environ.get("PAPER_DASHBOARD_ADMIN_PASSWORD", "")
    expected_password_sha256 = (
        admin_password_sha256
        if admin_password_sha256 is not None
        else os.environ.get("PAPER_DASHBOARD_ADMIN_PASSWORD_SHA256", "")
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_text(_dashboard_html(symbol=symbol, admin=False), content_type="text/html; charset=utf-8")
                return
            if parsed.path == "/admin":
                if not self._is_admin_authorized():
                    self._send_unauthorized()
                    return
                self._send_text(_dashboard_html(symbol=symbol, admin=True), content_type="text/html; charset=utf-8")
                return
            if parsed.path == "/api/state":
                query = parse_qs(parsed.query)
                row_limit = int(query.get("limit", ["80"])[0])
                state = build_dashboard_state(run_dir=run_path, book_csv=book_path, symbol=symbol, limit=row_limit)
                self._send_json(state)
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/kill-switch":
                if not self._is_admin_authorized():
                    self._send_unauthorized()
                    return
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {}
                reason = str(payload.get("reason") or "manual_dashboard")
                request_kill_switch(run_path, reason=reason)
                self._send_json({"ok": True, "kill_switch": _kill_switch_state(run_path)})
                return
            if parsed.path == "/api/clear-kill-switch":
                if not self._is_admin_authorized():
                    self._send_unauthorized()
                    return
                clear_kill_switch(run_path)
                self._send_json({"ok": True, "kill_switch": _kill_switch_state(run_path)})
                return
            self.send_error(404)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, default=_json_default).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, text: str, *, content_type: str) -> None:
            body = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_unauthorized(self) -> None:
            body = b"admin authentication required"
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="paper-dashboard-admin"')
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _is_admin_authorized(self) -> bool:
            if not expected_user or not (expected_password or expected_password_sha256):
                return False
            header = self.headers.get("Authorization", "")
            if not header.startswith("Basic "):
                return False
            try:
                decoded = base64.b64decode(header.removeprefix("Basic ").strip()).decode("utf-8")
            except Exception:
                return False
            user, sep, password = decoded.partition(":")
            if not sep:
                return False
            if not hmac.compare_digest(user, expected_user):
                return False
            if expected_password and hmac.compare_digest(password, expected_password):
                return True
            if expected_password_sha256:
                supplied_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
                return hmac.compare_digest(supplied_hash, expected_password_sha256)
            return False

    return ThreadingHTTPServer((host, int(port)), Handler)


def _market_state(*, symbol: str, balance: list[dict[str, Any]], book_csv: str | Path | None) -> dict[str, Any]:
    latest_balance = balance[-1] if balance else {}
    market = {
        "symbol": str(latest_balance.get("symbol") or symbol).upper(),
        "timestamp": latest_balance.get("timestamp"),
        "last_price": latest_balance.get("price"),
        "mid_price": latest_balance.get("price"),
        "bid": None,
        "ask": None,
        "spread": None,
        "spread_bps": None,
        "bid_size": None,
        "ask_size": None,
        "top_imbalance": None,
        "source": latest_balance.get("source") or "paper_balance",
    }
    if book_csv is None or not Path(book_csv).exists():
        return market
    frame = pd.read_csv(book_csv)
    required = {"timestamp", "bid_px_1", "bid_sz_1", "ask_px_1", "ask_sz_1"}
    if not required.issubset(frame.columns) or frame.empty:
        return market
    frame["timestamp"] = parse_timestamp_series(frame["timestamp"])
    for col in ["bid_px_1", "bid_sz_1", "ask_px_1", "ask_sz_1"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=list(required)).tail(1)
    if frame.empty:
        return market
    row = frame.iloc[-1]
    bid = float(row["bid_px_1"])
    ask = float(row["ask_px_1"])
    bid_size = float(row["bid_sz_1"])
    ask_size = float(row["ask_sz_1"])
    mid = (bid + ask) / 2.0
    spread = ask - bid
    market.update(
        {
            "timestamp": row["timestamp"].isoformat(),
            "last_price": mid,
            "mid_price": mid,
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "spread_bps": (spread / mid * 10_000.0) if mid else None,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "top_imbalance": ((bid_size - ask_size) / (bid_size + ask_size)) if (bid_size + ask_size) else None,
            "source": "book-csv",
        }
    )
    return market


def _read_csv_records(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return []
    if frame.empty:
        return []
    return [_clean_record(row) for row in frame.tail(int(limit)).to_dict(orient="records")]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _kill_switch_state(out: Path) -> dict[str, Any]:
    payload = _read_json(out / "kill_switch.json")
    if not payload:
        return {"active": False, "scope": "paper_positions_only"}
    payload["active"] = bool(payload.get("active"))
    payload.setdefault("scope", "paper_positions_only")
    return payload


def _clean_record(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_default(value) for key, value in row.items()}


def _json_default(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _dashboard_html(*, symbol: str, admin: bool) -> str:
    mode_label = "Admin Panel" if admin else "Public View"
    control_html = (
        '<button class="danger" id="kill">Kill Switch: Close Paper Positions</button>'
        '<button id="clearKill">Clear Kill Switch</button>'
        if admin
        else '<a class="admin-link" href="/admin">Admin</a>'
    )
    admin_script = (
        """
document.getElementById('kill').addEventListener('click', async () => {
  await fetch('/api/kill-switch', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({reason:'manual_dashboard'}) });
  await refresh();
});
document.getElementById('clearKill').addEventListener('click', async () => {
  await fetch('/api/clear-kill-switch', { method:'POST' });
  await refresh();
});
"""
        if admin
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{symbol.upper()} Paper Dashboard - {mode_label}</title>
<style>
:root {{ color-scheme: dark; --bg:#0b0f14; --panel:#121820; --line:#263241; --text:#e6edf3; --muted:#8796a8; --buy:#0ecb81; --sell:#f6465d; --warn:#f0b90b; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Arial, sans-serif; background:var(--bg); color:var(--text); }}
header {{ display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 18px; border-bottom:1px solid var(--line); background:#10161d; }}
h1 {{ margin:0; font-size:18px; letter-spacing:0; }}
button {{ border:1px solid var(--line); background:#18212b; color:var(--text); padding:9px 12px; border-radius:6px; cursor:pointer; }}
button.danger {{ background:#3a1319; border-color:#80313b; color:#ffd7dc; }}
.admin-link {{ color:var(--text); text-decoration:none; border:1px solid var(--line); border-radius:6px; padding:9px 12px; background:#18212b; }}
main {{ display:grid; grid-template-columns:320px minmax(420px,1fr) 380px; gap:10px; padding:10px; min-height:calc(100vh - 58px); }}
section {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; min-width:0; overflow:hidden; }}
.section-title {{ display:flex; justify-content:space-between; align-items:center; padding:10px 12px; border-bottom:1px solid var(--line); color:var(--muted); font-size:12px; text-transform:uppercase; }}
.content {{ padding:12px; }}
.price {{ font-size:30px; font-weight:700; }}
.buy {{ color:var(--buy); }}
.sell {{ color:var(--sell); }}
.warn {{ color:var(--warn); }}
.grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }}
.metric {{ border:1px solid var(--line); border-radius:6px; padding:8px; min-height:58px; }}
.label {{ color:var(--muted); font-size:11px; margin-bottom:4px; }}
.value {{ font-size:16px; overflow-wrap:anywhere; }}
table {{ width:100%; border-collapse:collapse; font-size:12px; }}
th, td {{ padding:7px 8px; border-bottom:1px solid var(--line); text-align:right; white-space:nowrap; }}
th:first-child, td:first-child {{ text-align:left; }}
th {{ color:var(--muted); font-weight:400; }}
.stack {{ display:grid; gap:10px; }}
.chart {{ width:100%; height:260px; }}
.muted {{ color:var(--muted); }}
.status {{ font-size:12px; color:var(--muted); }}
@media (max-width:1100px) {{ main {{ grid-template-columns:1fr; }} .chart {{ height:220px; }} }}
</style>
</head>
<body>
<header>
  <h1>{symbol.upper()} Paper Trading Dashboard <span class="muted">/ {mode_label}</span></h1>
  <div class="status" id="status">loading</div>
  <div>{control_html}</div>
</header>
<main>
  <div class="stack">
    <section><div class="section-title"><span>Market</span><span id="source"></span></div><div class="content">
      <div class="price" id="price">--</div>
      <div class="muted" id="spread">spread --</div>
      <div class="grid" style="margin-top:12px">
        <div class="metric"><div class="label">Bid</div><div class="value buy" id="bid">--</div></div>
        <div class="metric"><div class="label">Ask</div><div class="value sell" id="ask">--</div></div>
        <div class="metric"><div class="label">Top Imbalance</div><div class="value" id="imbalance">--</div></div>
        <div class="metric"><div class="label">Kill Switch</div><div class="value" id="killState">--</div></div>
      </div>
    </div></section>
    <section><div class="section-title"><span>Account</span></div><div class="content grid" id="account"></div></section>
  </div>
  <div class="stack">
    <section><div class="section-title"><span>Equity</span></div><div class="content"><canvas class="chart" id="equity"></canvas></div></section>
    <section><div class="section-title"><span>Positions</span></div><div class="content"><div id="positions"></div></div></section>
    <section><div class="section-title"><span>Current Paper Orders</span></div><div class="content"><div id="orders"></div></div></section>
  </div>
  <div class="stack">
    <section><div class="section-title"><span>Decision Reasons</span></div><div class="content"><div id="decisions"></div></div></section>
    <section><div class="section-title"><span>Recent Trades</span></div><div class="content"><div id="trades"></div></div></section>
    <section><div class="section-title"><span>Rejected Signals</span></div><div class="content"><div id="rejected"></div></div></section>
  </div>
</main>
<script>
const fmt = new Intl.NumberFormat(undefined, {{ maximumFractionDigits: 6 }});
const money = new Intl.NumberFormat(undefined, {{ maximumFractionDigits: 2 }});
const cell = v => v === null || v === undefined || v === '' ? '--' : String(v);
const num = v => v === null || v === undefined || v === '' ? '--' : fmt.format(Number(v));
const usd = v => v === null || v === undefined || v === '' ? '--' : money.format(Number(v));
function table(rows, keys) {{
  if (!rows || !rows.length) return '<div class="muted">No rows.</div>';
  const head = '<tr>' + keys.map(k => `<th>${{k}}</th>`).join('') + '</tr>';
  const body = rows.slice(-16).reverse().map(r => '<tr>' + keys.map(k => `<td>${{cell(r[k])}}</td>`).join('') + '</tr>').join('');
  return `<table>${{head}}${{body}}</table>`;
}}
function metric(label, value) {{ return `<div class="metric"><div class="label">${{label}}</div><div class="value">${{value}}</div></div>`; }}
function drawEquity(rows) {{
  const c = document.getElementById('equity');
  const ctx = c.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  c.width = c.clientWidth * dpr; c.height = c.clientHeight * dpr; ctx.scale(dpr, dpr);
  ctx.clearRect(0,0,c.clientWidth,c.clientHeight);
  const pts = (rows || []).map(r => Number(r.equity_usdc)).filter(Number.isFinite);
  if (pts.length < 2) return;
  const min = Math.min(...pts), max = Math.max(...pts), span = max - min || 1;
  ctx.strokeStyle = '#0ecb81'; ctx.lineWidth = 2; ctx.beginPath();
  pts.forEach((v,i) => {{
    const x = i / (pts.length - 1) * c.clientWidth;
    const y = c.clientHeight - ((v - min) / span * (c.clientHeight - 18) + 9);
    if (i === 0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
  }});
  ctx.stroke();
}}
async function refresh() {{
  const res = await fetch('/api/state?limit=120', {{ cache:'no-store' }});
  const s = await res.json();
  document.getElementById('status').textContent = `updated ${{new Date(s.generated_at).toLocaleTimeString()}}`;
  document.getElementById('source').textContent = s.market.source || '';
  document.getElementById('price').textContent = usd(s.market.mid_price || s.market.last_price);
  document.getElementById('bid').textContent = num(s.market.bid);
  document.getElementById('ask').textContent = num(s.market.ask);
  document.getElementById('spread').textContent = `spread ${{num(s.market.spread)}} / ${{num(s.market.spread_bps)}} bps`;
  document.getElementById('imbalance').textContent = num(s.market.top_imbalance);
  document.getElementById('killState').innerHTML = s.kill_switch.active ? '<span class="warn">ACTIVE</span>' : 'off';
  const last = (s.balance || []).slice(-1)[0] || {{}};
  document.getElementById('account').innerHTML = [
    metric('Equity USDC', usd(last.equity_usdc || s.summary.final_equity_usdc)),
    metric('Balance USDC', usd(last.balance_usdc || s.summary.final_balance_usdc)),
    metric('Drawdown %', num(last.drawdown_pct)),
    metric('Open Positions', cell(last.open_positions || s.summary.open_positions || 0))
  ].join('');
  drawEquity(s.balance || []);
  document.getElementById('positions').innerHTML = table(s.positions, ['signal_id','symbol','side','mark_price','entry_price','unrealized_pnl_usdc','time_to_exit_minutes']);
  document.getElementById('orders').innerHTML = table(s.orders, ['timestamp','signal_id','status','side','price','reason']);
  document.getElementById('decisions').innerHTML = table(s.decisions, ['timestamp','signal_id','decision','reason','result']);
  document.getElementById('trades').innerHTML = table(s.trades, ['timestamp','event_type','signal_id','side','price','net_pnl_usdc','close_reason']);
  document.getElementById('rejected').innerHTML = table(s.rejected_signals, ['timestamp','signal_id','reason','side','source']);
}}
{admin_script}
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>"""
