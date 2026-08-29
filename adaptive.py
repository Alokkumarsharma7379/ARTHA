"""
Watch what volume actually prints and re-plan when it disappoints.

On 40% of paths liquidity collapses partway through the session and you are not
told when, or whether. A schedule fixed at bar 0 cannot react; this one can.
"""

from artha import Bot


class Adaptive(Bot):
    def __init__(self, max_participation=0.08):
        self.cap = max_participation

    def on_bar(self, state):
        out = {}
        for sym in state.instruments:
            remaining = state.remaining[sym]

            # Last bar: whatever is left has to go through the closing auction.
            if state.bars_left <= 1:
                out[sym] = remaining
                continue

            want = remaining / state.bars_left

            # Cap against liquidity you have actually seen, not what you hoped
            # for. When volume dries up this pulls you back automatically.
            seen = state.volume_history[sym]
            if len(seen) >= 10:
                recent = sum(seen[-20:]) / len(seen[-20:])
                limit = self.cap * recent
                if abs(want) > limit:
                    want = limit if want > 0 else -limit

            out[sym] = want
        return out
