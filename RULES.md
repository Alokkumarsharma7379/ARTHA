# Artha — Rules

Everything that decides your score. Nothing here is negotiable at scoring time,
so read it once properly.

---

## 1. The mandate

At bar 0 your bot is handed a compulsory order across up to three instruments:

```
ASHVAM   +28,040     buy
BRIHAT   -28,034     sell
CHAKRA        0      not mandated on this path
```

Positive means buy, negative means sell. A leg with a mandate of **zero is
quoted but not yours to trade** — you can see its price and volume, and any
order you place on it is rejected.

- You have **320 bars**. Bars are indexed `0…319`. There are no timestamps.
- You cannot decline the mandate, trade anything outside it, or finish short.
- **Two legs on roughly two-thirds of paths, three on the rest.** Read the
  mandate; do not assume its shape.
- Legs are sized to **equal notional at arrival**, so executing them
  proportionally carries no net exposure and racing one ahead of another does.
- Mandate size varies per path, typically **3–8% of that session's total
  volume**. It is the same mandate for every team on a given path, so scores are
  directly comparable; roughly half the field is given the opposite side.

## 2. What you can see

Your bot's `on_bar(state)` receives, and only receives:

| Field | Meaning |
|---|---|
| `state.bar` | current bar index, `0…319` |
| `state.n_bars` | always 320 |
| `state.bars_left` | `n_bars - bar` |
| `state.instruments` | the three instrument names |
| `state.mandate` | signed target per instrument, fixed all session |
| `state.remaining` | signed quantity still to execute |
| `state.mid` | current midpoint per instrument |
| `state.last_volume` | volume that printed in bar `t-1` |
| `state.volume_history` | every volume you have seen, up to `t-1` |
| `state.mid_history` | every midpoint you have seen, up to `t` |

**There is nothing about the future in here.** No base path, no realised volume
for the current bar, no flag telling you whether this path has a liquidity
shock. The current bar's volume is not knowable when you size into it — that is
the forecasting problem.

## 3. What you return

A dict of signed quantities. Anything you do not name trades zero.

```python
return {"ASHVAM": 120.0, "BRIHAT": -90.0}
```

An order is **rejected**, logged, and treated as zero if it:

- moves away from your mandate (wrong side), or
- would take you past your mandate (overfill), or
- is not a finite number.

**Six rejections disqualifies the run.** A bot that raises an exception has that
bar treated as a no-trade and counted as one rejection.

## 4. Limits enforced by the engine

**Participation cap — 25% of any bar's volume.** This is clipped inside the
engine before impact is computed, not checked afterwards. Ordering more is not
an error; you simply get 25%.

**The closing auction is exempt.** Bar 319 has no cap, because otherwise a
residual could be impossible to clear. It is not free: clearing 8% of session
volume into a bar holding 0.3% of it is roughly 2,600% participation, which the
square-root term prices at around 275 bps. Do not plan to use it.

**2 seconds per bar.** A bar that times out submits nothing and counts as a rejection.

## 5. Market impact

Two effects, on two different clocks.

**Temporary — per bar.** The concession you pay on this bar's own fill, against
this bar's own liquidity:

```
h_t = 11.0 · sqrt(u_t) · σ_bar          where  u_t = gross flow / bar volume
```

At half a bar's volume this is roughly **38 bps**. It is driven by the bar's
**gross** flow, not yours alone — a bar's liquidity is a shared resource and
consuming it costs regardless of direction. Five agents taking 10% each pay the
concession for 50%.

**Permanent — per session.** The midpoint displacement your order causes, in
proportion to its size against the whole session's volume, accrued as it prints:

```
g_t = 4.0 · (net flow_t / session volume) · σ_session
```

An order worth 10% of session volume displaces the midpoint about **35 bps** in
total. This one runs off **net** flow: only imbalance moves a price persistently.
If a buyer and a seller both print, they traded with each other.

## 6. The liquidity shock

