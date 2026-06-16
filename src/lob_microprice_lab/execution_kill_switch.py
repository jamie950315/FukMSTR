from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OrderIntent:
    timestamp: str
    symbol: str
    side: str
    quantity: float
    intended_price: float
    dry_run: bool = True


@dataclass(frozen=True)
class KillSwitchDecision:
    allowed: bool
    reason: str
    event: dict[str, Any]


class KillSwitch:
    def __init__(self, *, active: bool) -> None:
        self.active = bool(active)

    def authorize_order(self, intent: OrderIntent) -> KillSwitchDecision:
        base_event = {
            "timestamp": intent.timestamp,
            "symbol": intent.symbol,
            "side": intent.side,
            "quantity": intent.quantity,
            "intended_price": intent.intended_price,
            "dry_run": intent.dry_run,
            "kill_switch_active": self.active,
            "would_place_order": False,
        }
        if self.active:
            event = {
                **base_event,
                "event_type": "kill_switch_tested",
                "allowed": False,
                "reason": "kill_switch_active",
            }
            return KillSwitchDecision(allowed=False, reason="kill_switch_active", event=event)
        if not intent.dry_run:
            event = {
                **base_event,
                "event_type": "live_order_blocked",
                "allowed": False,
                "reason": "live_order_not_supported",
            }
            return KillSwitchDecision(allowed=False, reason="live_order_not_supported", event=event)
        event = {
            **base_event,
            "event_type": "kill_switch_dry_run_authorized",
            "allowed": True,
            "reason": "dry_run_authorized",
        }
        return KillSwitchDecision(allowed=True, reason="dry_run_authorized", event=event)
