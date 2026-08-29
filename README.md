# Artha — starter kit

Everything you need to write, test and submit a bot.

```
starter.py       the file to edit
RULES.md         every rule that decides your score
examples/        three bots, from naive to adaptive
```

## Setup

```bash
pip install artha-1.0.0-py3-none-any.whl     # the wheel from the brief page
```

That installs the engine, the six house bots you will be scored against, the
scorer, and 400 training sessions. Everything below runs offline.

## Your first score

```bash
artha run starter.py
```

Two hundred sessions, roughly fifteen seconds, and a full breakdown of where
your cost went. Iterate here. You have twenty submissions a day and there is no
reason to spend them finding out things you could have found out locally.

```bash
artha benchmark
```

Scores the six house bots the same way you are scored, so you can see what a
respectable number looks like before you go chasing one.

## Submitting

```bash
export ARTHA_TOKEN=your-team-token
artha submit starter.py
```

## Getting at the data

The 400 training sessions are yours to pull apart:

```python
from artha.paths import load

for session in load("train"):
    session.volume["ASHVAM"]     # 320 bars of traded volume
    session.base["ASHVAM"]       # 320 midpoints, before anyone trades
    session.mandate              # signed quantity per instrument
    session.shock_at             # bar index, or None
```

What you find in there is up to you. It is a real part of the problem.
