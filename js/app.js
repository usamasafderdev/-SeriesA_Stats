(function () {
  const data = window.DEMO_DATA;
  const app = document.getElementById("app");
  const state = {
    screen: "landing",
    matchId: "m1",
    season: data.seasons[0],
    round: "all",
    search: "",
    team: "Inter",
    chartMetric: "points",
    detailTab: "overview",
    savedIds: ["m1", "m2", "m3"],
    chart: null
  };
  const navItems = [
    ["dashboard", "Home", "house"],
    ["matches", "Matches", "calendar-days"],
    ["teams", "Teams", "shield"],
    ["statistics", "Statistics", "chart-no-axes-column-increasing"],
    ["saved", "Saved Matches", "bookmark"],
    ["about", "About", "circle-help"]
  ];

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function icon(name, size) {
    return '<i data-lucide="' + name + '" width="' + (size || 17) + '" height="' + (size || 17) + '"></i>';
  }

  function teamInfo(name) {
    return data.teams.find(function (team) { return team.name === name; }) || data.teams[0];
  }

  function badge(name, large) {
    const team = teamInfo(name);
    return '<span class="team-badge' + (large ? " team-badge-lg" : "") + '" style="--team:' + team.color + ';--team-accent:' + team.accent + '" aria-label="' + escapeHtml(name) + '">' + escapeHtml(team.short) + '</span>';
  }

  function match(id) {
    return data.matches.find(function (item) { return item.id === id; }) || data.matches[0];
  }

  function dateLabel(matchItem) {
    return '<span class="date-cell">' + escapeHtml(matchItem.date) + '</span>';
  }

  function seasonSelect(id, className) {
    return '<label class="sr-only" for="' + id + '">Season</label><select class="' + (className || "select") + '" id="' + id + '" data-change="season">' +
      data.seasons.map(function (season) {
        return '<option value="' + season + '"' + (state.season === season ? " selected" : "") + '>Season: ' + season + '</option>';
      }).join("") + '</select>';
  }

  function shell(content) {
    const active = state.screen;
    return '<div class="app-shell">' +
      '<aside class="sidebar"><a class="brand-lockup" href="#" data-action="navigate" data-screen="dashboard"><img src="assets/logo.svg" alt="" class="brand-logo"><span><strong>Serie A</strong><small>Match Tracker</small></span></a>' +
      '<nav class="side-nav" aria-label="Main navigation">' + navItems.map(function (item) {
        return '<button class="nav-link' + (active === item[0] || (active === "match" && item[0] === "matches") ? " active" : "") + '" data-action="navigate" data-screen="' + item[0] + '">' + icon(item[2]) + '<span>' + item[1] + '</span></button>';
      }).join("") + '</nav><div class="sidebar-foot"><span class="status-dot"></span> Preview workspace</div></aside>' +
      '<main class="main-content"><div class="demo-banner">' + icon("flask-conical", 14) + '<span>' + data.label + '</span><span class="banner-note">Fictional values for preview only</span></div>' +
      '<header class="topbar"><div class="topbar-copy"><div class="eyebrow">SERIE A · MATCH CENTER</div><h1>' + screenTitle() + '</h1></div><div class="topbar-actions">' + seasonSelect("season-top", "select season-select") + '<span class="italy-mark" title="Italian-inspired color accent"><i></i><i></i><i></i></span><button class="mobile-menu icon-button" data-action="menu" aria-label="Toggle navigation">' + icon("menu") + '</button></div></header>' +
      '<section class="page-content">' + content + '</section><footer class="page-footer">Independent UI concept · Not affiliated with any league or club</footer></main></div>';
  }

  function screenTitle() {
    const titles = { dashboard: "Welcome to Serie A Tracker", match: "Match Statistics", matches: "Serie A Matches", teams: "Team Statistics", statistics: "League Statistics", saved: "Saved Matches", about: "About this preview" };
    return titles[state.screen] || "Welcome";
  }

  function landing() {
    return '<main class="landing"><div class="landing-scrim"></div><header class="landing-top"><a href="#" class="landing-brand" data-action="navigate" data-screen="dashboard"><img src="assets/logo.svg" alt="Original Serie A Tracker mark"><span>TRACKER<br><b>PREVIEW</b></span></a><span class="landing-demo">' + data.label + '</span></header>' +
      '<div class="landing-content"><div class="hero-logo"><img src="assets/logo.svg" alt="Original geometric football tracker logo"></div><p class="eyebrow hero-eyebrow">THE MATCH CENTER CONCEPT</p><h1>Serie A Match Statistics</h1><p class="hero-intro">Track goals, assists, possession and shots<br>for every sample match.</p><button class="button button-primary hero-button" data-action="navigate" data-screen="dashboard">Get Started <span>→</span></button>' +
      '<div class="feature-row"><div class="feature">' + icon("goal", 23) + '<span>Goals &amp; Assists</span></div><div class="feature">' + icon("chart-no-axes-column-increasing", 23) + '<span>Match Statistics</span></div><div class="feature">' + icon("database", 23) + '<span>Match Records</span></div><div class="feature">' + icon("trending-up", 23) + '<span>Team Analysis</span></div></div></div>' +
      '<div class="landing-bottom"><span>BUILT FOR THE BEAUTIFUL GAME</span><span>UI DEMONSTRATION · FICTIONAL DATA</span></div></main>';
  }

  function statCard(label, value, note, iconName, tone) {
    return '<article class="stat-card ' + tone + '"><div class="stat-card-icon">' + icon(iconName, 21) + '</div><div class="stat-card-copy"><span>' + label + '</span><strong>' + value + '</strong><small>' + note + '</small></div></article>';
  }

  function dashboard() {
    const goals = data.matches.reduce(function (sum, item) { return sum + item.score[0] + item.score[1]; }, 0);
    const avgPossession = (data.teams.reduce(function (sum, team) { return sum + team.possession; }, 0) / data.teams.length).toFixed(1);
    const rows = data.matches.slice(0, 3).map(function (item) {
      return '<tr><td>' + escapeHtml(item.home) + '</td><td>' + badge(item.home) + '</td><td><strong class="score">' + item.score.join(" – ") + '</strong></td><td>' + badge(item.away) + '</td><td>' + escapeHtml(item.away) + '</td><td>' + dateLabel(item) + '</td><td><button class="table-icon" title="' + (state.savedIds.includes(item.id) ? "Remove saved match" : "Save match") + '" data-action="toggle-save" data-id="' + item.id + '">' + icon(state.savedIds.includes(item.id) ? "bookmark-check" : "bookmark", 15) + '</button></td></tr>';
    }).join("");
    return '<div class="welcome-row"><div><p class="section-kicker">YOUR SEASON AT A GLANCE</p><p class="muted">Explore sample match results, team performance and detailed insights.</p></div><button class="button button-secondary" data-action="navigate" data-screen="matches">Browse matches ' + icon("arrow-up-right", 15) + '</button></div>' +
      '<div class="stats-grid">' + statCard("Sample Matches", data.matches.length, "Across 2 demo seasons", "goal", "cyan") + statCard("Sample Goals", goals, "Fictional match events", "trophy", "blue") + statCard("Teams", data.teams.length, "Illustrative team set", "users-round", "indigo") + statCard("Avg. Possession", avgPossession + "%", "Sample team average", "chart-no-axes-column-increasing", "violet") + '</div>' +
      '<section class="panel table-panel"><div class="panel-heading"><div><h2>Recent Matches</h2><p>Latest fixtures in the demo dataset</p></div><button class="text-button" data-action="navigate" data-screen="matches">View all ' + icon("arrow-right", 14) + '</button></div>' +
      '<div class="table-wrap"><table><thead><tr><th>Home Team</th><th></th><th>Score</th><th></th><th>Away Team</th><th>Date</th><th></th></tr></thead><tbody>' + rows + '</tbody></table></div></section>' +
      '<div class="bottom-cards"><article class="panel insight-card"><span class="insight-icon">' + icon("sparkles", 18) + '</span><div><h3>Made for matchday</h3><p>Compare every sample score, event and team performance in one place.</p></div></article><article class="panel insight-card"><span class="insight-icon green">' + icon("shield-check", 18) + '</span><div><h3>Preview, not a live feed</h3><p>All results and player events are fictional sample values.</p></div></article></div>';
  }

  function matchesScreen() {
    const rounds = Array.from(new Set(data.matches.filter(function (item) { return item.season === state.season; }).map(function (item) { return item.round; }))).sort(function (a, b) { return b - a; });
    const list = data.matches.filter(function (item) {
      return item.season === state.season && (state.round === "all" || String(item.round) === state.round) &&
        (item.home + " " + item.away).toLowerCase().includes(state.search.toLowerCase());
    });
    const rows = list.map(function (item) {
      return '<tr><td>' + dateLabel(item) + '<small class="sub-cell">Round ' + item.round + '</small></td><td><span class="team-name-cell">' + badge(item.home) + '<b>' + escapeHtml(item.home) + '</b></span></td><td><strong class="score">' + item.score.join(" – ") + '</strong></td><td><span class="team-name-cell">' + badge(item.away) + '<b>' + escapeHtml(item.away) + '</b></span></td><td><div class="row-actions"><button class="table-action" data-action="view-match" data-id="' + item.id + '">View ' + icon("arrow-right", 13) + '</button><button class="table-icon" aria-label="Toggle saved match" data-action="toggle-save" data-id="' + item.id + '">' + icon(state.savedIds.includes(item.id) ? "bookmark-check" : "bookmark", 15) + '</button></div></td></tr>';
    }).join("");
    return '<div class="filter-bar panel"><label class="select-wrap">' + icon("calendar-days", 15) + '<span class="sr-only">Season</span><select class="select" data-change="season">' + data.seasons.map(function (season) { return '<option value="' + season + '"' + (state.season === season ? " selected" : "") + '>Season: ' + season + '</option>'; }).join("") + '</select></label>' +
      '<label class="select-wrap">' + icon("list-filter", 15) + '<span class="sr-only">Round</span><select class="select" data-change="round"><option value="all">Round: All</option>' + rounds.map(function (round) { return '<option value="' + round + '"' + (state.round === String(round) ? " selected" : "") + '>Round: ' + round + '</option>'; }).join("") + '</select></label>' +
      '<label class="search-wrap">' + icon("search", 16) + '<span class="sr-only">Search teams</span><input type="search" data-input="search" value="' + escapeHtml(state.search) + '" placeholder="Search by team..."></label></div>' +
      '<section class="panel table-panel matches-table-panel"><div class="panel-heading"><div><h2>Fixtures</h2><p>' + list.length + ' fictional matches · Season ' + state.season + '</p></div><span class="result-count">' + list.length + ' RESULTS</span></div><div class="table-wrap"><table><thead><tr><th>Date / Round</th><th>Home Team</th><th>Score</th><th>Away Team</th><th>Actions</th></tr></thead><tbody>' + (rows || '<tr><td class="empty-state" colspan="5">No sample fixtures match these filters.</td></tr>') + '</tbody></table></div></section>';
  }

  function comparisonBar(label, left, right, unit) {
    const total = left + right || 1;
    return '<div class="comparison-row"><div class="compare-values"><b>' + left + (unit || "") + '</b><span>' + label + '</span><b>' + right + (unit || "") + '</b></div><div class="compare-track"><span class="home-fill" style="width:' + (left / total * 100) + '%"></span><span class="away-fill" style="width:' + (right / total * 100) + '%"></span></div></div>';
  }

  function detailScreen() {
    const item = match(state.matchId);
    const eventRows = item.goals.map(function (goal) {
      const home = goal.team === item.home;
      return '<div class="event-row"><span class="event-minute">' + goal.minute + '\'</span><span class="event-ball">' + icon("goal", 14) + '</span><div class="event-copy"><b>' + escapeHtml(goal.player) + '</b><small>Assist: ' + escapeHtml(goal.assist) + '</small></div>' + badge(goal.team) + '<span class="event-side">' + (home ? "Home" : "Away") + '</span></div>';
    }).join("");
    let activeContent;
    if (state.detailTab === "events") {
      activeContent = '<section class="panel detail-panel"><div class="panel-heading"><div><h2>Match Timeline</h2><p>Sample goal events · fictional player data</p></div><span class="result-count">' + item.goals.length + ' EVENTS</span></div><div class="event-list">' + eventRows + '</div></section>';
    } else if (state.detailTab === "lineups") {
      activeContent = '<div class="lineups-grid"><section class="panel detail-panel"><div class="panel-heading"><div><h2>' + escapeHtml(item.home) + '</h2><p>Sample starting XI</p></div>' + badge(item.home) + '</div><ol class="lineup-list">' + item.lineups.home.map(function (player, i) { return '<li><span>' + String(i + 1).padStart(2, "0") + '</span>' + escapeHtml(player) + '</li>'; }).join("") + '</ol></section><section class="panel detail-panel"><div class="panel-heading"><div><h2>' + escapeHtml(item.away) + '</h2><p>Sample starting XI</p></div>' + badge(item.away) + '</div><ol class="lineup-list">' + item.lineups.away.map(function (player, i) { return '<li><span>' + String(i + 1).padStart(2, "0") + '</span>' + escapeHtml(player) + '</li>'; }).join("") + '</ol></section></div>';
    } else {
      activeContent = '<div class="detail-grid"><section class="panel detail-panel"><div class="panel-heading"><div><h2>Match Stats</h2><p>Team comparison</p></div>' + icon("chart-no-axes-column-increasing", 17) + '</div>' +
        comparisonBar("Possession", item.possession[0], item.possession[1], "%") + comparisonBar("Total Shots", item.shots[0], item.shots[1]) + comparisonBar("Shots on Target", item.onTarget[0], item.onTarget[1]) + comparisonBar("Corners", item.corners[0], item.corners[1]) + comparisonBar("Fouls", item.fouls[0], item.fouls[1]) + '</section>' +
        '<section class="panel detail-panel"><div class="panel-heading"><div><h2>Goal Events</h2><p>Scorers &amp; assists</p></div>' + icon("goal", 17) + '</div><div class="event-list">' + eventRows + '</div></section></div>' +
        '<div class="bottom-cards"><article class="panel insight-card"><span class="insight-icon">' + icon("trophy", 17) + '</span><div><h3>Possession edge</h3><p>' + escapeHtml(item.possession[0] >= item.possession[1] ? item.home : item.away) + ' led possession with ' + Math.max.apply(null, item.possession) + '% in this sample fixture.</p></div></article><article class="panel insight-card"><span class="insight-icon green">' + icon("target", 18) + '</span><div><h3>Attacking output</h3><p>' + (item.shots[0] + item.shots[1]) + ' combined shots recorded in this fictional match.</p></div></article></div>';
    }
    return '<div class="match-hero panel"><div class="match-hero-top"><button class="back-button" data-action="navigate" data-screen="matches" aria-label="Back to matches">' + icon("arrow-left", 16) + '</button><span class="match-date">' + icon("calendar-days", 14) + ' ' + escapeHtml(item.date) + ' · Round ' + item.round + '</span>' + seasonSelect("season-detail", "select compact-select") + '</div>' +
      '<div class="scoreboard"><div class="score-team">' + badge(item.home, true) + '<strong>' + escapeHtml(item.home) + '</strong></div><div class="score-center"><div class="full-score">' + item.score[0] + '<span>:</span>' + item.score[1] + '</div><span class="ft-pill">FULL TIME</span></div><div class="score-team">' + badge(item.away, true) + '<strong>' + escapeHtml(item.away) + '</strong></div></div>' +
      '<div class="venue-line">' + icon("map-pin", 13) + ' ' + escapeHtml(item.venue) + '<button class="save-inline" data-action="toggle-save" data-id="' + item.id + '">' + icon(state.savedIds.includes(item.id) ? "bookmark-check" : "bookmark", 14) + (state.savedIds.includes(item.id) ? " Saved" : " Save match") + '</button></div></div>' +
      '<div class="tabs" role="tablist">' + [["overview", "Overview"], ["events", "Events"], ["lineups", "Lineups"]].map(function (tab) { return '<button class="tab' + (state.detailTab === tab[0] ? " active" : "") + '" role="tab" aria-selected="' + (state.detailTab === tab[0]) + '" data-action="detail-tab" data-tab="' + tab[0] + '">' + tab[1] + '</button>'; }).join("") + '</div>' + activeContent;
  }

  function teamSelect() {
    return '<select id="team-choice" class="select team-select" data-change="team">' + data.teams.map(function (team) { return '<option value="' + escapeHtml(team.name) + '"' + (state.team === team.name ? " selected" : "") + '>' + escapeHtml(team.name) + '</option>'; }).join("") + '</select>';
  }

  function chartTabs() {
    return [["points", "Overview"], ["goals", "Goals"], ["assists", "Assists"], ["possession", "Possession"], ["shots", "Shots"]].map(function (tab) {
      return '<button class="chart-tab' + (state.chartMetric === tab[0] ? " active" : "") + '" data-action="chart-tab" data-metric="' + tab[0] + '">' + tab[1] + '</button>';
    }).join("");
  }

  function chartPanel(title) {
    return '<section class="panel chart-panel"><div class="chart-panel-head"><div><h2>' + title + '</h2><p>' + escapeHtml(state.team) + ' · illustrative season trend</p></div><div class="chart-tabs">' + chartTabs() + '</div></div><div class="chart-canvas-wrap"><canvas id="team-chart" role="img" aria-label="' + escapeHtml(state.team) + ' sample team statistics chart"></canvas></div></section>';
  }

  function teamsScreen() {
    const team = teamInfo(state.team);
    return '<div class="team-toolbar panel"><div><label class="team-select-label" for="team-choice">Select Team</label><div class="team-picker">' + badge(team.name) + teamSelect() + '</div></div><div class="team-season">' + icon("calendar-days", 15) + ' Sample season overview</div></div>' +
      '<div class="team-stat-grid">' + statCard("Matches", team.played, "Illustrative fixtures", "goal", "cyan") + statCard("Wins", team.wins, "Sample results", "trophy", "green") + statCard("Draws", team.draws, "Sample results", "equal", "blue") + statCard("Losses", team.losses, "Sample results", "circle-x", "rose") + '</div>' +
      '<div class="team-lower"><section class="panel team-number-panel"><div class="panel-heading"><div><h2>Performance Snapshot</h2><p>Sample season totals</p></div></div><div class="number-grid"><div><span>Goals</span><b>' + team.goals + '</b></div><div><span>Assists</span><b>' + team.assists + '</b></div><div><span>Avg. Possession</span><b>' + team.possession + '%</b></div><div><span>Avg. Shots</span><b>' + team.shots + '</b></div></div></section>' + chartPanel("Team Performance") + '</div>';
  }

  function statisticsScreen() {
    const leaders = data.teams.slice().sort(function (a, b) { return b.goals - a.goals; }).slice(0, 5);
    const rows = leaders.map(function (team, index) {
      return '<tr><td><span class="rank-pill">' + (index + 1) + '</span></td><td><span class="team-name-cell">' + badge(team.name) + '<b>' + escapeHtml(team.name) + '</b></span></td><td>' + team.played + '</td><td>' + team.wins + '</td><td>' + team.goals + '</td><td>' + team.assists + '</td><td>' + team.possession + '%</td></tr>';
    }).join("");
    return '<div class="welcome-row"><div><p class="section-kicker">DEMO LEAGUE OVERVIEW</p><p class="muted">A comparison of illustrative team values—not official standings.</p></div><span class="result-count">SAMPLE VALUES</span></div><div class="stats-grid">' + statCard("Teams", data.teams.length, "In this sample dataset", "users-round", "cyan") + statCard("Fixtures", data.matches.length, "Across two sample seasons", "calendar-days", "blue") + statCard("Sample Goals", data.matches.reduce(function (sum, item) { return sum + item.score[0] + item.score[1]; }, 0), "Across listed fixtures", "goal", "indigo") + statCard("Seasons", data.seasons.length, "Fictional preview records", "clock-3", "violet") + '</div><section class="panel table-panel"><div class="panel-heading"><div><h2>Sample Team Comparison</h2><p>Ranked by illustrative goal totals</p></div></div><div class="table-wrap"><table><thead><tr><th>#</th><th>Team</th><th>Played</th><th>Wins</th><th>Goals</th><th>Assists</th><th>Possession</th></tr></thead><tbody>' + rows + '</tbody></table></div></section>';
  }

  function savedScreen() {
    const items = state.savedIds.map(match).filter(function (item) { return item.season === state.season; });
    const rows = items.map(function (item) {
      return '<tr><td>' + dateLabel(item) + '</td><td><span class="saved-match-name">' + badge(item.home) + '<span>' + escapeHtml(item.home) + ' <small>vs</small> ' + escapeHtml(item.away) + '</span>' + badge(item.away) + '</span></td><td><strong class="score">' + item.score.join(" – ") + '</strong></td><td><div class="row-actions"><button class="table-icon view-icon" title="View match" data-action="view-match" data-id="' + item.id + '">' + icon("eye", 15) + '</button><button class="table-icon remove-icon" title="Remove saved match" data-action="remove-save" data-id="' + item.id + '">' + icon("trash-2", 15) + '</button></div></td></tr>';
    }).join("");
    return '<div class="saved-layout"><section class="panel table-panel saved-table-panel"><div class="panel-heading"><div><h2>Your Collection</h2><p>' + items.length + ' saved sample matches · Season ' + state.season + '</p></div><span class="result-count">' + items.length + ' SAVED</span></div><div class="table-wrap"><table><thead><tr><th>Date</th><th>Match</th><th>Score</th><th>Actions</th></tr></thead><tbody>' + (rows || '<tr><td class="empty-state" colspan="4">No saved matches in this season. Use the bookmark button on a match to add one.</td></tr>') + '</tbody></table></div></section>' +
      '<section class="panel quick-analysis"><div class="panel-heading"><div><h2>Quick Analysis</h2><p>Saved match outcomes</p></div>' + icon("chart-pie", 17) + '</div><div class="donut-wrap"><canvas id="saved-chart" role="img" aria-label="Donut chart of saved match outcomes"></canvas><div class="donut-center"><strong>' + items.length + '</strong><span>Saved</span></div></div><div class="legend-list"><span><i class="legend-dot home-dot"></i> Home wins <b id="home-count">0%</b></span><span><i class="legend-dot draw-dot"></i> Draws <b id="draw-count">0%</b></span><span><i class="legend-dot away-dot"></i> Away wins <b id="away-count">0%</b></span></div></section></div>';
  }

  function aboutScreen() {
    return '<div class="about-hero panel"><div class="about-logo"><img src="assets/logo.svg" alt=""></div><div><p class="section-kicker">AN INTERACTIVE CLIENT PREVIEW</p><h2>A match center, imagined.</h2><p>Explore a polished, fictional Serie A-inspired match statistics interface. Every score, player event, team metric and chart shown in this preview is sample data created for demonstration.</p><span class="demo-tag">' + data.label + '</span></div></div><div class="about-grid"><article class="panel about-card"><span class="about-icon">' + icon("monitor", 19) + '</span><h3>Frontend only</h3><p>Built as a lightweight HTML, CSS and JavaScript prototype. No sign-in, server, database or live football feed.</p></article><article class="panel about-card"><span class="about-icon">' + icon("mouse-pointer-2", 19) + '</span><h3>Made to explore</h3><p>Navigate screens, filter fixtures, inspect team stats, switch charts and manage a temporary saved list.</p></article><article class="panel about-card"><span class="about-icon">' + icon("palette", 19) + '</span><h3>Original visual assets</h3><p>Includes an original geometric tracker mark and an illustrated stadium background; no official league or club logos.</p></article></div>';
  }

  function contentForScreen() {
    switch (state.screen) {
      case "dashboard": return dashboard();
      case "matches": return matchesScreen();
      case "match": return detailScreen();
      case "teams": return teamsScreen();
      case "statistics": return statisticsScreen();
      case "saved": return savedScreen();
      case "about": return aboutScreen();
      default: return dashboard();
    }
  }

  function render() {
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }
    app.innerHTML = state.screen === "landing" ? landing() : shell(contentForScreen());
    if (window.lucide) window.lucide.createIcons();
    if (state.screen === "teams") renderTeamChart();
    if (state.screen === "saved") renderSavedChart();
  }

  function metricValues(team) {
    const map = {
      points: { label: "Points", values: [38, 44, 49, 56, 60, 67, 72, 81, 84, 89, team.wins * 4 + team.draws] },
      goals: { label: "Goals", values: [3, 8, 13, 19, 25, 31, 38, 43, 49, 57, team.goals] },
      assists: { label: "Assists", values: [2, 6, 10, 15, 19, 24, 29, 34, 39, 43, team.assists] },
      possession: { label: "Possession %", values: [48, 49, 51, 52, 53, 54, 55, 55, 56, 56, team.possession] },
      shots: { label: "Avg. shots", values: [8, 9, 10, 10, 11, 12, 12, 13, 14, 14, team.shots] }
    };
    return map[state.chartMetric];
  }

  function renderTeamChart() {
    const canvas = document.getElementById("team-chart");
    if (!canvas || !window.Chart) return;
    const team = teamInfo(state.team);
    const metric = metricValues(team);
    const values = metric.values.map(function (value, index) { return index === 10 ? value : Number((value * (team.goals / 65)).toFixed(1)); });
    state.chart = new Chart(canvas, {
      type: "line",
      data: { labels: ["1", "4", "7", "10", "13", "16", "19", "22", "25", "28", "32"], datasets: [{ label: metric.label, data: values, borderColor: "#38a4ff", backgroundColor: "rgba(36, 119, 255, .18)", fill: true, tension: .38, pointRadius: 2.5, pointHoverRadius: 5, pointBackgroundColor: "#80dcff", borderWidth: 2 }] },
      options: { maintainAspectRatio: false, responsive: true, plugins: { legend: { display: false }, tooltip: { backgroundColor: "#101e36", titleColor: "#f4f8ff", bodyColor: "#bbcae0", borderColor: "rgba(139,174,225,.2)", borderWidth: 1 } }, scales: { x: { grid: { display: false }, ticks: { color: "#8999b4", maxTicksLimit: 8 } }, y: { grid: { color: "rgba(147,171,210,.09)" }, ticks: { color: "#8999b4", maxTicksLimit: 5 } } } }
    });
  }

  function renderSavedChart() {
    const canvas = document.getElementById("saved-chart");
    if (!canvas || !window.Chart) return;
    const items = state.savedIds.map(match).filter(function (item) { return item.season === state.season; });
    const result = items.reduce(function (counts, item) {
      if (item.score[0] === item.score[1]) counts[1]++;
      else if (item.score[0] > item.score[1]) counts[0]++;
      else counts[2]++;
      return counts;
    }, [0, 0, 0]);
    const percentages = result.map(function (count) { return items.length ? Math.round(count / items.length * 100) : 0; });
    document.getElementById("home-count").textContent = percentages[0] + "%";
    document.getElementById("draw-count").textContent = percentages[1] + "%";
    document.getElementById("away-count").textContent = percentages[2] + "%";
    state.chart = new Chart(canvas, {
      type: "doughnut",
      data: { labels: ["Home wins", "Draws", "Away wins"], datasets: [{ data: result, backgroundColor: ["#1683ff", "#59c8ed", "#ff5a69"], borderColor: "#0b172b", borderWidth: 4, hoverOffset: 5 }] },
      options: { maintainAspectRatio: false, cutout: "76%", plugins: { legend: { display: false }, tooltip: { backgroundColor: "#101e36", titleColor: "#f4f8ff", bodyColor: "#bbcae0", callbacks: { label: function (context) { return " " + context.label + ": " + context.raw; } } } } }
    });
  }

  function navigate(screen) {
    state.screen = screen;
    if (screen === "match") state.screen = "matches";
    render();
  }

  function toggleSaved(id, removeOnly) {
    const index = state.savedIds.indexOf(id);
    if (index >= 0) {
      state.savedIds.splice(index, 1);
    } else if (!removeOnly) {
      state.savedIds.push(id);
    }
    render();
  }

  app.addEventListener("click", function (event) {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    const action = target.dataset.action;
    if (action === "navigate") {
      event.preventDefault();
      navigate(target.dataset.screen);
    } else if (action === "view-match") {
      state.matchId = target.dataset.id;
      state.detailTab = "overview";
      state.screen = "match";
      render();
    } else if (action === "toggle-save") {
      toggleSaved(target.dataset.id, false);
    } else if (action === "remove-save") {
      toggleSaved(target.dataset.id, true);
    } else if (action === "detail-tab") {
      state.detailTab = target.dataset.tab;
      render();
    } else if (action === "chart-tab") {
      state.chartMetric = target.dataset.metric;
      render();
    } else if (action === "menu") {
      document.querySelector(".sidebar").classList.toggle("sidebar-open");
    }
  });

  app.addEventListener("change", function (event) {
    const target = event.target;
    if (target.dataset.change === "season") {
      state.season = target.value;
      if (state.round !== "all" && !data.matches.some(function (item) { return item.season === state.season && String(item.round) === state.round; })) state.round = "all";
      render();
    } else if (target.dataset.change === "round") {
      state.round = target.value;
      render();
    } else if (target.dataset.change === "team") {
      state.team = target.value;
      render();
    }
  });

  app.addEventListener("input", function (event) {
    if (event.target.dataset.input === "search") {
      const cursor = event.target.selectionStart;
      state.search = event.target.value;
      const content = document.querySelector(".page-content");
      content.innerHTML = matchesScreen();
      if (window.lucide) window.lucide.createIcons();
      const search = document.querySelector('[data-input="search"]');
      search.focus();
      search.setSelectionRange(cursor, cursor);
    }
  });

  render();
}());
