(async function () {
  const ids = __MATCH_IDS__;
  const result = { screens: [], browserErrors: [] };
  window.addEventListener("error", function (event) { result.browserErrors.push(event.message); });
  window.addEventListener("unhandledrejection", function (event) { result.browserErrors.push(String(event.reason)); });
  function assert(value, message) { if (!value) throw new Error(message); }
  async function wait(test, label) {
    for (let index = 0; index < 150; index++) {
      if (test()) return;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error("Timed out: " + label);
  }
  function click(selector) {
    const element = document.querySelector(selector);
    assert(element, "Missing control: " + selector);
    element.click();
  }
  function screen(name) {
    click('[data-action="navigate"][data-screen="' + name + '"]');
    result.screens.push(name);
  }
  async function match(id) {
    screen("matches");
    click('[data-action="view-match"][data-id="' + id + '"]');
    await wait(() => document.querySelector(".scoreboard"), "match details " + id);
  }
  try {
    screen("dashboard");
    await wait(() => document.body.innerText.includes("110"), "saved data loaded");
    assert(typeof Chart === "function", "Bundled chart library");
    assert(window.lucide, "Bundled icon library");
    screen("matches");
    assert(document.querySelectorAll("tbody tr").length === 110, "Default completed results");
    const status = document.getElementById("status-select");
    status.value = "scheduled";
    status.dispatchEvent(new Event("change", { bubbles: true }));
    assert(document.querySelectorAll("tbody tr").length === 270, "Future fixture filter");
    screen("dashboard");
    assert(document.querySelector(".stat-card strong").textContent === "110", "Home totals independent of future filter");
    screen("matches");
    const reset = document.getElementById("status-select");
    reset.value = "finished";
    reset.dispatchEvent(new Event("change", { bubbles: true }));
    await match(ids.Internazionale);
    result.inter = Array.from(document.querySelectorAll(".comparison-row")).map(e => e.innerText);
    assert(result.inter.join(" ").includes("43%"), "Inter saved possession");
    assert(!document.querySelector(".comparison-row").parentElement.innerText.includes("Total Shots"), "Missing total shots hidden");
    await match(ids.Genoa);
    assert(document.body.innerText.includes("No statistics saved yet"), "Genoa honest empty state");
    click('[data-tab="events"]');
    assert(document.body.innerText.includes("Events not available"), "Event empty state");
    await match(ids.Fiorentina);
    click('[data-tab="lineups"]');
    await wait(() => document.querySelector(".lineup-list li"), "saved starting XIs");
    assert(document.querySelectorAll(".lineup-list li").length === 22, "Both real starting XIs");
    click('[data-action="open-pitch"]');
    assert(document.querySelectorAll(".pitch-player").length === 22, "Both pitch formations");
    click('[data-action="select-player"]');
    assert(document.querySelector(".player-stat-list"), "Player selection and performance");
    assert(document.querySelectorAll(".substitute-player").length > 0, "Saved substitutes");
    result.playerName = document.querySelector(".player-detail h3").textContent;
    result.playerFields = document.querySelector(".player-stat-list").innerText;
    assert(document.querySelectorAll(".rating-indicator").length > 0, "Saved ratings on pitch");
    screen("teams");
    let team = document.getElementById("team-choice");
    assert(team.options.length === 20, "All 20 teams available");
    const names = Array.from(team.options).map(option => option.value);
    names.forEach(function (name) {
      team = document.getElementById("team-choice");
      team.value = name;
      team.dispatchEvent(new Event("change", { bubbles: true }));
      assert(document.querySelector(".team-stat-grid .stat-card strong").textContent === "11", name + " played count");
      assert(document.querySelector("#team-chart"), name + " result chart");
    });
    team = document.getElementById("team-choice");
    team.value = "FC Internazionale Milano";
    team.dispatchEvent(new Event("change", { bubbles: true }));
    assert(document.querySelector(".number-grid").innerText.includes("43.0%"), "Inter average");
    assert(document.querySelector(".number-grid").innerText.includes("1 match"), "Advanced sample size");
    click('[data-metric="possession"]');
    const chart = Chart.getChart("team-chart");
    assert(chart.data.datasets[0].data.filter(value => value != null).length === 1, "Missing chart values are gaps");
    screen("statistics");
    assert(document.querySelectorAll("tbody tr").length === 20, "Official standings table");
    screen("saved");
    screen("about");
    assert(document.body.innerText.includes("Highlightly"), "Correct provider description");
    screen("dashboard");
    document.getElementById("highlightly-max-matches").value = "4";
    document.getElementById("highlightly-max-requests").value = "11";
    click('[data-action="sync-highlightly"]');
    await wait(() => document.querySelector(".approval-panel"), "read-only request proposal");
    assert(document.querySelector(".approval-panel").innerText.includes("11"), "Budget preserved in approval");
    click('[data-action="cancel-request"]');
    assert(!document.querySelector(".approval-panel"), "Inline cancellation");
    assert(result.browserErrors.length === 0, "Browser errors: " + result.browserErrors.join("; "));
    result.viewport = { width: window.innerWidth, height: window.innerHeight };
    result.success = true;
  } catch (error) { result.error = error.message; }
  const output = document.createElement("pre");
  output.id = "acceptance-result";
  output.textContent = JSON.stringify(result);
  document.body.appendChild(output);
}());
