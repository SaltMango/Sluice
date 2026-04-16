"""
TuneEvaluator — per-torrent adaptive tuning decision engine.

Design principles
-----------------
* Returns (TuneLevel, reason: str) so callers can log and expose the
  decision via the debug API without any extra coupling.
* Hysteresis thresholds prevent oscillation:
    - Aggress UP   when utilization < THRESHOLD_UP   (0.50)
    - Step DOWN    when utilization > THRESHOLD_DOWN (0.65)
* Gradual stepping (±1 per evaluation) prevents jarring jumps.
* 10-second cooldown prevents thrashing.
* peer_speed_variance signals an unstable swarm → step down.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Tuple

from engine.models import TuneLevel

if TYPE_CHECKING:
    from engine.models import TorrentState

# ── Thresholds ─────────────────────────────────────────────────────────────────

COOLDOWN_SECS         = 10.0   # minimum gap between level changes
THRESHOLD_UP          = 0.50   # utilization below this → step up aggression
THRESHOLD_DOWN        = 0.65   # utilization above this (and calm) → step toward BALANCED
THRESHOLD_EXTREME     = 0.30   # extreme under-utilization trigger
EXTREME_PEER_MIN      = 50     # minimum peers required to engage EXTREME
STALL_LIMIT           = 3      # stalls above this → back off
VARIANCE_HIGH         = 50_000 # bytes/s — high peer speed variance = unstable swarm


class TuneEvaluator:
    """
    Stateless evaluator: all mutable state lives in TorrentState, so this
    object can be a single instance shared across all torrents.
    """

    def evaluate(
        self,
        state: TorrentState,
        metrics: dict,
    ) -> Tuple[TuneLevel, str]:
        """
        Evaluate the current metrics and return the recommended TuneLevel
        along with a human-readable reason string.

        Gradual stepping (±1) is applied so that the caller only needs to call
        apply_tune once per returned level and the transition stays smooth.
        """
        now = time.monotonic()
        current = state.tune_level

        # ── Cooldown guard ────────────────────────────────────────────────────
        if state.last_tune_change > 0.0 and (now - state.last_tune_change) < COOLDOWN_SECS:
            return current, "cooldown active"

        util      = float(metrics.get("utilization", 0.0))
        stalls    = int(metrics.get("stalls", 0))
        peers     = int(metrics.get("peers", 0))
        variance  = float(metrics.get("peer_speed_variance", 0.0))

        # ── Determine target level (direction) ───────────────────────────────

        # Safety: too many stalls → step toward SAFE
        if stalls > STALL_LIMIT:
            target  = TuneLevel.SAFE
            reason  = f"stall storm ({stalls} stalls) → reduce aggression"

        # Safety: high peer speed variance → unstable swarm, step down
        elif variance > VARIANCE_HIGH and current > TuneLevel.SAFE:
            target = TuneLevel(max(TuneLevel.SAFE, current - 1))
            reason = f"high peer variance ({variance:.0f} B/s σ) → unstable swarm, stepping down"

        # Extreme under-utilization with a deep peer pool
        elif util < THRESHOLD_EXTREME and peers >= EXTREME_PEER_MIN:
            target = TuneLevel.EXTREME
            reason = f"severe under-utilization ({util:.0%}) with {peers} peers → EXTREME"

        # Under-utilization: step up aggression
        elif util < THRESHOLD_UP:
            target = TuneLevel.EXTREME  # will be clamped to +1 below
            reason = f"low utilization ({util:.0%}) → increase aggression"

        # Good utilization and stable: step toward BALANCED
        elif util > THRESHOLD_DOWN and stalls == 0:
            target = TuneLevel.BALANCED
            reason = f"healthy utilization ({util:.0%}), no stalls → step toward BALANCED"

        # Steady state
        else:
            return current, "steady state"

        # ── Apply gradual step (±1 maximum per evaluation) ───────────────────
        if target > current:
            new_level = TuneLevel(min(current + 1, TuneLevel.EXTREME))
        elif target < current:
            new_level = TuneLevel(max(current - 1, TuneLevel.SAFE))
        else:
            new_level = current

        if new_level == current:
            return current, "already at target"

        return new_level, reason
