"""
Your bot. Rename it, change it, break it — this file is just a starting point.

Run it with:      artha run starter.py
Submit it with:   artha submit starter.py
"""

from artha import Bot


class MyBot(Bot):
    """Splits whatever is left evenly across the bars that remain.

    This is TWAP, and it is a genuinely respectable baseline — it beats a lot of
    cleverer things. It also ignores the volume curve completely, which is the
    obvious place to start improving it.
    """

    def on_bar(self, state):
        return {
            sym: state.remaining[sym] / max(state.bars_left, 1)
            for sym in state.instruments
        }
