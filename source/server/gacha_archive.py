"""Browse the existing summon catalogue by story season and collaboration."""
from collections import defaultdict
from datetime import date
import json
from pathlib import Path


# Global story starts from the existing calendar's source, Update_Schedule.
# These are browsing eras, not save progression or real-time availability gates.
STORY_STARTS = (date(2017, 11, 16), date(2020, 1, 30), date(2021, 11, 18))
COLLABORATIONS = (
    'Brave Frontier', 'Crystal Defenders', 'Deus Ex', 'Dragon Quest',
    'Fullmetal Alchemist', 'Just Cause', "King's Knight", 'Kingdom Hearts',
    'Legend of Mana', 'NieR', 'Octopath Traveler', 'Secret of Mana', 'Star Ocean',
    'Tomb Raider', 'Trials of Mana', 'Valkyrie Profile', 'WOTV', 'Xenogears', 'Katy Perry',
)
GROUPS = (('standard', 'Standard'), ('season1', 'Season 1'), ('season2', 'Season 2'),
          ('season3', 'Season 3'), ('season4', 'Season 4'), ('collaborations', 'Collab'))
# A season with more banners than this is shown as several groups, each a run of whole release years.
# The client builds a sprite and a scroll row for every banner in the chosen group, so a big season made
# the summon list slow to open and to scroll. The first part keeps the season's id, so a saved choice
# still opens it.
SPLIT_AT = 80
# Always-available summons, shown with every group (as on the live game).
PERMANENT_NAMES = {
    'Standard Summon', 'Rare Summon', 'Premium 10+1 Summon', '5★ Guaranteed 10+1 Summon',
    'NV Guaranteed EX Summon B',
}
# Original GL9 tab of each GachaMst type code: GachaTopScene::setListLayout
# (0x2120554) files a banner by GachaMst::isPayType / isFreeType (0, 6, 900) /
# isLimitedType (50, 7).
FREE_CODES, LIMITED_CODES = {0, 6, 900}, {50, 7}


def english_art(banner):
    """True when the banner's art is Global English art: the saved Global cache or the community calendar."""
    import os
    import data_paths
    from ffbe_gacha import banner_art_index
    path = banner_art_index().get(str((banner.get('art') or {}).get('banner') or ''))
    if not path:
        return False
    roots = (data_paths.COMMUNITY_ART_ROOT, os.path.join(data_paths.GAME_FILES, 'en'),
             os.path.join(data_paths.CDN_ROOT, 'en'))
    path = os.path.normcase(os.path.abspath(path))
    return any(path.startswith(os.path.normcase(os.path.abspath(root)) + os.sep) for root in roots)


def _ticket_only(banner):
    cost = banner.get('cost')
    cost = cost[0] if isinstance(cost, list) and cost else cost
    return not cost or (
        isinstance(cost, dict) and cost.get('kind') in ('ticket', 'important', 'item'))


def wire_type(banner, code):
    """The GachaMst type code that puts the banner on its original tab.
    Community-calendar banners were the limited-time event summons; free, friend and
    ticket-only summons belong on the Standard Summon tab."""
    # Keep the native step-up type. Its behavior is distinct from the tab
    # category; the original client must still recognize isNewStepUpGacha.
    if banner.get('steps'):
        return 5
    if banner.get('selection'):
        return 6
    if banner.get('boxes'):
        return 7
    tab = banner.get('tab')
    if tab:  # an explicit original tab (named banners)
        return {'limited': 50, 'free': 0}.get(tab, code if code not in FREE_CODES | LIMITED_CODES else 1)
    if code in LIMITED_CODES or code in FREE_CODES:
        return code
    if banner.get('community'):
        return 50
    if banner.get('type') != 'step' and _ticket_only(banner):
        return 0
    return code


_FAMILIES = []
def _standard_families():
    if not _FAMILIES:
        doc = json.loads(Path(__file__).with_name('gacha_standard.json').read_text(encoding='utf-8'))
        _FAMILIES.append(frozenset(str(row['id']) for row in doc.get('banners', [])))
    return _FAMILIES[0]


def permanent(banner, families=None):
    families = _standard_families() if families is None else families
    return (str(banner['id']) in families or banner.get('name') in PERMANENT_NAMES
            or banner.get('type') == 'friend')


def _collaboration(banner):
    search = banner.get('name', '') + ' ' + str((banner.get('art') or {}).get('banner', ''))
    return next((name for name in COLLABORATIONS if name.lower() in search.lower()), None)


def _released(banner):
    try:
        release = (banner.get('community') or {}).get('release') or banner['release']
        parts = list(map(int, str(release).split('-'))) + [1]
        return date(*parts[:3])
    except (KeyError, TypeError, ValueError):
        return None


# The grouping depends only on the banners' ids and static content, so it is worked out once per banner
# list: it serialises every offer (pools included) and ran on each summon screen visit and menu tap.
_GROUPS_CACHE = {}


def catalogue(banners):
    """Every non-permanent banner belongs to exactly one group; the permanent summons
    appear with every group. Uncertain dates stay under Standard. Collab banners are
    ordered by series, and seasons by release date."""
    key = tuple(str(banner['id']) for banner in banners)
    if key not in _GROUPS_CACHE:
        _GROUPS_CACHE.clear()
        _GROUPS_CACHE[key] = _catalogue(banners)
    return [dict(group, ids=list(group['ids'])) for group in _GROUPS_CACHE[key]]