On **40% of paths**, at a bar somewhere between 35% and 75% of the session, mean
volume falls to **25–40%** of its profile for the remainder and volatility rises.

You are told it exists and how often. **You are never told whether this path is
one of them.** A bot that always assumes a collapse over-trades the open on 60%
of paths; a bot that never assumes one is destroyed on 40%. Detecting it and
re-planning is the only correct answer.

## 7. Scoring

Your implementation shortfall is decomposed against three counterfactual price
paths the engine runs simultaneously: one where **nobody** trades, one where
**only you** trade, one where **everybody** does.

```
timing   = C_frictionless − C_arrival      drift while you were exposed
impact   = C_solo         − C_frictionless your own footprint
crowding = C_actual       − C_solo         the field's footprint on you
```

Those three sum exactly to total shortfall. Two further terms charge risk
directly, with no path noise in them:

```
exposure = λ · σ_session · sqrt( mean_t( (remaining_t / Q)² ) )
carry    = λ · σ_session · sqrt( mean_t( (x_A,t·P_A − x_B,t·P_B)² ) ) / notional
```

`exposure` charges the quantity still outstanding. `carry` charges the legs
being out of step — finishing one before another leaves an unhedged directional
position the mandate never asked you to hold.

### The score

```
SCORE = impact + crowding + exposure + carry + penalty      (bps, lower wins)
```

Every term is already basis points of the same notional, so they are summed, not
weighted. **λ = 0.35.**

### Timing is reported but never scored

Its mean is zero for every schedule, because drift has no expectation. Its
standard deviation is around 56 bps against impact's 0.7. Ranking on it would be
ranking you on luck, so it is shown to you and excluded from the score.

### Unfilled mandate

Any residual at bar 319 is force-filled at the closing midpoint, charged its own
impact, **plus a flat 200 bps penalty on the residual notional**. Finishing
always dominates.

## 8. Phases

| Phase | Paths | Field | Board |
|---|---|---|---|
| **Practice** | 400, shipped to you | — | none |
| **Public** | 120, never released | six house bots | live |
| **Private** | 200, never released | **every team, simultaneously** | at the close |

The three pools are disjoint **at the source bar**, not merely at the path. A
schedule tuned to the public paths carries no advantage into the private ones,
because there is no shared data for it to carry through.

In the finale your bot executes alongside the rest of the field on every path, in
cohorts that reshuffle each time, and impact is charged on combined
participation. If the field piles into bar 200, the field pays for bar 200.

## 9. Submissions

- **20 per day**, **10 minutes apart**. The day resets at midnight Asia/Kolkata.
- Uploads rejected at validation — a syntax error, no `Bot` subclass, a banned
  import — cost **neither quota nor cooldown**.
### Your finale entry

You choose it. In **My runs**, any submission that scored has a **Use for finale**
button, and exactly one submission carries the "finale entry" mark at a time.

**That entry is the only code scored on the private set.** Nothing else you
submitted is run, however well it did on the public board.

- Change it as often as you like while submissions are open. It locks when they close.
- If you never choose, your **best public score** is used. Doing nothing gives a
  sensible result, but choose explicitly if you want something else.
- Your position on the public leaderboard is separate: that is always your best
  public score, regardless of which entry you nominated.

### Allowed imports

`artha`, `numpy`, `math`, `statistics`, `random`, `collections`, `itertools`,
`functools`, `heapq`, `bisect`, `dataclasses`, `typing`, `enum`, `abc`, `copy`,
`json`, `re`.

Everything else is rejected, along with `eval`, `exec`, `compile`, `open`,
`__import__`, `globals`, `locals`, `getattr`, `setattr`, and any dunder attribute
access. Submissions are capped at 100 KB and run with no network access.

## 10. Conduct

Your bot competes; it does not interfere. Attempting to read another team's
state, escape the sandbox, or degrade the evaluation for others is
disqualification, not a clever exploit.

Submitting deliberately oversized orders to inflate rivals' crowding cost is
covered by the participation cap and will not work — but the intent is still
disqualifying.
