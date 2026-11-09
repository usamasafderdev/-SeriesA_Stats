const assert = require("node:assert/strict");
const test = require("node:test");
const { formations, getFormationPositions } = require("./formation-layout.js");
const { getFormationLayout, getPitchPositions } = require("./formation-layout.js");

test("supported formations return eleven in-bounds approximate positions", () => {
  for (const formation of Object.keys(formations)) {
    const home = getFormationPositions(formation, "home");
    const away = getFormationPositions(formation, "away");

    assert.equal(home.length, 11, formation);
    assert.equal(away.length, 11, formation);
    for (const position of home.concat(away)) {
      assert.ok(position.left >= 8 && position.left <= 92, formation);
      assert.ok(position.top >= 13 && position.top <= 87, formation);
      assert.ok(position.role, formation);
    }
    assert.equal(home[0].left, 8, formation);
    assert.equal(away[0].left, 92, formation);
  }
});

test("unknown formations use a safe 4-3-3 layout", () => {
  assert.deepEqual(
    getFormationPositions("unknown", "home"),
    getFormationPositions("4-3-3", "home"),
  );
});

test("pitch supports supplied formations and omits unknown layouts", () => {
  assert.equal(getFormationLayout("4-4-1-1").roles.length, 11);
  assert.equal(getPitchPositions("4-4-1-1").length, 11);
  assert.deepEqual(getPitchPositions(null), []);
  assert.deepEqual(getPitchPositions("9-9-9"), []);
  for (const formation of Object.keys(formations)) {
    const positions = getPitchPositions(formation);
    assert.equal(positions.length, 11);
    assert.equal(new Set(positions.map(p => p.left + "," + p.top)).size, 11);
    assert.ok(positions.every(p => p.left >= 12 && p.left <= 88 && p.top >= 12 && p.top <= 88));
  }
});