def _catalogue(banners):
    families = _standard_families()
    members = defaultdict(list)
    shared = []
    seen = set()
    aliases = {str(alias) for banner in banners for alias in banner.get('alias_ids', [])
               if str(alias) != str(banner['id'])}
    for banner in banners:
        bid = str(banner['id'])
        if bid in aliases:
            continue
        # A reused picture does not make two campaigns the same. Preserve reruns
        # and distinct offers; collapse only identical campaign/offer records.
        offer = {key: banner.get(key) for key in ('cost', 'draws', 'steps', 'ticket_group_id',
                                                 'guarantee', 'secondary_offer', 'pool', 'reward_pool',
                                                 'selection', 'daily_limit', 'weekly_limit', 'purchase_limit',
                                                 'lap_limit', 'milestone_bonus', 'bonus_rewards', 'bonus_choice',
                                                 'guarantee_slots')}
        if bid in families:
            identity = ('standard', banner.get('name'), json.dumps(offer, sort_keys=True))
        else:
            identity = (((banner.get('art') or {}).get('banner'), str(_released(banner))),
                        json.dumps(offer, sort_keys=True))
        if identity in seen:
            continue
        seen.add(identity)
        if permanent(banner, families):
            shared.append(bid)
            continue
        collab = _collaboration(banner)
        released = _released(banner)
        if collab:
            members['collaborations'].append((collab, released or date.min, bid))
        elif banner.get('season'):
            members[banner['season']].append(('', released or date.min, bid))
        elif released:
            season = 1 + sum(released >= start for start in STORY_STARTS)
            members['season' + str(season)].append(('', released, bid))
        else:
            members['standard'].append(('', date.min, bid))
    by_id = {str(banner['id']): banner for banner in banners}
    from ffbe_gacha import gacha_type_code
    groups = []
    for key, label in GROUPS:
        rows = sorted(members[key], key=lambda row: (row[0], row[1]))
        for part_id, part_label, part in _season_parts(key, label, rows):
            ordered = [bid for _, _, bid in part]
            ids = shared + ordered
            # Open the group on its own lineup: Limited Time when it has limited banners.
            limited = any(by_id[bid].get('tab') == 'limited' or
                          gacha_type_code(by_id[bid]) in LIMITED_CODES for bid in ids)
            tab = 2 if limited and key != 'standard' else 0
            groups.append({'id': part_id, 'label': part_label, 'ids': ids, 'count': len(ordered), 'tab': tab})
    return groups


def _season_parts(key, label, rows):
    """(id, label, rows) for each group a season is shown as. Rows are (series, released, id), in release
    order. Seasons over SPLIT_AT banners split between release years, never inside one year: "S2 2017-18"
    as `season2`, then "S2 2019-20" as `season2-2`. Standard and collaborations stay whole."""
    if not key.startswith('season') or len(rows) <= SPLIT_AT:
        return [(key, label, rows)]
    years = []
    for row in rows:
        year = row[1].year
        if years and years[-1][0] == year:
            years[-1][1].append(row)
        else:
            years.append((year, [row]))
    runs = []
    for year, chunk in years:
        if runs and len(runs[-1][2]) + len(chunk) <= SPLIT_AT:
            runs[-1][1] = year
            runs[-1][2].extend(chunk)
        else:
            runs.append([year, year, list(chunk)])
    if len(runs) == 1:
        return [(key, label, rows)]
    short = 'S' + key[len('season'):]
    parts = []
    for index, (first, last, chunk) in enumerate(runs):
        dated = [row[1].year for row in chunk if row[1] != date.min]
        first, last = (min(dated), max(dated)) if dated else (None, None)
        span = ('undated' if first is None else str(first) if first == last
                else '%d-%02d' % (first, last % 100))
        parts.append((key if index == 0 else '%s-%d' % (key, index + 1), short + ' ' + span, chunk))
    return parts


def selected_group(player, groups):
    selected = player.data.get('summon_archive') if player else None
    return next((group for group in groups if group['id'] == selected), groups[0])


def visible_banners(player, banners):
    ids = selected_group(player, catalogue(banners))['ids']
    by_id = {str(banner['id']): banner for banner in banners}
    # GL9 sorts schedule rows by descending display order. Publish the archive's
    # series/date order there, rather than preserving unrelated old campaign ranks.
    return [dict(by_id[bid], schedule=dict(by_id[bid].get('schedule') or {},
                                         disp_order=len(ids) - index))
            for index, bid in enumerate(ids)]


def menu(player, banners, selection=''):
    groups = catalogue(banners)
    if selection:
        if selection not in {group['id'] for group in groups}:
            raise ValueError('Unknown summon archive group')
        player.data['summon_archive'] = selection
        player.dirty = True
    chosen = selected_group(player, groups)
    return {'groups': [{key: group[key] for key in ('id', 'label', 'count', 'tab')} for group in groups],
            'selected': {key: chosen[key] for key in ('id', 'label', 'count', 'tab')}}
