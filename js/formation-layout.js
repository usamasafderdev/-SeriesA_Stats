(function (root) {
  const formations = {
    "4-3-3": { rows: [1, 4, 3, 3], roles: ["GK", "LB", "CB", "CB", "RB", "CM", "DM", "CM", "LW", "ST", "RW"] },
    "4-4-2": { rows: [1, 4, 4, 2], roles: ["GK", "LB", "CB", "CB", "RB", "LM", "CM", "CM", "RM", "ST", "ST"] },
    "3-5-2": { rows: [1, 3, 5, 2], roles: ["GK", "CB", "CB", "CB", "LWB", "CM", "DM", "CM", "RWB", "ST", "ST"] },
    "4-2-3-1": { rows: [1, 4, 2, 3, 1], roles: ["GK", "LB", "CB", "CB", "RB", "DM", "DM", "LW", "AM", "RW", "ST"] },
    "3-4-1-2": { rows: [1, 3, 4, 1, 2], roles: ["GK", "CB", "CB", "CB", "LWB", "CM", "CM", "RWB", "AM", "ST", "ST"] },
    "3-4-2-1": { rows: [1, 3, 4, 2, 1], roles: ["GK", "CB", "CB", "CB", "LWB", "CM", "CM", "RWB", "AM", "AM", "ST"] }
  };

  function getFormationPositions(formation, side) {
    const layout = getFormationLayout(formation) || formations["4-3-3"];
    const positions = [];
    let playerIndex = 0;

    // Spread each formation line evenly across the field and the pitch depth.
    layout.rows.forEach(function (playerCount, rowIndex) {
      for (let playerInRow = 0; playerInRow < playerCount; playerInRow++) {
        const depth = 8 + rowIndex * (84 / (layout.rows.length - 1));
        const top = playerCount === 1
          ? 50
          : 13 + playerInRow * (74 / (playerCount - 1));
        positions.push({
          left: side === "away" ? 100 - depth : depth,
          top: top,
          role: layout.roles[playerIndex]
        });
        playerIndex += 1;
      }
    });

    return positions;
  }

  function getFormationLayout(formation) {
    if (formations[formation]) return formations[formation];
    if (!/^\d(?:-\d){1,4}$/.test(formation || "")) return null;
    const lines = formation.split("-").map(Number);
    if (lines.some(function (count) { return count < 1 || count > 5; }) ||
        lines.reduce(function (sum, count) { return sum + count; }, 0) !== 10) return null;
    const roles = ["GK"];
    lines.forEach(function (count, index) {
      for (let n = 0; n < count; n++) roles.push(index === 0 ? "Defender" : index === lines.length - 1 ? "Forward" : "Midfielder");
    });
    return { rows: [1].concat(lines), roles: roles };
  }

  function getPitchPositions(formation) {
    const layout = getFormationLayout(formation);
    if (!layout) return [];
    const positions = [];
    layout.rows.forEach(function (count, row) {
      for (let index = 0; index < count; index++) {
        positions.push({ left: count === 1 ? 50 : 12 + index * 76 / (count - 1),
          top: 88 - row * 76 / (layout.rows.length - 1), role: layout.roles[positions.length] });
      }
    });
    return positions;
  }

  const formationTools = {
    formations: formations,
    getFormationLayout: getFormationLayout,
    getPitchPositions: getPitchPositions,
    getFormationPositions: getFormationPositions
  };
  root.SERIE_A_FORMATIONS = formationTools;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = formationTools;
  }
}(typeof window !== "undefined" ? window : globalThis));
