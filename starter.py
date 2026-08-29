"""Adaptive execution bot for the Artha competition.

The policy is a small, dependency-free model-predictive controller.  It fits the
known intraday shape, estimates the session's liquidity scale from prints,
maintains a probability that the common liquidity shock has happened, and
re-plans a volatility/crowding-adjusted schedule on every bar.  Orders are made
in common mandate-completion space so capped fills cannot silently leave the
legs far out of step.

Run locally with ``artha run starter.py`` and submit with
``artha submit starter.py``.
"""

import math
import statistics

from artha import Bot


class MyBot(Bot):
    """Bayesian regime-switching, receding-horizon execution policy."""

    # The engine's public mean-volume curve, represented compactly and
    # interpolated to the session length.  Keeping this in the submission makes
    # the bot deterministic and avoids prohibited file access.
    _PROFILE_KNOTS = (
        12.8, 6.7, 5.2, 4.3, 4.0, 3.5, 3.1, 3.0, 3.0, 2.8,
        2.6, 2.6, 2.8, 2.9, 2.6, 2.5, 2.7, 2.9, 2.9, 3.2,
        3.2, 3.5, 3.8, 5.7, 7.8,
    )

    def __init__(self):
        self.profile = None
        self.log_profile_mean = 0.0
        self.scale_log = None
        self.normal_scale_log = None
        self.shock_probability = 0.0
        self.weakness = 0.0
        self.last_observation_bar = -1

    def on_bar(self, state):
        self._ensure_profile(state.n_bars)
        self._observe(state)

        # Never rely on truthiness or sign arithmetic for a zero-mandate leg.
        active = [s for s in state.instruments if state.mandate[s] != 0.0]
        out = {s: 0.0 for s in state.instruments}
        if not active:
            return out

        # The uncapped auction is an expensive safety net, but exact completion
        # here prevents a penalty if earlier stochastic caps left a residue.
        if state.bars_left <= 1:
            return {s: self._safe(state.remaining[s], state.remaining[s])
                    for s in state.instruments}

        progress = {
            s: 1.0 - abs(state.remaining[s]) / max(abs(state.mandate[s]), 1e-12)
            for s in active
        }
        mean_progress = sum(progress.values()) / len(progress)
        base_fraction = self._next_progress_fraction(state, active)
        target_progress = min(1.0, mean_progress + (1.0 - mean_progress) * base_fraction)

        # A lagging leg receives a controlled catch-up adjustment; an advanced
        # leg slows down.  This directly attacks carry without allowing an
        # overfill or a wrong-side order.
        participation = self._operating_participation(state)
        for sym in active:
            mandate = state.mandate[sym]
            remaining = state.remaining[sym]
            catch_up_target = target_progress + 0.70 * (mean_progress - progress[sym])
            catch_up_target = min(1.0, max(progress[sym], catch_up_target))
            wanted = abs(mandate) * (catch_up_target - progress[sym])

            # Current-bar volume is unknowable.  Use a conservative forecast to
            # avoid routinely requesting fills that the engine will clip.
            forecast_volume = self._forecast_volume(sym, state.bar)
            wanted = min(wanted, participation * forecast_volume)

            # In the last few capped bars, completion dominates fine schedule
            # shaping.  Request an even residual (still bounded and legal).
            if state.bars_left <= 6:
                wanted = max(wanted, abs(remaining) / state.bars_left)

            signed = math.copysign(min(wanted, abs(remaining)), remaining)
            out[sym] = self._safe(signed, remaining)
        return out

    def _ensure_profile(self, n):
        if self.profile is not None and len(self.profile) == n:
            return
        knots = self._PROFILE_KNOTS
        raw = []
        for bar in range(n):
            x = bar * (len(knots) - 1) / max(n - 1, 1)
            lo = int(x)
            hi = min(lo + 1, len(knots) - 1)
            raw.append(knots[lo] + (knots[hi] - knots[lo]) * (x - lo))
        total = sum(raw)
        self.profile = [x / total for x in raw]
        self.log_profile_mean = sum(math.log(max(x, 1e-15)) for x in self.profile) / n

    def _observe(self, state):
        """Update common liquidity scale and shock probability exactly once."""
        observed_bar = state.bar - 1
        if observed_bar < 0 or observed_bar == self.last_observation_bar:
            return
        normalized_logs = []
        for sym in state.instruments:
            history = state.volume_history[sym]
            if history:
                volume = max(float(history[-1]), 1.0)
                normalized_logs.append(math.log(volume / max(self.profile[observed_bar], 1e-15)))
        if not normalized_logs:
            return

        observation = statistics.median(normalized_logs)
        if self.scale_log is None:
            self.scale_log = observation
            self.normal_scale_log = observation
        else:
            # Fast scale follows ordinary persistent volume variation.
            self.scale_log = 0.88 * self.scale_log + 0.12 * observation

            start = int(0.35 * state.n_bars)
            end = int(0.75 * state.n_bars)
            if observed_bar < start:
                # Establish a shock-free baseline before a shock is possible.
                self.normal_scale_log = 0.97 * self.normal_scale_log + 0.03 * observation
                self.shock_probability *= 0.85
            else:
                gap = self.normal_scale_log - observation
                evidence = max(0.0, min(1.0, (gap - 0.30) / 0.90))
                self.weakness = 0.72 * self.weakness + 0.28 * evidence

                # A persistent common 25-40% volume regime produces a log gap
                # near one.  The smooth posterior avoids reacting to one print.
                likelihood = 1.0 / (1.0 + math.exp(-9.0 * (self.weakness - 0.48)))
                if observed_bar <= end or self.shock_probability > 0.25:
                    self.shock_probability = max(
                        self.shock_probability * 0.96,
                        likelihood,
                    )
                # Do not teach the normal baseline the collapse after detection.
                if self.shock_probability < 0.20 and observed_bar <= end:
                    self.normal_scale_log = (
                        0.995 * self.normal_scale_log + 0.005 * observation
                    )
        self.last_observation_bar = observed_bar

    def _next_progress_fraction(self, state, active):
        """Return the optimized fraction of remaining inventory to trade now."""
        weights = []
        for bar in range(state.bar, state.n_bars):
            profile = self.profile[bar]
            log_shape = math.log(max(profile, 1e-15)) - self.log_profile_mean
            sigma = max(1.0, 4.9 * (1.0 + 0.25 * log_shape))
            if self.shock_probability > 0.0:
                sigma *= 1.0 + 0.35 * self.shock_probability

            # Solo temporary-impact optimum: q is proportional to V/sigma^2.
            regime_volume = profile * (1.0 - 0.67 * self.shock_probability)
            weight = regime_volume / (sigma * sigma)

            # Mild anti-crowding discount: profile followers crowd the liquid
            # peaks, TWAP supplies a flat background, and backloaders crowd the
            # final 15%.  It is deliberately modest because liquidity still wins.
            relative_profile = profile * state.n_bars
            crowd = 0.22 * math.sqrt(max(relative_profile, 0.0))
            if bar >= int(0.85 * state.n_bars):
                crowd += 0.18
            weight /= 1.0 + crowd

            # Exposure and deteriorating capacity justify earlier execution.
            distance = (bar - state.bar) / max(state.bars_left - 1, 1)
            urgency = 0.35 + 0.90 * self.shock_probability
            weight *= math.exp(-urgency * distance)
            weights.append(max(weight, 1e-15))

        fraction = weights[0] / sum(weights)

        # Conservative remaining-capacity guard.  If intended participation no
        # longer covers the mandate, raise the current fraction smoothly.
        scale = self._unshocked_scale()
        depth = 1.0 - 0.72 * self.shock_probability
        future_volume = scale * depth * sum(self.profile[state.bar:-1])
        operational = self._operating_participation(state)
        largest_remaining = max(abs(state.remaining[s]) for s in active)
        pressure = largest_remaining / max(operational * future_volume, 1.0)
        if pressure > 0.80:
            fraction *= 1.0 + min(3.0, (pressure - 0.80) * 2.5)

        # A deterministic deadline curve prevents a low forecast from creating
        # a catastrophic closing-auction residual.
        elapsed = state.bar / max(state.n_bars - 1, 1)
        if elapsed > 0.84:
            fraction = max(fraction, 1.15 / state.bars_left)
        if elapsed > 0.94:
            fraction = max(fraction, 1.60 / state.bars_left)
        return min(1.0, max(0.0, fraction))

    def _operating_participation(self, state):
        elapsed = state.bar / max(state.n_bars - 1, 1)
        rate = 0.085 + 0.055 * self.shock_probability
        if elapsed > 0.70:
            rate += 0.025
        if elapsed > 0.88:
            rate += 0.045
        return min(0.235, rate)

    def _forecast_volume(self, sym, bar):
        del sym  # The common estimate is intentionally robust across instruments.
        scale = self._unshocked_scale()
        mixture_depth = 1.0 - 0.67 * self.shock_probability
        # A small uncertainty haircut reduces unintended cap clipping.
        return max(1.0, 0.82 * scale * self.profile[bar] * mixture_depth)

    def _unshocked_scale(self):
        """Blend fast and protected baselines without counting a shock twice."""
        if self.scale_log is None:
            return 1_000_000.0
        normal = (self.normal_scale_log
                  if self.normal_scale_log is not None else self.scale_log)
        log_scale = ((1.0 - self.shock_probability) * self.scale_log
                     + self.shock_probability * normal)
        return math.exp(log_scale)

    @staticmethod
    def _safe(order, remaining):
        """Return a finite, correctly signed, non-overfilling order."""
        if remaining == 0.0 or not math.isfinite(order):
            return 0.0
        size = min(abs(float(order)), abs(float(remaining)))
        return math.copysign(size, remaining)
