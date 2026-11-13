"""Supply the original native exchange screens with recovered shop stock."""
from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path
import time

from data_paths import TEXT_DIR
from exvius_actions_shops import (_action, _feature, _grant, _int, _node, _pay,
                                  _reply, _require, _rewards, _rows, _store)
from exvius_rewards import parse
from ffbe_state import State

START = '2020-01-01 00:00:00'
END = '2099-12-31 23:59:59'

# Currencies the player can still earn but whose shops were never served. Their whole original
# F_MEDAL_EXCHANGE_MST stock is offered, not only the fragment rows (#18, #23, #70).
FULL_STOCK = {
    '1209002122': 'Celebratory Lapis Replica (8th Anniversary)',  # United Forces / clash rewards
    '1209001907': 'Exchange Ticket (Original Armory IV)',  # United Forces step 3
    '1209002145': "Exchange Ticket (It's a Celebration, Kupo!)",  # United Forces step 6
    '1209002102': 'NV Unit Select Ticket (8th Anniversary)',  # bought with Lapis Replicas
    '1209002103': 'VC Select Ticket (8th Anniversary)',  # bought with Lapis Replicas
    '1209002138': 'Summon Coin (C.K.Rain/H.R.Taivas)',
    '1209002139': 'NV Exchange Ticket (C.K.Rain/H.R.Taivas)',
    '1209002140': 'Exchange Ticket (Hero of Elmont)',
    '1209002141': 'Summon Coin (A.K.Lasswell)',
    '1209002142': 'NV Exchange Ticket (A.K.Lasswell)',
    '1209002143': 'Summon Coin (A.C.B.Rhus)',
    '1209002144': 'NV Exchange Ticket (A.C.B.Rhus)',
    '1209001045': 'Summon Coin (Sora/Cloud (KH))',
    '1209001046': 'Summon Coin (Riku/Sephiroth (KH))',
    '1209001298': 'Summon Coin (KHIII)',
}
# The NV Fragment Select Ticket (8th Anniversary) has no exchange rows of its own, so selling it
# would only mint another dead ticket.
SKIP_PRODUCTS = {'258031'}

# Unit Shop: every unit a summon could give, one copy per purchase, priced by player_tweaks
# (1 lapis or free). Long lists are split into tabs of at most UNIT_SHOP_TAB units, by name.
UNIT_SHOP_TAB = 250
UNIT_SHOP_GROUPS = (('7', 'Neo Vision'), ('5', '5\u2605 base'), ('4', '4\u2605 base'),
                    ('3', '1-3\u2605 base'), ('2', '1-3\u2605 base'), ('1', '1-3\u2605 base'))
UNIT_SHOP_PRODUCT = 1000000000  # + the unit id, so a unit keeps its product id across updates
# Every exchange shop priced in lapis is charged in gil instead, at the same number (30 is gil's
# reward kind; the shop's currency header reads 30 as GIL, NVShopItemListScene_sg::updateCurrencyItem).
SHOP_CURRENCY = (30, '1')
# Gear Shop: every equipment (kind 21) and materia (kind 22) piece any merchant exchange sold, one
# per purchase, for the same number of gil as its cheapest exchange price, no buy limit. Product ids
# count up from GEAR_SHOP_PRODUCT in item-id order (equipment ids don't fit beside an offset).
GEAR_SHOP_PRODUCT = 970000000
GEAR_SHOP_KINDS = ((21, 'ITEM_EQUIP', 'Equipment', ''), (22, 'MATERIA', 'Materia', ''))
# Item Shop: the same for every other single reward a merchant exchange sold: items (awakening
# materials, crystals, potions, event currencies), recipes, vision cards and tickets. Product ids
# count up from ITEM_SHOP_PRODUCT the same way. 23:912 is left out: its icon is not in the item packs.
ITEM_SHOP_PRODUCT = 975000000
ITEM_SHOP_KINDS = ((20, 'ITEM', 'Items', ''), (60, 'RECIPE_BOOK', 'Recipes', ' (Recipe)'),
                   (27, 'VISION_CARD', 'Vision Cards', ''), (23, 'IMPORTANT_ITEM', 'Tickets', ''))
