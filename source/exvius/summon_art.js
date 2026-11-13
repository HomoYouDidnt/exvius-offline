import artwork from '../server/summon_art.json';

export function fitSummonArt(sourceWidth, sourceHeight, width, height) {
  if (![sourceWidth, sourceHeight, width, height].every(n => Number.isFinite(n) && n > 0)) return null;
  const scale = Math.min(width / sourceWidth, height / sourceHeight);
  return {width: sourceWidth * scale, height: sourceHeight * scale};
}

// GachaDetailScrlObj::updatePosition runs for every banner in the carousel on
// every frame while it scrolls, and a large summon group holds hundreds. The
// centring below is done in C so those calls never enter JavaScript.
export const ART_CENTER_SOURCE = `
#include <gum/guminterceptor.h>

extern void * getBanner (void * object);
extern const float * anchor (void * node);
extern float getX (void * node);
extern float getY (void * node);
extern void setX (void * node, float x);
extern void setY (void * node, float y);

typedef struct { float dx, dy, x, y; int adjusted; } Box;
typedef struct { void * object; } Call;

#define CAP 4096
#define MASK (CAP - 1)
/* The table lives in memory the script allocates: some devices map the
   compiled module read-only, so a static table there faults on first write. */
typedef struct { void * keys[CAP]; Box boxes[CAP]; unsigned int used; } Table;
extern Table table;

static unsigned int slot_of (void * key)
{
  unsigned long long h = (unsigned long long) key;
  h ^= h >> 33;
  h *= 0xff51afd7ed558ccdULL;
  h ^= h >> 33;
  return (unsigned int) h & MASK;
}

static int find (void * object)
{
  unsigned int i = slot_of (object);
  while (table.keys[i] != 0)
  {
    if (table.keys[i] == object)
      return (int) i;
    i = (i + 1) & MASK;
  }
  return -1;
}

void art_remove (void * object)
{
  int found = find (object);
  unsigned int i, j, k;
  if (found < 0)
    return;
  i = (unsigned int) found;
  j = i;
  for (;;)
  {
    j = (j + 1) & MASK;
    if (table.keys[j] == 0)
      break;
    k = slot_of (table.keys[j]);
    if (i <= j ? (i < k && k <= j) : (i < k || k <= j))
      continue;
    table.keys[i] = table.keys[j];
    table.boxes[i] = table.boxes[j];
    i = j;
  }
  table.keys[i] = 0;
  table.used--;
}

void art_set (void * object, float dx, float dy)
{
  int found = find (object);
  unsigned int i;
  if (found < 0)
  {
    if (table.used >= CAP / 4 * 3)
      return;
    i = slot_of (object);
    while (table.keys[i] != 0)
      i = (i + 1) & MASK;
    table.keys[i] = object;
    table.used++;
  }
  else
    i = (unsigned int) found;
  table.boxes[i].dx = dx;
  table.boxes[i].dy = dy;
  table.boxes[i].adjusted = 0;
}

void art_center (void * object)
{
  int found = find (object);
  Box * box;
  void * node;
  const float * point;
  float x, y, ex, ey;
  if (found < 0)
    return;
  box = &table.boxes[found];
  node = getBanner (object);
  if (node == 0)
    return;
  x = getX (node);
  y = getY (node);
  ex = x - box->x;
  ey = y - box->y;
  if (box->adjusted && ex < 0.01f && ex > -0.01f && ey < 0.01f && ey > -0.01f)
    return;
  point = anchor (node);
  box->x = x + (0.5f - point[0]) * box->dx;
  box->y = y + (0.5f - point[1]) * box->dy;
  box->adjusted = 1;
  setX (node, box->x);
  setY (node, box->y);
}

void onEnter (GumInvocationContext * ic)
{
  GUM_IC_GET_INVOCATION_DATA (ic, Call)->object = gum_invocation_context_get_nth_argument (ic, 0);
}

void onLeave (GumInvocationContext * ic)
{
  art_center (GUM_IC_GET_INVOCATION_DATA (ic, Call)->object);
}

void onDestroy (GumInvocationContext * ic)
{
  art_remove (gum_invocation_context_get_nth_argument (ic, 0));
}
`;

