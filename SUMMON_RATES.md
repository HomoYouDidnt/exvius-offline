# How summons work, and how to change the rates, lapis gains and summon prices

## The short version

Exvius Settings (the second launcher icon) has four rows for this:

- **5★ and Neo Vision chance:** 1x, 2x, 5x or 10x.
- **Rate-up units on top of that:** 1x, 2x or 4x.
- **Lapis gained:** 1x, 2x, 3x, 5x or 10x. Every lapis credit (mission challenges, rank-ups, quests,
  mail, exchanges) is multiplied. Spending isn't.
- **Lapis summon price:** Normal, Half, or 1 lapis for any lapis summon, single or multi. Tickets,
  friend points and item costs don't change.

They apply right away. The in-game Drop Rates button shows the exact odds; reopen the summon screen to
see a new price. Result screens still print a mission's original lapis amount, but the top bar shows
what you really have.

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

## The settings file

The settings screen writes `files/exvius/tweaks.json`. `source/server/player_tweaks.py` reads it whenever
it changes. It accepts finer values than the screen offers:

```json
{
  "rarity_multiplier": {"5": 3, "6": 3, "7": 3, "4": 1.5},
  "featured_multiplier": 2,
  "lapis_multiplier": 2.5,
  "lapis_summon_cost": "half",
  "unit_shop_price": "free"
}
```

- `rarity_multiplier` scales every unit of that base rarity (7 is Neo Vision).
- `featured_multiplier` scales a banner's rate-up units on top.
- `lapis_multiplier` scales lapis gains in `State.add_currency`, the one place lapis is credited.
- `lapis_summon_cost` is `"half"` or `"1"`. The shown price and the charge both go through
  `summon_cost`, so the screen and your balance always agree.
- `unit_shop_price` is `"1"` (the default) or `"free"`: what one unit costs in the Unit Shop.
- No file, or a broken one, means the game's own numbers.
- Multipliers are capped at 1000. Negative or non-numeric values are ignored.

Because weights are normalised, a multiplier isn't a flat percentage. 5x on a 1% tier comes out at about
4.8%, not 5%. The Drop Rates screen shows the real figure.

The rate multipliers don't touch guarantees, step-up structure, box summons, or item pools such as reward
summons.

## Unit Shop

The exchange shop has Unit Shop tabs next to the VIP and coin shops. They sell every unit a summon can
give, one copy at a time, with no limit, for 1 lapis each (or free, from Exvius Settings).

- Units come at their base rarity, the same form a summon gives: a 5★ base unit arrives at 5★ and
  awakens the usual way. Extra copies work as awakening and enhancement copies.
- Neo Vision units have their own tabs. Brave Shift forms aren't sold separately; they come with their NV unit.
- The list is built from the game's unit table (`F_UNIT_MST`) the first time the shop opens:
  `exvius_shop_catalogue.unit_shops`. It leaves out units with no name (the result screen crashes on
  them) and the 9xxxxxxxx material units (moogles, pots, cactuars).
- Long lists are split into tabs of up to 250 units, sorted by name.
