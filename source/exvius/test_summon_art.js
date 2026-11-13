const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const hooks = new Map();
const resized = [];
const widthSymbol = '_ZN10GameSprite8getWidthEv';
const heightSymbol = '_ZN10GameSprite9getHeightEv';
const sizeSymbol = '_ZN10GameSprite7setSizeEff';
const layoutSymbol = '_ZN13GachaTopScene13setListLayoutEv';
const buttonSymbol = '_ZN12SpriteButton19initForChangeSpriteEiffiP10GameSpriteS1_ib';
const source = fs.readFileSync(path.join(__dirname, 'summon_art.js'), 'utf8')
  .replace(/^import .*;\r?$/gm, '').replace(/export (function|const) /g, '$1 ');
const context = {
  artwork: JSON.parse(fs.readFileSync(path.join(__dirname, '../server/summon_art.json'), 'utf8')),
  NativeFunction: function (symbol) {
    if (symbol === widthSymbol) return node => node.width;
    if (symbol === heightSymbol) return node => node.height;
    if (symbol === sizeSymbol) return (node, width, height) => {
      resized.push([width, height]);
      Object.assign(node, {width, height});
    };
    return () => { throw new Error('Unexpected native call: ' + symbol); };
  },
  Interceptor: {attach(symbol, handlers) { hooks.set(symbol, handlers); return handlers; }}
};
vm.createContext(context);
vm.runInContext(source, context);
context.installSummonArt({getExportByName: name => name}, () => {}, [], () => {});
const layout = hooks.get(layoutSymbol), button = hooks.get(buttonSymbol);
const sprite = (width, height) => ({width, height, isNull: () => false});
const args = (normal, pressed) => [null, null, normal, pressed];

// Other menus using the same engine button must keep their original skin.
const outside = sprite(640, 160);
button.onEnter(args(sprite(640, 392), outside));
assert.equal(outside.height, 160);
assert.equal(resized.length, 0);

layout.onEnter();
const dimensions = new Set(Object.values(context.artwork.images).map(size => size.join('x')));
for (const dimension of dimensions) {
  const [width, height] = dimension.split('x').map(Number);
  const normal = sprite(width, height), pressed = sprite(640, 160);
  button.onEnter(args(normal, pressed));
  assert.deepEqual([pressed.width, pressed.height], [width, height], dimension);
  assert.deepEqual([normal.width, normal.height], [width, height], 'Artwork must stay unchanged');
  const count = resized.length;
  button.onEnter(args(normal, pressed));
  assert.equal(resized.length, count, 'Already matching overlays need no resize');
}
for (const normal of [sprite(0, 160), {isNull: () => true}]) {
  const count = resized.length;
  button.onEnter(args(normal, sprite(640, 160)));
  assert.equal(resized.length, count);
}
button.onEnter(args(sprite(640, 392), {isNull: () => true}));
layout.onEnter();
layout.onLeave();
const nested = sprite(640, 160);
button.onEnter(args(sprite(626, 186), nested));
assert.equal(nested.height, 186);
layout.onLeave();
const count = resized.length;
button.onEnter(args(sprite(640, 392), sprite(640, 160)));
assert.equal(resized.length, count, 'List scope must end normally');

for (const [width, height] of Object.values(context.artwork.images)) {
  const fit = context.fitSummonArt(width, height, 640, 392);
  assert.ok(fit.width <= 640.00001 && fit.height <= 392.00001);
  assert.ok(Math.abs(fit.width / fit.height - width / height) < 1e-9);
}
console.log('Summon banner proportions and pressed overlays passed for ' + dimensions.size + ' source sizes; other menus unchanged.');
