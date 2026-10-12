"""Provider-reported turn spend capture (MODEL-05).

OpenRouter reports authoritative per-request USD inline as ``usage.cost``;
the Strands SDK drops the field when formatting metadata chunks. This
module recovers it at the seam: a capture mixin composed onto
``LiteLLMModel`` for openrouter-routed ids only, drained per turn by
``record_turn_metrics``. Display only — actuals change numbers shown,
never behavior.
"""

from __future__ import annotations

import copy
from typing import Any

from strands_code_cli import live_pricing

_wrapped_classes: dict[type, type] = {}
"""Composed capture subclass per SDK base (one base in production)."""


def _extract_cost(value: object) -> float | None:
    """Reported USD spend verbatim (None when absent or non-numeric)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


class ReportedCostMixin:
    """Capture inline ``usage.cost`` per model cycle into a side channel.

    Mixed onto the ``LiteLLMModel`` subclass composed by
    :func:`wrap_for_openrouter`; chunks pass through to ``super()``
    unmodified, so the agent loop never sees the capture.
    """

    _reported_costs: list[float | None]
    """Per-cycle captured costs; initialized by the wrap on promotion."""

    def format_chunk(self, event: dict[str, Any], **kwargs: Any) -> Any:
        """Record the metadata cost, then delegate verbatim to super().

        Capture never raises into the stream: an unrecorded cost
        degrades to the tokens-x-rate estimate path downstream.
        """
        try:
            if event.get("chunk_type") == "metadata":
                cost = _extract_cost(getattr(event.get("data"), "cost", None))
                self._reported_costs.append(cost)
        except Exception:
            pass
        return super().format_chunk(event, **kwargs)

    def take_reported_costs(self) -> list[float | None]:
        """Drain accumulated per-cycle costs (None marks an absent cycle)."""
        costs = self._reported_costs
        self._reported_costs = []
        return costs


def _composed_class(base: type) -> type:
    """Capture subclass for one SDK base, cached per base class."""
    cls = _wrapped_classes.get(base)
    if cls is None:

        class ReportedCostModel(ReportedCostMixin, base):
            """SDK model subclass capturing inline usage.cost per cycle."""

        cls = ReportedCostModel
        _wrapped_classes[base] = cls
    return cls


def sum_reported_costs(costs: list[float | None]) -> float | None:
    """Sum of present per-cycle costs, or None when no cycle reported.

    A turn is actual iff at least one cycle reported (any-rule); a
    present 0.0 stays a present zero, never None.
    """
    present = [cost for cost in costs if cost is not None]
    return sum(present) if present else None


def wrap_for_openrouter(model_id: str, resolved: Any) -> Any:
    """Promote a resolved model to capture inline usage.cost.

    Non-OpenRouter ids pass through untouched (the identical object).
    OpenRouter-routed ids promote the resolved instance in place, which
    preserves its configured effort/caching/client_args with zero SDK
    constructor knowledge. Without the provider extra the instance
    passes through unchanged (openrouter turns cannot run there).

    Args:
        model_id: Resolved model id string (wrap gate).
        resolved: Model instance from ``resolve_model``.

    Returns:
        The promoted instance, or ``resolved`` unchanged.
    """
    if not live_pricing.is_openrouter_id(model_id):
        return resolved
    try:
        from strands.models.litellm import LiteLLMModel
    except ImportError:
        return resolved
    resolved.__class__ = _composed_class(LiteLLMModel)
    # Costs gathered without per-turn drain discipline belong to no single
    # turn, so a re-wrap drops them once instead of misattributing them.
    resolved._reported_costs = []
    return resolved


def fresh_side_model(model: Any) -> Any:
    """Fresh cost side-channel for a side-agent build, else input unchanged.

    A side build replaying the parent's wrapped model must never share
    the parent's accumulated costs: shallow-copy the instance and empty
    the copy's cost list. Inputs without a cost side channel pass
    through untouched (the identical object).
    """
    if not callable(getattr(model, "take_reported_costs", None)):
        return model
    fresh = copy.copy(model)
    fresh._reported_costs = []
    return fresh