function nativeArtCenter(module, note) {
  if (typeof CModule === 'undefined') return null;
  try {
    const exported = name => module.getExportByName(name);
    // Pages from Memory.alloc are zero-filled, which the table needs.
    const size = 4096 * (Process.pointerSize + 20) + 16;
    const table = Memory.alloc(Math.ceil(size / Process.pageSize) * Process.pageSize);
    const code = new CModule(ART_CENTER_SOURCE, {
      table,
      getBanner: exported('_ZNK18GachaDetailScrlObj9getBannerEv'),
      anchor: exported('_ZNK7cocos2d4Node14getAnchorPointEv'),
      getX: exported('_ZNK7cocos2d4Node12getPositionXEv'),
      getY: exported('_ZNK7cocos2d4Node12getPositionYEv'),
      setX: exported('_ZN7cocos2d4Node12setPositionXEf'),
      setY: exported('_ZN7cocos2d4Node12setPositionYEf')
    });
    note('SUMMON_ART_CENTER native');
    return {
      code,
      table,
      set: new NativeFunction(code.art_set, 'void', ['pointer', 'float', 'float']),
      remove: new NativeFunction(code.art_remove, 'void', ['pointer']),
      center: new NativeFunction(code.art_center, 'void', ['pointer'])
    };
  } catch (error) {
    note('SUMMON_ART_CENTER_FALLBACK ' + error);
    return null;
  }
}

