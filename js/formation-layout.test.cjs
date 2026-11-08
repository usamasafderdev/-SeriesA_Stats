const assert = require("node:assert/strict");
const test = require("node:test");
const { formations, getFormationPositions } = require("./formation-layout.js");

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
