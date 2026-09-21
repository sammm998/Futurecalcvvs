// Run with node --experimental-strip-types tools/test_live.mjs. No camera or API is used.
import assert from 'node:assert/strict';
import { HandGestures, pinchedHands, extension, withPipeExtensions } from '../src/live/gestures.ts';
const hand = (x, y = .4, pinch = true) => {
  const p = Array.from({ length: 21 }, () => ({ x, y }));
  p[0] = { x, y: y + .2 }; p[9] = { x, y };
  p[4] = { x, y }; p[8] = { x: x + (pinch ? .01 : .12), y };
  return p;
};
const g = new HandGestures();
assert.equal(g.update([hand(.5)], 100), null);
assert.ok(g.update([hand(.52)], 165).dx > 0);
assert.equal(g.update([], 230), null);
assert.equal(g.update([hand(.8)], 295), null); // reacquisition does not jump
assert.equal(g.update([hand(.8, .4, false)], 360), null);
assert.equal(g.update([hand(.3), hand(.7)], 425), null);
assert.ok(g.update([hand(.28), hand(.72)], 490).factor > 1);
assert.equal(g.update([hand(.2), hand(.8)], 1000), null); // stalled camera
g.reset(); assert.equal(g.update([hand(.9)], 1100), null);
const pipe = { page: 0, geometry: [[[0, 0], [100, 0]]] };
assert.deepEqual(extension(pipe, 0, 2, 'right', .02), { points: [[100, 0], [200, 0]], meters: 2 });
assert.deepEqual(extension(pipe, 0, 2, 'left', .02).points, [[0, 0], [-100, 0]]);
assert.throws(() => extension(pipe, 1, 2, 'right', .02));
assert.throws(() => extension(null, 0, 2, 'right', .02));
assert.throws(() => extension(pipe, 0, NaN, 'right', .02));
assert.throws(() => extension(pipe, 0, -2, 'right', .02));
assert.throws(() => extension(pipe, 0, 2, 'right', 0));
assert.throws(() => extension(pipe, 0, 2, 'down', .02)); // equal terminal heights
const chained = { ...pipe, geometry: [...pipe.geometry, [[100, 0], [200, 0]]] };
assert.deepEqual(extension(chained, 0, 2, 'right', .02).points, [[200, 0], [300, 0]]);
const dashed = { geometry: [[[0, 0], [500, 0]], [[500, 0], [100, 100]]], frontiers: [{x:0,y:0}, {x:100,y:100}] };
assert.deepEqual(extension(dashed, 0, 1, 'right', .02).points, [[100, 100], [150, 100]]);
assert.deepEqual(extension({...dashed, extensions:[[[100,100],[150,100]]]}, 0, 1, 'right', .02).points, [[150,100],[200,100]]);
const original = { pipes: [{...pipe, physical_pipe_id:'p'}], quantities:[{total_m:3}] };
const correction = {id:'c', kind:'extend', page:0, payload:{pipe_id:'p', points:[[100,0],[150,0]]}};
const changed = withPipeExtensions(original, [correction]);
assert.equal(changed.pipes[0].geometry.length, 2);
assert.equal(original.pipes[0].geometry.length, 1);
assert.deepEqual(changed.quantities, original.quantities);
assert.equal(changed.manualExtensions, 1);
assert.equal(withPipeExtensions(original, [{...correction, undone:true}]).manualExtensions, 0);
assert.equal(withPipeExtensions(original, [{...correction, page:1}]).manualExtensions, 0);
const slower = new HandGestures();
assert.equal(slower.update([hand(.5)], 100), null);
assert.ok(slower.update([hand(.53)], 300).dx > 0); // CPU inference can take 200ms
const gradual = new HandGestures();
assert.equal(gradual.update([hand(.5)], 100), null);
assert.equal(gradual.update([hand(.501)], 165), null);
assert.ok(gradual.update([hand(.5025)], 230).dx > 0); // slow drag crosses dead zone cumulatively
gradual.reset();
assert.equal(gradual.update([hand(.3),hand(.7)], 100), null);
assert.equal(gradual.update([hand(.2995),hand(.7005)], 165), null);
assert.equal(gradual.update([hand(.299),hand(.701)], 230), null);
assert.ok(gradual.update([hand(.298),hand(.702)], 295).factor > 1);
assert.ok(slower.update([hand(.55)], 650).dx > 0); // slower camera retains continuous tracking
assert.equal(pinchedHands([hand(.5, .4, false)]).length, 0);
assert.equal(pinchedHands([hand(.3), hand(.7)]).length, 2);
console.log('Gesture, extension and 3D checks passed');