// GL9's image carousel stretches every source to its layout rectangle. Use
// the original wide variant where available, then fit the complete image
// proportionally. Both source artwork and native carousel controls stay intact.
export function installSummonArt(module, note, retained, bridge) {
  const native = (name, result, args) => new NativeFunction(module.getExportByName(name), result, args, {exceptions: 'propagate'});
  const makeString = native('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEC2IDnEEPKc',
    'void', ['pointer', 'pointer']);
  const freeString = native('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEED2Ev',
    'void', ['pointer']);
  const getBanner = native('_ZNK18GachaDetailScrlObj9getBannerEv', 'pointer', ['pointer']);
  const anchor = native('_ZNK7cocos2d4Node14getAnchorPointEv', 'pointer', ['pointer']);
  const getX = native('_ZNK7cocos2d4Node12getPositionXEv', 'float', ['pointer']);
  const getY = native('_ZNK7cocos2d4Node12getPositionYEv', 'float', ['pointer']);
  const setX = native('_ZN7cocos2d4Node12setPositionXEf', 'void', ['pointer', 'float']);
  const setY = native('_ZN7cocos2d4Node12setPositionYEf', 'void', ['pointer', 'float']);
  const spriteWidth = native('_ZN10GameSprite8getWidthEv', 'int', ['pointer']);
  const spriteHeight = native('_ZN10GameSprite9getHeightEv', 'int', ['pointer']);
  const spriteSize = native('_ZN10GameSprite7setSizeEff', 'void', ['pointer', 'float', 'float']);
  let listDepth = 0;
  retained.push(Interceptor.attach(module.getExportByName('_ZN13GachaTopScene13setListLayoutEv'), {
    onEnter() { listDepth += 1; },
    onLeave() { listDepth -= 1; }
  }));
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN12SpriteButton19initForChangeSpriteEiffiP10GameSpriteS1_ib'), {
    onEnter(args) {
      // The list builds its touch rectangle and row spacing from the banner
      // sprite. Its separate pressed overlay uses fixed artwork chosen by
      // summon type, so fit that overlay to this banner before native init.
      if (!listDepth || args[2].isNull() || args[3].isNull()) return;
      const width = spriteWidth(args[2]), height = spriteHeight(args[2]);
      if (width > 0 && height > 0 &&
          (spriteWidth(args[3]) !== width || spriteHeight(args[3]) !== height))
        spriteSize(args[3], width, height);
    }
  }));
  let currentObject = null, reports = 0;
  const offsets = new Map();
  function center(object) {
    const box = offsets.get(object.toString());
    if (!box) return;
    const node = getBanner(object);
    if (node.isNull()) return;
    const x = getX(node), y = getY(node);
    if (box.adjusted && Math.abs(x - box.adjusted.x) < 0.01 && Math.abs(y - box.adjusted.y) < 0.01) return;
    const point = anchor(node);
    box.adjusted = {x: x + (0.5 - point.readFloat()) * box.dx,
                    y: y + (0.5 - point.add(4).readFloat()) * box.dy};
    setX(node, box.adjusted.x);
    setY(node, box.adjusted.y);
  }
  const art = nativeArtCenter(module, note);
  if (art) retained.push(art);
  const forget = art ? object => art.remove(object) : object => offsets.delete(object.toString());
  const place = art ? object => art.center(object) : center;
  retained.push(Interceptor.attach(module.getExportByName('_ZN18GachaDetailScrlObj9addObjectEiff'), {
    onEnter(args) {
      this.previous = currentObject;
      this.object = currentObject = args[0];
      forget(this.object);
    },
    onLeave() { place(this.object); currentObject = this.previous; }
  }));
  if (art) {
    retained.push(Interceptor.attach(module.getExportByName('_ZN18GachaDetailScrlObj14updatePositionEff'),
      {onEnter: art.code.onEnter, onLeave: art.code.onLeave}));
    retained.push(Interceptor.attach(module.getExportByName('_ZN18GachaDetailScrlObjD1Ev'),
      {onEnter: art.code.onDestroy}));
  } else {
    retained.push(Interceptor.attach(module.getExportByName('_ZN18GachaDetailScrlObj14updatePositionEff'), {
      onEnter(args) { this.object = args[0]; },
      onLeave() { center(this.object); }
    }));
    retained.push(Interceptor.attach(module.getExportByName('_ZN18GachaDetailScrlObjD1Ev'), {
      onEnter(args) { offsets.delete(args[0].toString()); }
    }));
  }
  retained.push(Interceptor.attach(module.getExportByName(
    '_ZN21GachaBannerDownloader12createBannerERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEERKN7cocos2d4SizeE'), {
    onEnter(args) {
      const flags = args[0].readU8();
      const length = flags & 1 ? args[0].add(8).readU64().toNumber() : flags >>> 1;
      if (length > 1024) return;
      let path = (flags & 1 ? args[0].add(16).readPointer() : args[0].add(1)).readUtf8String(length);
      let name = path.split(/[\\/]/).pop(), size = artwork.images[name];
      if (!size) return;
      let width = args[1].readFloat(), height = args[1].add(4).readFloat();
      if (width <= 0 || height <= 0) {
        if (size[0] <= 640) return;
        width = 640; height = size[1] * width / size[0];
      }
      const alternative = artwork.wide[name];
      if (width / height >= 2.8 && alternative) {
        const target = bridge('materializedPath', '(Ljava/lang/String;)Ljava/lang/String;',
          ['/en/sd/static_banner/gacha/sub/' + alternative]);
        if (target) {
          this.path = Memory.alloc(24);
          makeString(this.path, Memory.allocUtf8String(target));
          args[0] = this.path;
          name = alternative; size = artwork.images[name];
        }
      }
      const fitted = fitSummonArt(size[0], size[1], width, height);
      if (!fitted) return;
      this.size = Memory.alloc(8);
      this.size.writeFloat(fitted.width); this.size.add(4).writeFloat(fitted.height);
      args[1] = this.size;
      if (currentObject) {
        if (art) art.set(currentObject, width - fitted.width, height - fitted.height);
        else offsets.set(currentObject.toString(), {dx: width - fitted.width, dy: height - fitted.height});
      }
      if (reports++ < 16) note('SUMMON_ART_FIT file=' + name + ' source=' + size.join('x') +
        ' display=' + fitted.width.toFixed(1) + 'x' + fitted.height.toFixed(1));
    },
    onLeave() { if (this.path) freeString(this.path); }
  }));
}
