# How summons work, and how to change the rates

## The short version

Exvius Settings (the second launcher icon) has two summon rows:

- **5★ and Neo Vision chance:** 1x, 2x, 5x or 10x.
- **Rate-up units on top of that:** 1x, 2x or 4x.

They apply from the next summon, and the in-game Drop Rates button shows the exact odds they produce.

## What happens on a pull

1. **The pool.** Each banner lists rarity tiers, for example 5★ 1%, 4★ 19%, 3★ 80%. A tier with no unit
   list is filled with every base unit of that rarity. Rate-up units take a share of their tier
   (`featured_share`), and the other units split the rest. Code: `expand_pool` in
   `source/server/player_state.py`.
2. **The draw.** Every slot picks one unit at random, weighted by its rate. The weights are divided by
   their total, so they don't have to add up to 100%. Code: `State.roll_gacha`, the `_pick` function.
3. **Guarantees.** A guaranteed 5★ or NV slot, or a ticket's rarity floor, replaces the lowest draws with
   a pick from the eligible units, by the same weights.

## Where the numbers live

| File (in `source/server`) | Banners | Typical split |
| --- | --- | --- |
| `gacha_standard.json` | Permanent summons | 5★ 1%, 4★ 19%, 3★ 80% |
| `gacha_community.json`, `gacha_catalogue.json` | Global calendar banners | 5★ 3% (rate-up units get a third of it), 4★ 19%, 3★ 78% |
| `gacha_named.json` | NV-era banners | NV 3%, 5★ 12%, 4★ 42.5%, 3★ 42.5% |
| `gacha_authored.json` | The hand-made set (tutorial, friend, tickets) | varies |

Editing those files changes one banner at a time but needs a new build. The multipliers change every
banner at once without a rebuild.

## The multiplier file

The settings screen writes `files/exvius/gacha_tweaks.json`. `source/server/gacha_tweaks.py` reads it
before every pull. It accepts finer values than the screen offers:

```json
{
  "rarity_multiplier": {"5": 3, "6": 3, "7": 3, "4": 1.5},
  "featured_multiplier": 2
}
```

- `rarity_multiplier` scales every unit of that base rarity (7 is Neo Vision).
- `featured_multiplier` scales a banner's rate-up units on top.
- No file, or a broken one, means the banner's own rates.
- Values are capped at 1000. Negative or non-numeric values are ignored.

Because weights are normalised, a multiplier isn't a flat percentage. 5x on a 1% tier comes out at about
4.8%, not 5%. The Drop Rates screen shows the real figure.

The multipliers don't touch costs, guarantees, step-ups, box summons, or item pools such as reward
summons.
