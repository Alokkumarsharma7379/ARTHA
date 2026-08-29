"""
Trade in proportion to how much volume you expect the bar to carry.

The intuition is right: put size where the liquidity is. Whether proportional to
volume is the *best* answer is worth thinking about — impact grows with the
square root of participation, not linearly, and that changes the arithmetic.
"""

from artha import Bot


class VolumeFollower(Bot):
    def __init__(self):
        self.shape = None

    def on_bar(self, state):
        if self.shape is None or len(self.shape) != state.n_bars:
            self.shape = self._forecast(state.n_bars)

        ahead = sum(self.shape[state.bar:])
        weight = self.shape[state.bar] / ahead if ahead > 0 else 1.0
        return {s: state.remaining[s] * weight for s in state.instruments}

    def _forecast(self, n):
        """A flat forecast, deliberately. Replacing this with something fitted to
        the training paths is most of the work."""
        return [1.0 / n] * n