ITEM_SHOP_SKIP = {(23, '912')}


def _units_with_icons():
    """Unit ids whose unit_icon_<id>.png ships in the game data (content/unit_icons.json)."""
    path = Path(__file__).with_name('content').joinpath('unit_icons.json')
    return set(json.loads(path.read_text(encoding='utf-8'))['units'])


def _unit_names():
    names = {}
    path = Path(TEXT_DIR) / 'F_TEXT_UNITS_NAME.ndjson'
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            row = json.loads(line)
            names[row['key'].rsplit('_', 1)[-1]] = row['v'][0].strip()
    return names


def unit_shops():
    """[(tab title, [(unit id, label)])] for the Unit Shop.

    The units are the series roots a summon pool draws from (player_state.unit_roots_by_rarity):
    rows whose id is their own family root, at their base rarity. Left out: units with no name row
    (the award screen crashes on them), Brave Shift forms (another row's JPW8Vs40 points at them;
    they come with their NV unit), the 9xxxxxxxx material units (moogles, pots, cactuars) and units
    with no icon in the game data (the shop list crashes drawing them, e.g. Lara Croft, Ling, Xon).
    Neo Vision units are the roots whose base rarity is 7."""
    names = _unit_names()
    icons = _units_with_icons()
    rows = _rows('F_UNIT_MST')
    shifted = {str(r.get('JPW8Vs40') or '') for r in rows
               if str(r.get('JPW8Vs40') or '') not in ('', '0', str(r.get('3HriTp6B')))}
    groups = defaultdict(list)
    for row in rows:
        uid = str(row.get('3HriTp6B', ''))
        if (uid != str(row.get('woghJa61')) or names.get(uid, '<na>') in ('', '<na>')
                or uid.startswith('9') or uid in shifted or uid not in icons):
            continue
        title = dict(UNIT_SHOP_GROUPS).get(str(row.get('9fW0TePj')))
        if title is None:
            continue
        label = names[uid]
        if str(row.get('9fW0TePj')) == '7' and 'Neo Vision' not in label:
            label += ' (NV)'
        groups[title].append((uid, label))
    tabs = []
    for title in dict.fromkeys(t for _, t in UNIT_SHOP_GROUPS):
        units = sorted(groups.get(title, []), key=lambda u: (u[1].lower(), int(u[0])))
        parts = max(1, -(-len(units) // UNIT_SHOP_TAB))
        size = -(-len(units) // parts) if units else 0
        for start in range(0, len(units), size or 1):
            chunk = units[start:start + size]
            name = 'Unit Shop: ' + title
            if parts > 1:
                first, last = (u[1][:1].upper() for u in (chunk[0], chunk[-1]))
                name += ' (' + (first if first.isalpha() else 'A') + '-' + last + ')'
            tabs.append((name, chunk))
    return tabs


def _split_tabs(prefix, items):
    """Split [(id, label)] sorted by label into tabs of at most UNIT_SHOP_TAB, named by letter range."""
    items = sorted(items, key=lambda u: (u[1].lower(), int(u[0])))
    parts = max(1, -(-len(items) // UNIT_SHOP_TAB))
    size = -(-len(items) // parts) if items else 0
    tabs = []
    for start in range(0, len(items), size or 1):
        chunk = items[start:start + size]
        name = prefix
        if parts > 1:
            first, last = (u[1][:1].upper() for u in (chunk[0], chunk[-1]))
            name += ' (' + (first if first.isalpha() else 'A') + '-' + last + ')'
        tabs.append((name, chunk))
    return tabs


def _exchange_shops(shop, kinds, skip=()):
    """[(tab title, kind, [(item id, label, gil price)])] for a shop of exchange rewards.

    Every reward of the given kinds that F_MEDAL_EXCHANGE_MST (the merchant exchanges, whose own
    currencies the game checks on the phone) sells on its own, at its cheapest price per piece in
    that exchange's currency, charged as the same number of gil. Rewards with no name row are left
    out (the award screen crashes on them)."""
    wanted = {kind for kind, _, _, _ in kinds}
    best = {}
    for row in _rows('F_MEDAL_EXCHANGE_MST'):
        try:
            rewards = parse(row.get('7iJpH5zZ'))
            price = int(row.get('Qy5EvcK1') or 0)
        except ValueError:
            continue
        if len(rewards) != 1 or price <= 0:
            continue
        reward = rewards[0]
        key = (reward['kind'], str(reward['id']))
        if reward['kind'] not in wanted or key in skip or reward['count'] <= 0:
            continue
        each = max(1, -(-price // reward['count']))
        best[key] = min(best.get(key, each), each)
    tabs = []
    for kind, table, title, suffix in kinds:
        names = {}
        path = Path(TEXT_DIR) / ('F_TEXT_' + table + '_NAME.ndjson')
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                row = json.loads(line)
                names[row['key'].rsplit('_', 1)[-1]] = row['v'][0].strip()
        items = [(iid, names[iid] + suffix) for (k, iid) in best if k == kind and names.get(iid)]
        for name, chunk in _split_tabs(shop + ': ' + title, items):
            tabs.append((name, kind, [(iid, label, best[kind, iid]) for iid, label in chunk]))
    return tabs


def gear_shops():
    """Gear Shop tabs: every exchange equipment and materia piece (see _exchange_shops)."""
    return _exchange_shops('Gear Shop', GEAR_SHOP_KINDS)


def item_shops():
    """Item Shop tabs: every other exchange item, recipe, vision card and ticket (see _exchange_shops)."""
    return _exchange_shops('Item Shop', ITEM_SHOP_KINDS, ITEM_SHOP_SKIP)


@lru_cache(maxsize=1)
def catalogue():
    # Fragment exchanges retain their original currency, quantity and limits.
    names = {}
    path = Path(TEXT_DIR) / 'F_TEXT_ITEM_NAME.ndjson'
    for line in path.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        names[row['key'].rsplit('_', 1)[-1]] = row['v'][0]
    currencies = defaultdict(list)
    full = defaultdict(list)
    for row in _rows('F_MEDAL_EXCHANGE_MST'):
        if str(row.get('ak2dhKm3')) in FULL_STOCK:
            if str(row.get('S21FT3L8')) not in SKIP_PRODUCTS:
                full[str(row['ak2dhKm3'])].append(row)
            continue
        if not str(row.get('7iJpH5zZ', '')).startswith('20:250'):
            continue
        rewards = parse(row.get('7iJpH5zZ'))
        if len(rewards) == 1 and rewards[0]['kind'] == 20 and str(rewards[0]['id']).startswith('250'):
            currencies[str(row['ak2dhKm3'])].append((row, rewards[0]))
    details, products, offers = [], [], {}

    def detail(did, title, kind, currency, category, banner=0):
        details.append({'3X1gLufw': str(did), 'X1IuZnj2': '0', 'JV8AIH3n': str(category),
                        'Z0EN6jSh': str(len(details) + 1), 'fSxqkF10': str(banner), 'uYcL8IQ1': '-1',
                        '6uvHX2JG': title, 'VjJQ51uG': START, 'm8ivD4NX': END,
                        '0GgK6ytT': str(kind) + ':' + str(currency)})

    def product(pid, did, reward, price, limit, currency, monthly=False, label=None):
        row = {'jPV7Xc4N': str(pid), '3X1gLufw': str(did), 'P4puB2ch': reward,
               'e4mG8jTc': str(price), 'uYcL8IQ1': str(-1 if int(limit) == 2147483647 else limit),
               'Z0EN6jSh': str(len(products) + 1),
               '6uvHX2JG': '', 'VjJQ51uG': START, 'm8ivD4NX': END, 'fbcj5Aq9': '', 'JasF1S3u': ''}
        products.append(row)
        offers[str(pid)] = {'detail': str(did), 'rewards': parse(reward), 'cost': currency,
                            'price': int(price), 'limit': int(limit), 'monthly': monthly}
        if label:
            offers[str(pid)]['label'] = label

    for index, (currency, stock) in enumerate(sorted(currencies.items(), key=lambda pair: int(pair[0]))):
        did = 850000000 + index
        detail(did, names.get(currency, 'Fragment Exchange'), 20, currency, 5)
        for row, _reward in stock:
            limit = int(row['x0NDnEC9']) if row['kR4n5DxP'] == '1' else 2147483647
            product(900000000 + int(row['S21FT3L8']), did, row['7iJpH5zZ'], row['Qy5EvcK1'],
                    limit, (20, currency))

    # Original monthly VIP stock and prices, recorded on the preservation wiki.
    # https://exvius.fandom.com/wiki/VIP_Coin#Exchange_Shop
    did = 850001000
    detail(did, 'VIP Shop', SHOP_CURRENCY[0], SHOP_CURRENCY[1], 6, 10)
    vip = [
        ('23:110260:10', 10000, 1), ('23:110260:1', 1000, 1),
        ('23:80:1', 1750, 1), ('23:50:2', 200, 2),
        ('23:110180:1', 1400, 2), ('23:110160:3', 200, 5),
        ('20:900000001:1', 2500, 1),
        ('10:904000105:1:100:1:500:0:0:100000050', 200, 8),
        ('20:293000200:1', 200, 3), ('20:293000100:1', 1000, 2),
        ('10:900010501:10', 60, 20), ('10:900020401:10:100:60', 70, 20),
        ('27:900020101:1', 700, 10), ('20:1209001274:30', 200, 10),
    ]
    for index, (reward, price, limit) in enumerate(vip):
        product(940000000 + index, did, reward, price, limit, SHOP_CURRENCY, True)
    recovered = json.loads(Path(__file__).with_name('content').joinpath('permanent_shops.json').read_text())
    for index, shop in enumerate(recovered['shops']):
        did = 850001001 + index
        kind, currency = shop['currency']
        category = shop.get('category', 6)
        if category == 6:
            kind, currency = SHOP_CURRENCY
        banner = 60 if shop['name'] == 'EX Coin Shop' else 0
        detail(did, shop['name'], kind, currency, category, banner)
        for position, row in enumerate(shop['products']):
            product(940001000 + index * 1000 + position, did, row['reward'], row['price'],
                    row['limit'], (kind, currency), shop['reset_months'])
    # Same product ids as the fragment loop, so purchases made there still count.
    for index, currency in enumerate(FULL_STOCK):
        stock = full.get(currency)
        if not stock:
            continue
        did = 850002000 + index
        detail(did, names.get(currency, FULL_STOCK[currency]), 20, currency, 4)
        for row in stock:
            limit = int(row['x0NDnEC9']) if row['kR4n5DxP'] == '1' else 2147483647
            product(900000000 + int(row['S21FT3L8']), did, row['7iJpH5zZ'], row['Qy5EvcK1'],
                    limit, (20, currency))
    # Unit Shop tabs sit with the other coin shops (category 6). The listed price is the default;
    # entry() and purchase() apply the player's current unit_shop_price.
    for index, (title, units) in enumerate(unit_shops()):
        did = 850003000 + index
        detail(did, title, SHOP_CURRENCY[0], SHOP_CURRENCY[1], 6)
        for uid, label in units:
            product(UNIT_SHOP_PRODUCT + int(uid), did, '10:' + uid + ':1', 1, 2147483647,
                    SHOP_CURRENCY, label=label)
            offers[str(UNIT_SHOP_PRODUCT + int(uid))]['unit_shop'] = True
    # Gear Shop tabs follow, also in gil with the coin shops.
    gear = sorted((kind, iid) for _, kind, items in gear_shops() for iid, _, _ in items)
    gear_pid = {item: GEAR_SHOP_PRODUCT + index for index, item in enumerate(gear)}
    for index, (title, kind, items) in enumerate(gear_shops()):
        did = 850004000 + index
        detail(did, title, SHOP_CURRENCY[0], SHOP_CURRENCY[1], 6)
        for iid, label, price in items:
            product(gear_pid[kind, iid], did, str(kind) + ':' + iid + ':1', price, 2147483647,
                    SHOP_CURRENCY, label=label)
    # Item Shop tabs last: awakening materials and every other exchange reward, in gil.
    stock = item_shops()
    item_pid = {item: ITEM_SHOP_PRODUCT + index for index, item in
                enumerate(sorted((kind, iid) for _, kind, items in stock for iid, _, _ in items))}
    for index, (title, kind, items) in enumerate(stock):
        did = 850005000 + index
        detail(did, title, SHOP_CURRENCY[0], SHOP_CURRENCY[1], 6)
        for iid, label, price in items:
            product(item_pid[kind, iid], did, str(kind) + ':' + iid + ':1', price, 2147483647,
                    SHOP_CURRENCY, label=label)
    return details, products, offers


def _price(offer):
    if offer.get('unit_shop'):
        from player_tweaks import unit_shop_price
        return unit_shop_price()
    return offer['price']


def receipt_key(pid, offer):
    if not offer['monthly']:
        return pid
    months = int(offer['monthly'])
    now = time.localtime()
    period = (now.tm_year * 12 + now.tm_mon - 1) // months
    return pid + '/' + str(period)


@lru_cache(maxsize=1)
def labels():
    names = {}
    for kind, table in [(20, 'ITEM'), (23, 'IMPORTANT_ITEM'), (10, 'UNITS'), (27, 'VISION_CARD'),
                        (21, 'ITEM_EQUIP'), (22, 'MATERIA'), (60, 'RECIPE_BOOK')]:
        path = Path(TEXT_DIR) / ('F_TEXT_' + table + '_NAME.ndjson')
        for line in path.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            names[kind, row['key'].rsplit('_', 1)[-1]] = row['v'][0].strip()
    result = {}
    for pid, offer in catalogue()[2].items():
        if offer.get('label'):
            result[pid] = {'name': offer['label'], 'description': 'Buy ' + offer['label'] + '.'}
            continue
        texts = []
        for row in offer['rewards']:
            name = names.get((row['kind'], str(row['id'])), 'Reward ' + str(row['id']))
            points = list(row.get('affinity_points') or []) + ['', '']
            if points[0]:
                name += ' (ALL ' + str(int(points[0]) // 10) + '%)'
            elif points[1]:
                name += ' (Super Trust ' + str(int(points[1]) // 10) + '%)'
            if row['count'] > 1:
                name += ' x' + str(row['count'])
            texts.append(name)
        title = ', '.join(texts)
        result[pid] = {'name': title, 'description': 'Exchange for ' + title + '.'}
    return result


def entry(spec, req):
    details, products, offers = catalogue()
    out = _reply(spec)
    out['F2rNo6qf'] = [dict(row) for row in details]
    out['TPrh6Ay3'] = [dict(row) for row in products]
    for row in out['TPrh6Ay3']:
        offer = offers.get(row['jPV7Xc4N'])
        if offer and offer.get('unit_shop'):
            row['e4mG8jTc'] = str(_price(offer))
    counts = _feature('shop_catalogue').get('counts', {})
    out['qS62ewjH'] = [{'jPV7Xc4N': pid, '3X1gLufw': offer['detail'],
                        'Q8GLK1pz': str(counts.get(receipt_key(pid, offer), 0))}
                       for pid, offer in offers.items()]
    return out


@_action
def purchase(spec, req):
    node = _node(req, '4mrD6JuA') or {}
    pid = str(node.get('jPV7Xc4N', ''))
    offer = catalogue()[2].get(pid)
    _require(offer is not None, 'unknown exchange product')
    quantity = _int(node.get('Qy5EvcK1'), 1)
    counts = dict(_feature('shop_catalogue').get('counts', {}))
    key = receipt_key(pid, offer)
    bought = int(counts.get(key, 0))
    _require(bought + quantity <= offer['limit'], 'exchange stock exhausted')
    rewards = [dict(row, count=row['count'] * quantity) for row in offer['rewards']]
    _rewards(rewards)
    kind, currency = offer['cost']
    amount = _price(offer) * quantity
    if kind == 50:
        _require(State.player.spend_lapis(amount), 'not enough Lapis')
    elif kind == 30:
        _require(State.player.spend_currency('gil', amount), 'not enough gil')
    else:
        _pay([{'kind': kind, 'id': currency, 'count': amount}])
    _grant(rewards)
    counts[key] = bought + quantity
    _store('shop_catalogue', {'counts': counts})
    out = _reply(spec)
    out['4owH1uT2'] = [{'jPV7Xc4N': pid, '3X1gLufw': offer['detail'], 'Q8GLK1pz': str(counts[key])}]
    return out
