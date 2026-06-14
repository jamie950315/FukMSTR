from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class FeatureConfig:
    depth_levels: list[int] = field(default_factory=lambda: [1, 3, 5, 10])
    trade_windows_sec: list[float] = field(default_factory=lambda: [1.0, 5.0, 10.0])
    add_lagged_features: bool = True
    ewm_span: int = 20
    add_order_flow_features: bool = True
    add_depth_shape_features: bool = True
    add_multi_level_microprice: bool = True
    temporal_windows_rows: list[int] = field(default_factory=lambda: [2, 5, 10, 20])


@dataclass
class LabelConfig:
    horizon_sec: float = 1.0
    threshold_bps: float = 0.5


@dataclass
class SplitConfig:
    train_ratio: float = 0.70


@dataclass
class ModelConfig:
    type: str = "logistic"
    random_state: int = 42
    max_iter: int = 1000
    quantile_clip: tuple[float, float] = (0.01, 0.99)


@dataclass
class BacktestConfig:
    cost_bps: float = 1.5
    signal_edge_threshold: float = 0.10


@dataclass
class IOConfig:
    timestamp_col: str = "timestamp"


@dataclass
class AppConfig:
    features: FeatureConfig = field(default_factory=FeatureConfig)
    labels: LabelConfig = field(default_factory=LabelConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    io: IOConfig = field(default_factory=IOConfig)

    @classmethod
    def from_yaml(cls, path: str | Path | None) -> "AppConfig":
        cfg = cls()
        if path is None:
            return cfg
        with Path(path).open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppConfig":
        return cls(
            features=_feature_config(raw.get("features", {})),
            labels=LabelConfig(**raw.get("labels", {})),
            split=SplitConfig(**raw.get("split", {})),
            model=_model_config(raw.get("model", {})),
            backtest=BacktestConfig(**raw.get("backtest", {})),
            io=IOConfig(**raw.get("io", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        q = out["model"].get("quantile_clip")
        if isinstance(q, tuple):
            out["model"]["quantile_clip"] = list(q)
        return out

    def to_yaml(self, path: str | Path) -> None:
        with Path(path).open("w", encoding="utf-8") as f:
            yaml.safe_dump(self.to_dict(), f, sort_keys=False)


def _model_config(raw: dict[str, Any]) -> ModelConfig:
    raw = dict(raw)
    if "quantile_clip" in raw and isinstance(raw["quantile_clip"], list):
        raw["quantile_clip"] = tuple(raw["quantile_clip"])
    return ModelConfig(**raw)


def _feature_config(raw: dict[str, Any]) -> FeatureConfig:
    raw = dict(raw)
    # Old config files should keep working after new feature switches were added.
    return FeatureConfig(**raw)
