"""player_tweaks.py -- the player's own adjustments: summon-rate multipliers and a lapis gain multiplier.

How a summon works here (see `player_state.State.roll_gacha` and `expand_pool`):

  * Every banner has a pool. Most pools are written as rarity TIERS, for example
    `5: 1%, 4: 19%, 3: 80%`, optionally with `featured` units that take `featured_share` of their tier
    (the "rate up" units). `expand_pool` turns that into one row per unit with its own rate.
  * Each draw picks one row at random, weighted by those rates. Weights are relative: they are divided
    by their total, so they need not add up to 1.
  * Guarantees (an 11-pull's guaranteed 5-star slot, a ticket's rarity floor) then replace the lowest
    draws, picking from the eligible rows by the same weights.

This module only reweights rows. It never changes guarantees, costs or which units are in a pool, so a
setting can't make a banner unwinnable. The Drop Rates screen reads the same `expand_pool`, so it shows
the odds the tweaks produce.

The settings file is `tweaks.json` next to the save folder (on Android `files/exvius/tweaks.json`,
written by the Exvius Settings screen). `EXVIUS_TWEAKS` overrides the path. A missing or unreadable file
means the game's own numbers. Example:

    {
      "rarity_multiplier": {"5": 3, "7": 3},
      "featured_multiplier": 2,
      "lapis_multiplier": 3,
      "lapis_summon_cost": "half"
    }

`rarity_multiplier` scales every row of that base rarity (7 = Neo Vision). `featured_multiplier` scales
a banner's rate-up units on top of that. A multiplier of 3 on a 1% tier makes it about 3% of the
weight; the exact chance is shown on the Drop Rates screen after the weights are normalised.

`lapis_multiplier` scales every lapis GAIN (mission challenges, rank-up bonus, quests, mail, login
rewards, exchanges) at the one place lapis is credited, `State.add_currency`. Spending is unchanged.
Result screens still print the original amount; the top bar shows the real balance.

`lapis_summon_cost` changes what a lapis-priced summon costs: "half" (rounded down, at least 1) or "1"
(every lapis summon, single or multi, costs 1 lapis). Both the price the summon screen shows and the
amount charged go through `summon_cost`, so they always agree. Ticket, friend point and item costs are
unchanged.
"""
from __future__ import annotations

import json
import os

import data_paths

MAX_MULTIPLIER = 1000.0
_cache: dict = {"key": None, "value": {}}


def settings_path() -> str:
    return os.environ.get("EXVIUS_TWEAKS") or os.path.join(os.path.dirname(data_paths.STATE_DIR),
                                                            "tweaks.json")


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number < 0:          # NaN or negative: ignore the entry
        return None
    return min(number, MAX_MULTIPLIER)


def settings() -> dict:
    """The parsed settings, re-read whenever the file changes, so a new choice applies to the next pull."""
    path = settings_path()
    try:
        stat = os.stat(path)
        key = (path, stat.st_mtime_ns, stat.st_size)
    except OSError:
        _cache.update(key=None, value={})
        return {}
    if _cache["key"] == key:
        return _cache["value"]
    value: dict = {}
    try:
        with open(path, encoding="utf-8") as source:
            raw = json.load(source)
        rarity = {}
        for name, factor in (raw.get("rarity_multiplier") or {}).items():
            number = _number(factor)
            if str(name).isdigit() and number is not None:
                rarity[int(name)] = number
        if rarity:
            value["rarity_multiplier"] = rarity
        featured = _number(raw.get("featured_multiplier"))
        if featured is not None and featured != 1:
            value["featured_multiplier"] = featured
        cost = str(raw.get("lapis_summon_cost") or "").strip().lower()
        if cost in ("half", "1"):
            value["lapis_summon_cost"] = cost
        lapis = _number(raw.get("lapis_multiplier"))
        if lapis is not None and lapis != 1:
            value["lapis_multiplier"] = lapis
    except (OSError, ValueError, AttributeError) as error:
        print(f"    player tweaks ignored ({type(error).__name__}): {path}", flush=True)
        value = {}
    _cache.update(key=key, value=value)
    return value


def active() -> bool:
    """Whether any summon multiplier is set."""
    current = settings()
    return bool(current.get("rarity_multiplier") or current.get("featured_multiplier"))


def summon_cost(kind, amount: int) -> int:
    """A summon price after the player's setting. Only lapis prices (cost kind "lapis" or 50) change."""
    amount = int(amount or 0)
    mode = settings().get("lapis_summon_cost")
    if not mode or amount <= 0 or str(kind) not in ("lapis", "50"):
        return amount
    return 1 if mode == "1" else max(1, amount // 2)


def lapis_gain(amount: int) -> int:
    """A lapis gain after the player's multiplier (rounded; never below the original for factors >= 1)."""
    factor = settings().get("lapis_multiplier")
    if factor is None or int(amount) <= 0:
        return int(amount)
    return int(round(int(amount) * factor))


def adjust(rate: float, rarity, featured: bool = False) -> float:
    """`rate` after the player's multipliers for a unit of `rarity` (featured = a rate-up unit)."""
    current = settings()
    if not current:
        return rate
    try:
        level = int(rarity or 0)
    except (TypeError, ValueError):
        level = 0
    factor = current.get("rarity_multiplier", {}).get(level, 1.0)
    if featured:
        factor *= current.get("featured_multiplier", 1.0)
    return rate * factor


def adjust_rows(rows: list, featured_ids=()) -> list:
    """Copies of explicit `{unit_id, rarity, rate}` rows with the multipliers applied.
    Item rows (a `kind` other than 10) are left alone."""
    if not active():
        return rows
    featured = {str(unit) for unit in featured_ids}
    out = []
    for row in rows:
        if int(row.get("kind", 10) or 10) != 10 or "rate" not in row:
            out.append(row)
            continue
        out.append(dict(row, rate=adjust(float(row.get("rate") or 0), row.get("rarity"),
                                         str(row.get("unit_id")) in featured)))
    return out
