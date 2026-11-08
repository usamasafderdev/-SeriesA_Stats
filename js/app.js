(function () {
  const data = window.DEMO_DATA;
  const app = document.getElementById("app");
  const state = {
    screen: "landing",
    matchId: "m1",
    dataMode: "demo",
    liveSeason: "all",
    activeMatchSource: "demo",
    liveMatchDetails: null,
    liveMatchDetailsLoading: false,
    liveMatchDetailsError: "",
    liveStatsMessage: "",
    season: data.seasons[0],
    round: "all",
    search: "",
    team: "Inter",
    chartMetric: "points",
    detailTab: "overview",
    lineupSide: "both",
    activeLineupPlayer: null,
    lineupMode: "demo",
    liveMatches: [],
    liveMatchesLoaded: false,
    liveMatchesError: "",
    liveMatchId: "",
    liveLineups: null,
    liveLineupMessage: "",
    liveImportMessage: "",
    listImportSeason: "2025",
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

  function liveSeasonSelect(id, className) {
    const seasons = Array.from(new Set(state.liveMatches.map(function (item) { return item.season; }))).sort().reverse();
    const options = ['<option value="all"' + (state.liveSeason === "all" ? " selected" : "") + '>All saved seasons</option>'].concat(
      seasons.map(function (season) {
        return '<option value="' + escapeHtml(season) + '"' + (state.liveSeason === season ? " selected" : "") + '>Season: ' + escapeHtml(season) + '</option>';
      })
    );
    return '<label class="sr-only" for="' + id + '">Saved season</label><select class="' + (className || "select") + '" id="' + id + '" data-change="live-season">' + options.join("") + '</select>';
  }

  function icon(name, size) {
    return '<i data-lucide="' + name + '" width="' + (size || 17) + '" height="' + (size || 17) + '"></i>';
  }

  function teamInfo(name) {
    return data.teams.find(function (team) { return team.name === name; }) || data.teams[0];
  }

  function badge(name, large) {
    const knownTeam = data.teams.find(function (team) { return team.name === name; });
    const initials = String(name).split(/\s+/).slice(0, 2).map(function (part) { return part.charAt(0); }).join("").toUpperCase();
    const team = knownTeam || { color: "#2879d8", accent: "#e5f4ff", short: initials || "FC" };
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
    const showLiveMode = (["dashboard", "matches", "match"].includes(active) && state.dataMode === "live") ||
      (active === "lineup" && state.lineupMode === "live");
    return '<div class="app-shell">' +
      '<aside class="sidebar"><a class="brand-lockup" href="#" data-action="navigate" data-screen="dashboard"><img src="assets/logo.svg" alt="" class="brand-logo"><span><strong>Serie A</strong><small>Match Tracker</small></span></a>' +
      '<nav class="side-nav" aria-label="Main navigation">' + navItems.map(function (item) {
        return '<button class="nav-link' + (active === item[0] || ((active === "match" || active === "lineup") && item[0] === "matches") ? " active" : "") + '" data-action="navigate" data-screen="' + item[0] + '">' + icon(item[2]) + '<span>' + item[1] + '</span></button>';
      }).join("") + '</nav><div class="sidebar-foot"><span class="status-dot"></span> Preview workspace</div></aside>' +
      '<main class="main-content"><div class="demo-banner' + (showLiveMode ? ' live-banner' : '') + '">' + icon(showLiveMode ? "database" : "flask-conical", 14) + '<span>' + (showLiveMode ? "LIVE DATA MODE — LOCAL DATABASE" : data.label) + '</span><span class="banner-note">' + (showLiveMode ? "Only saved provider records · missing values stay unavailable" : "Fictional values for preview only") + '</span></div>' +
      '<header class="topbar"><div class="topbar-copy"><div class="eyebrow">SERIE A · MATCH CENTER</div><h1>' + screenTitle() + '</h1></div><div class="topbar-actions">' + ((state.dataMode === "live" && ["dashboard", "matches", "match"].includes(active)) ? liveSeasonSelect("season-top", "select season-select") : seasonSelect("season-top", "select season-select")) + '<span class="italy-mark" title="Italian-inspired color accent"><i></i><i></i><i></i></span><button class="mobile-menu icon-button" data-action="menu" aria-label="Toggle navigation">' + icon("menu") + '</button></div></header>' +
      '<section class="page-content">' + content + '</section><footer class="page-footer">Independent UI concept · Not affiliated with any league or club</footer></main></div>';
  }

  function screenTitle() {
    const titles = { dashboard: "Welcome to Serie A Tracker", match: "Match Statistics", lineup: "Player Lineup", matches: "Serie A Matches", teams: "Team Statistics", statistics: "League Statistics", saved: "Saved Matches", about: "About this preview" };
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

  function sourceModeControls() {
    return '<div class="source-mode-controls" role="group" aria-label="Match data mode">' +
      '<button class="mode-button' + (state.dataMode === "demo" ? " active" : "") + '" data-action="data-mode" data-mode="demo">Demo Mode</button>' +
      '<button class="mode-button' + (state.dataMode === "live" ? " active" : "") + '" data-action="data-mode" data-mode="live">Live Data Mode</button>' +
      '</div>';
  }

  function liveImportPanel() {
    const refreshButton = state.liveMatches.length
      ? '<button class="button button-secondary" data-action="refresh-live-matches">Refresh saved sample</button>'
      : "";
    return '<section class="panel live-lineup-panel"><div class="panel-heading"><div><h2>Import a small match sample</h2><p>Nothing imports automatically. Review current provider pricing before confirming.</p></div></div><div class="match-list-import"><label><span>Season start year (maximum 3 matches)</span><input id="live-season" value="' + escapeHtml(state.listImportSeason) + '" maxlength="20"></label><button class="button button-secondary" data-action="import-live-matches">Load saved / import</button>' + refreshButton + '<small>Credit estimate: not independently verified. Check StrikerAPI pricing first; a request is capped at 3 matches.</small></div>' + (state.liveImportMessage ? '<p class="live-status" role="status">' + escapeHtml(state.liveImportMessage) + '</p>' : '') + '</section>';
  }

  function liveMatchRows(records) {
    return records.map(function (item) {
      const score = item.home_score == null || item.away_score == null
        ? "Not available"
        : item.home_score + " – " + item.away_score;
      return '<tr><td>' + dateLabel({ date: formatMatchDate(item.match_date) }) + '</td><td><span class="team-name-cell">' + badge(item.home_team_name) + '<b>' + escapeHtml(item.home_team_name) + '</b></span></td><td><strong class="score">' + escapeHtml(score) + '</strong></td><td><span class="team-name-cell">' + badge(item.away_team_name) + '<b>' + escapeHtml(item.away_team_name) + '</b></span></td><td><div class="row-actions"><button class="table-action" data-action="view-live-match" data-id="' + item.id + '">View ' + icon("arrow-right", 13) + '</button></div></td></tr>';
    }).join("");
  }

  function formatMatchDate(value) {
    if (!value) return "Date not available";
    const dateText = String(value);
    const hasTimeZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(dateText);
    const parsedDate = new Date(hasTimeZone ? dateText : dateText + "Z");
    if (Number.isNaN(parsedDate.getTime())) return "Date not available";
    return parsedDate.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  }

  function selectedLiveMatches() {
    return state.liveMatches.filter(function (item) {
      const seasonMatches = state.liveSeason === "all" || item.season === state.liveSeason;
      const teams = (item.home_team_name + " " + item.away_team_name).toLowerCase();
      return seasonMatches && teams.includes(state.search.toLowerCase());
    });
  }

  function dashboard() {
    if (state.dataMode === "live") {
      loadLiveMatches();
      const records = selectedLiveMatches();
      const scoredMatches = records.filter(function (item) { return item.home_score != null && item.away_score != null; });
      const totalGoals = scoredMatches.reduce(function (sum, item) { return sum + item.home_score + item.away_score; }, 0);
      const teamNames = new Set();
      records.forEach(function (item) { teamNames.add(item.home_team_name); teamNames.add(item.away_team_name); });
      const rows = records.slice(0, 5).map(function (item) {
        const score = item.home_score == null || item.away_score == null ? "Not available" : item.home_score + " – " + item.away_score;
        return '<tr><td>' + escapeHtml(item.home_team_name) + '</td><td>' + badge(item.home_team_name) + '</td><td><strong class="score">' + escapeHtml(score) + '</strong></td><td>' + badge(item.away_team_name) + '</td><td>' + escapeHtml(item.away_team_name) + '</td><td>' + escapeHtml(formatMatchDate(item.match_date)) + '</td><td><button class="table-action" data-action="view-live-match" data-id="' + item.id + '">View</button></td></tr>';
      }).join("");
      const empty = state.liveMatchesError
        ? '<div class="panel empty-state live-empty" role="status">' + escapeHtml(state.liveMatchesError) + '</div>'
        : state.liveMatchesLoaded && records.length === 0
          ? '<div class="panel empty-state live-empty">No saved live matches' + (state.liveSeason !== "all" || state.search ? ' match these filters.' : ' yet. Import a small sample below to populate the local database.') + '</div>'
          : '<div class="panel empty-state live-empty">Loading saved live matches…</div>';
      return sourceModeControls() + '<div class="welcome-row"><div><p class="section-kicker">LIVE DATABASE OVERVIEW</p><p class="muted">Only saved records are shown. No fictional values are used in Live Data Mode.</p></div><button class="button button-secondary" data-action="navigate" data-screen="matches">Browse matches ' + icon("arrow-up-right", 15) + '</button></div>' +
        '<div class="stats-grid">' + statCard("Saved Matches", records.length, "Filtered local records", "database", "cyan") + statCard("Known Goals", scoredMatches.length ? totalGoals : "Not available", scoredMatches.length ? "From matches with both scores" : "Scores not available", "goal", "blue") + statCard("Teams", teamNames.size || "Not available", "In the selected records", "users-round", "indigo") + statCard("Possession", "Not available", "Not stored in match-list data", "chart-no-axes-column-increasing", "violet") + '</div>' +
        (records.length ? '<section class="panel table-panel"><div class="panel-heading"><div><h2>Recent Matches</h2><p>Latest saved live records</p></div><button class="text-button" data-action="navigate" data-screen="matches">View all ' + icon("arrow-right", 14) + '</button></div><div class="table-wrap"><table><thead><tr><th>Home Team</th><th></th><th>Score</th><th></th><th>Away Team</th><th>Date</th><th>Details</th></tr></thead><tbody>' + rows + '</tbody></table></div></section>' : empty) + liveImportPanel();
    }

    const goals = data.matches.reduce(function (sum, item) { return sum + item.score[0] + item.score[1]; }, 0);
    const avgPossession = (data.teams.reduce(function (sum, team) { return sum + team.possession; }, 0) / data.teams.length).toFixed(1);
    const rows = data.matches.slice(0, 3).map(function (item) {
      return '<tr><td>' + escapeHtml(item.home) + '</td><td>' + badge(item.home) + '</td><td><strong class="score">' + item.score.join(" – ") + '</strong></td><td>' + badge(item.away) + '</td><td>' + escapeHtml(item.away) + '</td><td>' + dateLabel(item) + '</td><td><button class="table-icon" title="' + (state.savedIds.includes(item.id) ? "Remove saved match" : "Save match") + '" data-action="toggle-save" data-id="' + item.id + '">' + icon(state.savedIds.includes(item.id) ? "bookmark-check" : "bookmark", 15) + '</button></td></tr>';
    }).join("");
    return sourceModeControls() + '<div class="welcome-row"><div><p class="section-kicker">YOUR SEASON AT A GLANCE</p><p class="muted">Explore sample match results, team performance and detailed insights.</p></div><button class="button button-secondary" data-action="navigate" data-screen="matches">Browse matches ' + icon("arrow-up-right", 15) + '</button></div>' +
      '<div class="stats-grid">' + statCard("Sample Matches", data.matches.length, "Across 2 demo seasons", "goal", "cyan") + statCard("Sample Goals", goals, "Fictional match events", "trophy", "blue") + statCard("Teams", data.teams.length, "Illustrative team set", "users-round", "indigo") + statCard("Avg. Possession", avgPossession + "%", "Sample team average", "chart-no-axes-column-increasing", "violet") + '</div>' +
      '<section class="panel table-panel"><div class="panel-heading"><div><h2>Recent Matches</h2><p>Latest fixtures in the demo dataset</p></div><button class="text-button" data-action="navigate" data-screen="matches">View all ' + icon("arrow-right", 14) + '</button></div>' +
      '<div class="table-wrap"><table><thead><tr><th>Home Team</th><th></th><th>Score</th><th></th><th>Away Team</th><th>Date</th><th></th></tr></thead><tbody>' + rows + '</tbody></table></div></section>' +
      '<div class="bottom-cards"><article class="panel insight-card"><span class="insight-icon">' + icon("sparkles", 18) + '</span><div><h3>Made for matchday</h3><p>Compare every sample score, event and team performance in one place.</p></div></article><article class="panel insight-card"><span class="insight-icon green">' + icon("shield-check", 18) + '</span><div><h3>Preview, not a live feed</h3><p>All results and player events are fictional sample values.</p></div></article></div>';
  }

  function matchesScreen() {
    if (state.dataMode === "live") {
      loadLiveMatches();
      const records = selectedLiveMatches();
      const rows = liveMatchRows(records);
      const emptyMessage = state.liveMatchesError
        ? state.liveMatchesError
        : state.liveMatchesLoaded
          ? (state.liveMatches.length ? "No saved live matches match these filters." : "No live matches have been imported yet. Import a maximum of three below. Demo records are not shown in Live Data Mode.")
          : "Loading saved live matches…";
      return sourceModeControls() + '<div class="filter-bar panel">' + liveSeasonSelect("live-season-filter", "select") +
        '<label class="search-wrap">' + icon("search", 16) + '<span class="sr-only">Search teams</span><input type="search" data-input="search" value="' + escapeHtml(state.search) + '" placeholder="Search by team..."></label></div>' +
        '<section class="panel table-panel matches-table-panel"><div class="panel-heading"><div><h2>Saved Live Fixtures</h2><p>SQLite records · Live source only</p></div><span class="result-count">' + records.length + ' RESULTS</span></div><div class="table-wrap"><table><thead><tr><th>Date</th><th>Home Team</th><th>Score</th><th>Away Team</th><th>Actions</th></tr></thead><tbody>' + (rows || '<tr><td class="empty-state" colspan="5">' + escapeHtml(emptyMessage) + '</td></tr>') + '</tbody></table></div></section>' + liveImportPanel();
    }

    const rounds = Array.from(new Set(data.matches.filter(function (item) { return item.season === state.season; }).map(function (item) { return item.round; }))).sort(function (a, b) { return b - a; });
    const list = data.matches.filter(function (item) {
      return item.season === state.season && (state.round === "all" || String(item.round) === state.round) &&
        (item.home + " " + item.away).toLowerCase().includes(state.search.toLowerCase());
    });
    const rows = list.map(function (item) {
      return '<tr><td>' + dateLabel(item) + '<small class="sub-cell">Round ' + item.round + '</small></td><td><span class="team-name-cell">' + badge(item.home) + '<b>' + escapeHtml(item.home) + '</b></span></td><td><strong class="score">' + item.score.join(" – ") + '</strong></td><td><span class="team-name-cell">' + badge(item.away) + '<b>' + escapeHtml(item.away) + '</b></span></td><td><div class="row-actions"><button class="table-action" data-action="view-match" data-id="' + item.id + '">View ' + icon("arrow-right", 13) + '</button><button class="table-icon" aria-label="Toggle saved match" data-action="toggle-save" data-id="' + item.id + '">' + icon(state.savedIds.includes(item.id) ? "bookmark-check" : "bookmark", 15) + '</button></div></td></tr>';
    }).join("");
    return sourceModeControls() + '<div class="filter-bar panel"><label class="select-wrap">' + icon("calendar-days", 15) + '<span class="sr-only">Season</span><select class="select" data-change="season">' + data.seasons.map(function (season) { return '<option value="' + season + '"' + (state.season === season ? " selected" : "") + '>Season: ' + season + '</option>'; }).join("") + '</select></label>' +
      '<label class="select-wrap">' + icon("list-filter", 15) + '<span class="sr-only">Round</span><select class="select" data-change="round"><option value="all">Round: All</option>' + rounds.map(function (round) { return '<option value="' + round + '"' + (state.round === String(round) ? " selected" : "") + '>Round: ' + round + '</option>'; }).join("") + '</select></label>' +
      '<label class="search-wrap">' + icon("search", 16) + '<span class="sr-only">Search teams</span><input type="search" data-input="search" value="' + escapeHtml(state.search) + '" placeholder="Search by team..."></label></div>' +
      '<section class="panel table-panel matches-table-panel"><div class="panel-heading"><div><h2>Fixtures</h2><p>' + list.length + ' fictional matches · Season ' + state.season + '</p></div><span class="result-count">' + list.length + ' RESULTS</span></div><div class="table-wrap"><table><thead><tr><th>Date / Round</th><th>Home Team</th><th>Score</th><th>Away Team</th><th>Actions</th></tr></thead><tbody>' + (rows || '<tr><td class="empty-state" colspan="5">No sample fixtures match these filters.</td></tr>') + '</tbody></table></div></section>';
  }

  function comparisonBar(label, left, right, unit) {
    if (left == null || right == null) {
      return '<div class="comparison-row"><div class="compare-values"><b>' + (left == null ? "Not available" : escapeHtml(left) + (unit || "")) + '</b><span>' + label + '</span><b>' + (right == null ? "Not available" : escapeHtml(right) + (unit || "")) + '</b></div><div class="metric-unavailable">One or both team values are not available.</div></div>';
    }
    const total = left + right || 1;
    return '<div class="comparison-row"><div class="compare-values"><b>' + left + (unit || "") + '</b><span>' + label + '</span><b>' + right + (unit || "") + '</b></div><div class="compare-track"><span class="home-fill" style="width:' + (left / total * 100) + '%"></span><span class="away-fill" style="width:' + (right / total * 100) + '%"></span></div></div>';
  }

  function liveDetailScreen() {
    if (state.liveMatchDetailsLoading) {
      return '<section class="panel empty-state live-empty">Loading saved match details…</section>';
    }
    if (state.liveMatchDetailsError || !state.liveMatchDetails) {
      return '<section class="panel empty-state live-empty">' + escapeHtml(state.liveMatchDetailsError || "Match details are not available.") + '<p><button class="button button-secondary" data-action="navigate" data-screen="matches">Back to live matches</button></p></section>';
    }

    const item = state.liveMatchDetails;
    const home = item.home_team.name;
    const away = item.away_team.name;
    const stats = item.statistics || {};
    function contributionPanel(title, entries, available, fieldName) {
      const rows = entries.map(function (entry) {
        return '<li><b>' + escapeHtml(entry.player_name) + '</b><span>' +
          escapeHtml(entry.team_name) + ' · ' + entry[fieldName] + '</span></li>';
      }).join("");
      const content = rows
        ? '<ul class="lineup-list">' + rows + '</ul>'
        : '<p class="muted">' + (available ? "No recorded " + title.toLowerCase() + "." : "Not available. Saved lineup data may not include player contributions.") + '</p>';
      return '<section class="panel detail-panel"><div class="panel-heading"><div><h2>' + title + '</h2><p>' + (item.contributions_source ? "Saved player data" : "No player contribution data is stored") + '</p></div>' + icon("goal", 17) + '</div>' + content + '</section>';
    }
    const contributionStats = '<div class="detail-grid">' +
      contributionPanel("Goal scorers", item.goal_scorers || [], item.goal_scorers_available, "goals") +
      contributionPanel("Assists", item.goal_assists || [], item.goal_assists_available, "assists") +
      '</div>';
    let activeContent;
    if (state.detailTab === "events") {
      activeContent = '<section class="panel detail-panel"><div class="panel-heading"><div><h2>Player Contributions</h2><p>Recorded from saved StrikerAPI lineup records; not a minute-by-minute event feed.</p></div></div><div class="detail-grid">' +
        contributionPanel("Goal scorers", item.goal_scorers || [], item.goal_scorers_available, "goals") +
        contributionPanel("Assists", item.goal_assists || [], item.goal_assists_available, "assists") +
        '</div></section>';
    } else if (state.detailTab === "lineups") {
      const savedLineups = state.liveLineups && state.liveLineups.match_id === item.id ? state.liveLineups.lineups : [];
      const lineupSummary = state.liveLineups
        ? savedLineups.map(function (lineup) {
          return '<section class="panel detail-panel"><div class="panel-heading"><div><h2>' + escapeHtml(lineup.team_name) + '</h2><p>' + escapeHtml(lineup.formation || "Formation not provided") + ' · saved lineup</p></div>' + badge(lineup.team_name) + '</div><ol class="lineup-list">' + lineup.starting_players.map(function (player) {
            return '<li><span>' + escapeHtml(player.shirt_number == null ? "—" : player.shirt_number) + '</span>' + escapeHtml(player.name) + '</li>';
          }).join("") + '</ol></section>';
        }).join("")
        : '<section class="panel detail-panel empty-state live-empty">Saved lineup data has not been checked yet. Open the pitch view to load the local lineup records.</section>';
      activeContent = '<div class="lineups-grid">' + lineupSummary + '<div class="lineup-open-row"><p>Only saved player data is shown. Importing missing lineups requires a separate confirmation.</p><button class="button button-primary" data-action="open-lineup">Open full pitch view ' + icon("arrow-up-right", 14) + '</button></div></div>';
    } else {
      const sourceLabel = item.statistics_source === "bigballsdata"
        ? "BigBallsData · stored match statistics"
        : "Statistics have not been imported";
      const statisticsButton = '<div class="statistics-import-row"><div><p>' + sourceLabel + '</p>' +
        (state.liveStatsMessage ? '<small>' + escapeHtml(state.liveStatsMessage) + '</small>' : '') +
        '</div><button class="button button-secondary" data-action="' +
        (item.statistics_source === "bigballsdata" ? "refresh-live-statistics" : "import-live-statistics") +
        '">' + (item.statistics_source === "bigballsdata" ? "Refresh statistics" : "Import match statistics") + '</button></div>';
      activeContent = '<div class="detail-grid"><section class="panel detail-panel"><div class="panel-heading"><div><h2>Match Statistics</h2><p>Missing provider values remain unavailable.</p></div>' + icon("chart-no-axes-column-increasing", 17) + '</div>' +
        comparisonBar("Possession", stats.home_possession, stats.away_possession, "%") + comparisonBar("Total Shots", stats.home_shots, stats.away_shots) + comparisonBar("Shots on Target", stats.home_shots_on_target, stats.away_shots_on_target) + statisticsButton + '</section>' +
        '<section class="panel detail-panel"><div class="panel-heading"><div><h2>Goal Contributions</h2><p>From saved player lineup data when available</p></div>' + icon("goal", 17) + '</div>' + contributionStats + '</section></div>';
    }
    const score = item.home_score == null || item.away_score == null
      ? "Not available"
      : item.home_score + '<span>:</span>' + item.away_score;
    return '<div class="match-hero panel"><div class="match-hero-top"><button class="back-button" data-action="navigate" data-screen="matches" aria-label="Back to matches">' + icon("arrow-left", 16) + '</button><span class="match-date">' + icon("calendar-days", 14) + ' ' + escapeHtml(formatMatchDate(item.match_date)) + ' · LIVE DATABASE RECORD</span></div>' +
      '<div class="scoreboard"><div class="score-team">' + badge(home, true) + '<strong>' + escapeHtml(home) + '</strong></div><div class="score-center"><div class="full-score">' + score + '</div><span class="ft-pill">' + escapeHtml(item.status || "Status not available") + '</span></div><div class="score-team">' + badge(away, true) + '<strong>' + escapeHtml(away) + '</strong></div></div>' +
      '<div class="venue-line">Season ' + escapeHtml(item.season) + '<button class="save-inline" data-action="open-lineup">' + icon("users-round", 14) + ' Saved lineups</button></div></div>' +
      '<div class="tabs" role="tablist">' + [["overview", "Overview"], ["events", "Events"], ["lineups", "Lineups"]].map(function (tab) { return '<button class="tab' + (state.detailTab === tab[0] ? " active" : "") + '" role="tab" aria-selected="' + (state.detailTab === tab[0]) + '" data-action="detail-tab" data-tab="' + tab[0] + '">' + tab[1] + '</button>'; }).join("") + '</div>' + activeContent;
  }

  function detailScreen() {
    if (state.dataMode === "live" && state.activeMatchSource === "live") return liveDetailScreen();
    const item = match(state.matchId);
    const eventRows = item.goals.map(function (goal) {
      const home = goal.team === item.home;
      return '<div class="event-row"><span class="event-minute">' + goal.minute + '\'</span><span class="event-ball">' + icon("goal", 14) + '</span><div class="event-copy"><b>' + escapeHtml(goal.player) + '</b><small>Assist: ' + escapeHtml(goal.assist) + '</small></div>' + badge(goal.team) + '<span class="event-side">' + (home ? "Home" : "Away") + '</span></div>';
    }).join("");
    let activeContent;
    if (state.detailTab === "events") {
      activeContent = '<section class="panel detail-panel"><div class="panel-heading"><div><h2>Match Timeline</h2><p>Sample goal events · fictional player data</p></div><span class="result-count">' + item.goals.length + ' EVENTS</span></div><div class="event-list">' + eventRows + '</div></section>';
    } else if (state.detailTab === "lineups") {
      activeContent = '<div class="lineups-grid"><section class="panel detail-panel"><div class="panel-heading"><div><h2>' + escapeHtml(item.home) + '</h2><p>DEMO starting players · sample values</p></div>' + badge(item.home) + '</div><ol class="lineup-list">' + demoPitchLineup(item, "home").players.map(function (player) { return '<li><span>' + String(player.number).padStart(2, "0") + '</span>' + escapeHtml(player.name) + '</li>'; }).join("") + '</ol></section><section class="panel detail-panel"><div class="panel-heading"><div><h2>' + escapeHtml(item.away) + '</h2><p>DEMO starting players · sample values</p></div>' + badge(item.away) + '</div><ol class="lineup-list">' + demoPitchLineup(item, "away").players.map(function (player) { return '<li><span>' + String(player.number).padStart(2, "0") + '</span>' + escapeHtml(player.name) + '</li>'; }).join("") + '</ol></section><div class="lineup-open-row"><p>Approximate formation slots are for display only; no provider pitch coordinates are available in this demo.</p><button class="button button-primary" data-action="open-lineup">Open full pitch view ' + icon("arrow-up-right", 14) + '</button></div></div>';
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
    return '<div class="about-hero panel"><div class="about-logo"><img src="assets/logo.svg" alt=""></div><div><p class="section-kicker">AN INTERACTIVE CLIENT PREVIEW</p><h2>A match center, imagined.</h2><p>Explore a polished, fictional Serie A-inspired match statistics interface. Every score, player event, team metric and chart shown in this preview is sample data created for demonstration.</p><span class="demo-tag">' + data.label + '</span></div></div><div class="about-grid"><article class="panel about-card"><span class="about-icon">' + icon("database", 19) + '</span><h3>Local data foundation</h3><p>FastAPI and SQLite store explicitly imported matches and lineups. No sign-in is implemented, and API requests require a user-confirmed import.</p></article><article class="panel about-card"><span class="about-icon">' + icon("mouse-pointer-2", 19) + '</span><h3>Made to explore</h3><p>Navigate screens, filter fixtures, inspect team stats, switch charts and manage a temporary saved list.</p></article><article class="panel about-card"><span class="about-icon">' + icon("palette", 19) + '</span><h3>Original visual assets</h3><p>Includes an original geometric tracker mark and an illustrated stadium background; no official league or club logos.</p></article></div>';
  }

  function contentForScreen() {
    switch (state.screen) {
      case "dashboard": return dashboard();
      case "matches": return matchesScreen();
      case "match": return detailScreen();
      case "lineup": return lineupScreen();
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

  const formationLayouts = window.SERIE_A_FORMATIONS.formations;
  const demoFormations = Object.keys(formationLayouts);

  function loadLiveMatches() {
    if (state.liveMatchesLoaded) return;
    state.liveMatchesLoaded = true;
    state.liveMatchesError = "";
    if (window.location.protocol === "file:") {
      state.liveMatchesError = "Live database matches are available when this preview is served by the Python app.";
      return;
    }
    fetch("/api/matches?source=live").then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) throw new Error(body.detail || "Could not load stored live matches.");
        return body;
      });
    }).then(function (matches) {
      if (!Array.isArray(matches)) throw new Error("The live match response was not a list.");
      state.liveMatches = matches;
      state.liveMatchesError = "";
      if (state.liveSeason !== "all" && !matches.some(function (item) { return item.season === state.liveSeason; })) {
        state.liveSeason = "all";
      }
      render();
    }).catch(function (error) {
      state.liveMatchesError = error.message || "Could not load saved live matches.";
      render();
    });
  }

  function openLiveMatch(matchId) {
    state.dataMode = "live";
    state.activeMatchSource = "live";
    state.liveMatchDetails = null;
    state.liveMatchDetailsLoading = true;
    state.liveMatchDetailsError = "";
    state.liveStatsMessage = "";
    state.detailTab = "overview";
    state.screen = "match";
    render();
    fetch("/api/matches/" + encodeURIComponent(matchId)).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) throw new Error(body.detail || "Could not load saved match details.");
        return body;
      });
    }).then(function (details) {
      state.liveMatchDetails = details;
      state.liveMatchDetailsLoading = false;
      render();
    }).catch(function (error) {
      state.liveMatchDetailsLoading = false;
      state.liveMatchDetailsError = error.message || "Could not load saved match details.";
      render();
    });
  }

  function loadSavedLiveLineups(matchId) {
    state.liveMatchId = String(matchId);
    state.lineupMode = "live";
    state.liveLineups = null;
    state.liveLineupMessage = "Loading stored lineups...";
    state.activeLineupPlayer = null;
    render();
    fetch("/api/matches/" + encodeURIComponent(matchId) + "/lineups").then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) throw new Error(body.detail || "Could not load saved lineups.");
        return body;
      });
    }).then(function (body) {
      state.liveLineups = body;
      state.liveLineupMessage = body.message || "";
      render();
    }).catch(function (error) {
      state.liveLineupMessage = error.message || "Could not load saved lineups.";
      render();
    });
  }

  function sendConfirmedLineupImport() {
    if (!window.confirm("Import lineups for this live match? The estimated cost is 5 StrikerAPI credits. No automatic retry will be made.")) return;
    state.liveImportMessage = "Requesting verified lineups...";
    render();
    fetch("/api/matches/" + encodeURIComponent(state.liveMatchId) + "/lineups/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmed: true })
    }).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) throw new Error(body.detail || "Lineup import failed.");
        return body;
      });
    }).then(function (body) {
      state.liveLineups = body;
      state.liveLineupMessage = body.message || "";
      state.liveImportMessage = "Lineups saved locally. Estimated API cost: " + body.estimated_credits + " credits.";
      render();
    }).catch(function (error) {
      state.liveImportMessage = error.message || "Lineup import failed. No retry was made.";
      render();
    });
  }

  function sendConfirmedStatisticsImport(refresh) {
    if (!state.liveMatchDetails || state.activeMatchSource !== "live") return;
    const prompt = refresh
      ? "Refresh this match's stored statistics from BigBallsData? This uses up to 2 requests. Its free plan is season-limited; no automatic retry will be made."
      : "Import this match's statistics from BigBallsData? This uses up to 2 requests. The free plan is season-limited; no automatic retry will be made.";
    if (!window.confirm(prompt)) return;
    const matchId = state.liveMatchDetails.id;
    state.liveStatsMessage = "Requesting verified match statistics...";
    render();
    fetch("/api/matches/" + encodeURIComponent(matchId) + "/statistics/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmed: true, refresh: refresh })
    }).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) throw new Error(body.detail || "Statistics import failed.");
        return body;
      });
    }).then(function (body) {
      state.liveMatchDetails = body;
      state.liveStatsMessage = body.statistics_import && body.statistics_import.cached
        ? "Showing locally saved BigBallsData statistics; no requests were used."
        : body.statistics_import && body.statistics_import.available
          ? "Statistics saved locally from BigBallsData."
          : "The provider returned no statistics for this match; missing values remain unavailable.";
      render();
    }).catch(function (error) {
      state.liveStatsMessage = error.message || "Statistics import failed. No retry was made.";
      render();
    });
  }

  function sendConfirmedMatchListImport(refresh) {
    const requestText = refresh
      ? "Refresh up to 3 saved matches from StrikerAPI? The list_games credit cost is not independently verified. Check current provider pricing before continuing."
      : "Load up to 3 saved matches, or request the match list from StrikerAPI if more records are needed? The list_games credit cost is not independently verified. Check current provider pricing before continuing.";
    if (!window.confirm(requestText)) return;
    const seasonInput = document.getElementById("live-season");
    const season = seasonInput ? seasonInput.value.trim() : state.listImportSeason;
    if (!season) {
      state.liveImportMessage = "Enter a season before importing matches.";
      render();
      return;
    }
    state.listImportSeason = season;
    state.liveImportMessage = "Importing a small live match list...";
    render();
    fetch("/api/live-matches/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ season: season, limit: 3, refresh: Boolean(refresh), confirmed: true })
    }).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) throw new Error(body.detail || "Match-list import failed.");
        return body;
      });
    }).then(function (body) {
      state.liveImportMessage = "Match-list request completed. Created: " + body.imported_records.created + ", updated: " + body.imported_records.updated + ", unchanged: " + body.imported_records.skipped + ".";
      state.liveMatchesLoaded = false;
      state.liveMatches = [];
      loadLiveMatches();
      render();
    }).catch(function (error) {
      state.liveImportMessage = error.message || "Match-list import failed.";
      render();
    });
  }

  function demoPitchLineup(matchItem, side) {
    const matchNumber = Number(String(matchItem.id).replace(/\D/g, "")) || 1;
    const formation = demoFormations[(matchNumber - 1) % demoFormations.length];
    const home = side === "home";
    const sampleNames = matchItem.lineups[side].slice(0, 11);
    while (sampleNames.length < 11) {
      sampleNames.push((home ? "Home" : "Away") + " Demo Player " + String(sampleNames.length + 1).padStart(2, "0"));
    }

    const positions = window.SERIE_A_FORMATIONS.getFormationPositions(formation, side);
    const players = positions.map(function (position, index) {
      return {
        id: side + "-" + index,
        name: sampleNames[index],
        number: index + 1,
        role: position.role,
        left: position.left,
        top: position.top,
        goals: index === 10 ? 1 : 0,
        assists: index === 9 ? 1 : 0,
        yellowCards: index === 5 ? 1 : 0,
        redCards: 0,
        playerRole: "starter"
      };
    });

    const substitutes = [1, 2, 3].map(function (number) {
      return {
        id: side + "-sub-" + number,
        name: (home ? "Home" : "Away") + " Demo Substitute " + number,
        number: 20 + number,
        role: "Substitute",
        goals: 0,
        assists: 0,
        yellowCards: 0,
        redCards: 0,
        playerRole: "unused_substitute"
      };
    });
    return { formation: formation, players: players, substitutes: substitutes };
  }

  function apiPitchLineup(lineup, side) {
    if (!lineup) return { formation: "—", players: [], substitutes: [] };
    const formation = formationLayouts[lineup.formation] ? lineup.formation : "4-3-3";
    const layout = formationLayouts[formation];
    const slots = window.SERIE_A_FORMATIONS.getFormationPositions(formation, side);

    const starters = Array.isArray(lineup.starting_players) ? lineup.starting_players : [];
    const players = starters.map(function (player, index) {
      const formationSlot = Number(player.formation_slot);
      const slotIndex = Number.isInteger(formationSlot) && formationSlot >= 1 && formationSlot <= 11 ? formationSlot - 1 : index;
      const position = slots[slotIndex] || slots[index] || { left: 50, top: 50, role: "Player" };
      return {
        id: "api-" + lineup.team_id + "-" + player.id,
        name: player.name || "Name not provided",
        number: player.shirt_number == null ? "—" : player.shirt_number,
        role: player.position || (position.role + " · approx"),
        left: position.left,
        top: position.top,
        goals: player.goals,
        assists: player.assists,
        yellowCards: player.yellow_cards,
        redCards: player.red_cards,
        playerRole: player.player_role || "starter"
      };
    });

    function convertSubstitute(player) {
      return {
        id: "api-" + lineup.team_id + "-" + player.id,
        name: player.name || "Name not provided",
        number: player.shirt_number == null ? "—" : player.shirt_number,
        role: player.position || "Position not provided",
        goals: player.goals,
        assists: player.assists,
        yellowCards: player.yellow_cards,
        redCards: player.red_cards,
        minuteOn: player.minute_on,
        minuteOff: player.minute_off,
        playerRole: player.player_role || "substitute"
      };
    }

    const used = Array.isArray(lineup.substitutes_used) ? lineup.substitutes_used : [];
    const unused = Array.isArray(lineup.unused_substitutes) ? lineup.unused_substitutes : [];
    return {
      formation: lineup.formation || "Formation not provided",
      players: players,
      substitutes: used.concat(unused).map(convertSubstitute)
    };
  }

  function playerIndicators(player) {
    let result = "";
    const sample = state.lineupMode === "demo" ? " demo" : "";
    if (player.goals > 0) result += '<span class="lineup-indicator goal-indicator" title="' + player.goals + sample + ' goal(s)">' + icon("goal", 11) + '</span>';
    if (player.assists > 0) result += '<span class="lineup-indicator assist-indicator" title="' + player.assists + sample + ' assist(s)">A</span>';
    if (player.yellowCards > 0) result += '<span class="card-indicator yellow-card" title="' + player.yellowCards + sample + ' yellow card(s)"></span>';
    if (player.redCards > 0) result += '<span class="card-indicator red-card" title="' + player.redCards + sample + ' red card(s)"></span>';
    return result;
  }

  function pitchPlayer(player, side) {
    return '<button class="pitch-player ' + side + (state.activeLineupPlayer === player.id ? " selected" : "") + '" style="left:' + player.left + '%;top:' + player.top + '%" data-action="lineup-player" data-player-id="' + player.id + '" aria-label="' + escapeHtml(player.name) + ', number ' + player.number + ', ' + player.role + '">' +
      '<span class="pitch-shirt">' + player.number + '</span><span class="pitch-name">' + escapeHtml(player.name) + '</span><span class="pitch-role">' + player.role + '</span><span class="pitch-indicators">' + playerIndicators(player) + '</span></button>';
  }

  function lineupScreen() {
    loadLiveMatches();
    const demoItem = match(state.matchId);
    const liveMatch = state.liveMatches.find(function (record) {
      return String(record.id) === state.liveMatchId;
    });
    const useLive = state.lineupMode === "live";
    const item = useLive ? {
      home: liveMatch ? liveMatch.home_team_name : "Home team not available",
      away: liveMatch ? liveMatch.away_team_name : "Away team not available",
      lineups: { home: [], away: [] }
    } : demoItem;
    let homeLineup;
    let awayLineup;
    if (useLive && state.liveLineups) {
      const savedLineups = state.liveLineups.lineups || [];
      homeLineup = apiPitchLineup(
        savedLineups.find(function (row) { return row.team_name === item.home; }),
        "home",
      );
      awayLineup = apiPitchLineup(
        savedLineups.find(function (row) { return row.team_name === item.away; }),
        "away",
      );
    } else if (useLive) {
      homeLineup = { formation: "—", players: [], substitutes: [] };
      awayLineup = { formation: "—", players: [], substitutes: [] };
    } else {
      homeLineup = demoPitchLineup(item, "home");
      awayLineup = demoPitchLineup(item, "away");
    }
    const visibleHome = state.lineupSide !== "away";
    const visibleAway = state.lineupSide !== "home";
    let selectedPlayer = null;
    homeLineup.players.concat(awayLineup.players, homeLineup.substitutes, awayLineup.substitutes).forEach(function (player) {
      if (player.id === state.activeLineupPlayer) selectedPlayer = player;
    });
    const substitutes = [visibleHome ? { team: item.home, players: homeLineup.substitutes } : null, visibleAway ? { team: item.away, players: awayLineup.substitutes } : null].filter(Boolean).map(function (group) {
      return '<section class="substitute-group"><div class="substitute-heading"><h3>' + escapeHtml(group.team) + ' · Substitutes</h3><span>' + (useLive ? "SAVED DATA" : "DEMO DATA") + '</span></div><div class="substitute-list">' + (group.players.length ? group.players.map(function (player) {
        const minuteLabel = [player.minuteOn, player.minuteOff].filter(function (minute) { return minute != null; }).map(function (minute) { return minute + "'"; }).join("–");
        return '<button class="substitute-player" data-action="lineup-player" data-player-id="' + player.id + '"><span class="substitute-number">' + escapeHtml(player.number) + '</span><span>' + escapeHtml(player.name) + '</span><small>' + escapeHtml(player.playerRole.replaceAll("_", " ")) + (minuteLabel ? " · " + minuteLabel : "") + '</small>' + playerIndicators(player) + '</button>';
      }).join("") : '<p class="muted">Substitute information was not provided.</p>') + '</div></section>';
    }).join("");
    const detailLabel = useLive ? "Stored player data" : "DEMO DATA — SAMPLE VALUES";
    function showStatistic(value) {
      return value == null ? "Not provided" : value;
    }
    const detail = selectedPlayer ? '<aside class="panel player-detail"><div class="panel-heading"><div><h2>Player details</h2><p>' + detailLabel + '</p></div><button class="icon-button" data-action="close-player" aria-label="Close player details">' + icon("x", 15) + '</button></div><h3>' + escapeHtml(selectedPlayer.name) + '</h3><p class="player-role-line">#' + escapeHtml(selectedPlayer.number) + ' · ' + escapeHtml(selectedPlayer.role) + ' · ' + escapeHtml(selectedPlayer.playerRole.replaceAll("_", " ")) + '</p><div class="player-stat-list"><span>Goals <b>' + showStatistic(selectedPlayer.goals) + '</b></span><span>Assists <b>' + showStatistic(selectedPlayer.assists) + '</b></span><span>Yellow cards <b>' + showStatistic(selectedPlayer.yellowCards) + '</b></span><span>Red cards <b>' + showStatistic(selectedPlayer.redCards) + '</b></span>' + (selectedPlayer.minuteOn != null ? '<span>Minute on <b>' + selectedPlayer.minuteOn + '\'</b></span>' : '') + (selectedPlayer.minuteOff != null ? '<span>Minute off <b>' + selectedPlayer.minuteOff + '\'</b></span>' : '') + '</div></aside>' : '<aside class="panel player-detail player-detail-empty"><p>Select a player to inspect ' + (useLive ? "stored" : "fictional sample") + ' contributions. Missing values are shown as “Not provided”.</p></aside>';
    const liveOptions = state.liveMatches.map(function (record) {
      return '<option value="' + record.id + '"' + (useLive && state.liveMatchId === String(record.id) ? " selected" : "") + '>' + escapeHtml(record.home_team_name + " vs " + record.away_team_name) + '</option>';
    }).join("");
    const unavailableLiveOption = useLive && !liveMatch
      ? '<option value="' + escapeHtml(state.liveMatchId) + '" selected>Saved live match unavailable</option>'
      : "";
    const sourcePanel = '<section class="panel live-lineup-panel"><div class="panel-heading"><div><h2>Saved live match data</h2><p>Local database lookup uses no API credits. Live import requires confirmation.</p></div></div><div class="live-lineup-controls"><label><span>Match</span><select class="select" data-change="lineup-match"><option value="demo"' + (state.lineupMode === "demo" ? " selected" : "") + '>Fictional demo fixture</option>' + unavailableLiveOption + liveOptions + '</select></label>' + (useLive && liveMatch ? '<button class="button button-secondary" data-action="load-live-lineups">Load saved lineups</button><button class="button button-primary" data-action="import-live-lineups">Import from StrikerAPI · 5 credits</button>' : '') + '</div>' + (state.liveMatchesError ? '<p class="live-status">' + escapeHtml(state.liveMatchesError) + '</p>' : '') + (state.liveLineupMessage ? '<p class="live-status">' + escapeHtml(state.liveLineupMessage) + '</p>' : '') + (state.liveImportMessage ? '<p class="live-status">' + escapeHtml(state.liveImportMessage) + '</p>' : '') + '<div class="match-list-import"><label><span>Season for a small match-list import (up to 3 matches)</span><input id="live-season" value="' + escapeHtml(state.listImportSeason) + '" maxlength="20"></label><button class="button button-secondary" data-action="import-live-matches">Import match list</button><small>Credit estimate: not independently verified. Check current provider pricing before confirming.</small></div></section>';
    const emptyLineupMessage = useLive && !state.liveLineups ? '<div class="panel empty-lineup-state">' + escapeHtml(state.liveLineupMessage || "Choose Load saved lineups to check the local database. No live request will happen automatically.") + '</div>' : "";
    const noSavedLineupMessage = useLive && state.liveLineups && !state.liveLineups.complete ? '<div class="panel empty-lineup-state">' + escapeHtml(state.liveLineups.message || "Complete lineup data is not stored for both teams. Choose import only if you approve the displayed 5-credit estimate.") + '</div>' : "";

    return sourcePanel + '<div class="lineup-toolbar panel"><div><p class="section-kicker">' + (useLive ? "STORED LIVE MATCH LINEUP" : "INTERACTIVE FORMATION PREVIEW") + '</p><p class="muted">' + escapeHtml(item.home) + ' vs ' + escapeHtml(item.away) + ' · Formation: ' + homeLineup.formation + ' / ' + awayLineup.formation + '</p></div><div class="lineup-tools"><label class="sr-only" for="lineup-side">Team view</label><select class="select" id="lineup-side" data-change="lineup-side"><option value="both"' + (state.lineupSide === "both" ? " selected" : "") + '>Both teams</option><option value="home"' + (state.lineupSide === "home" ? " selected" : "") + '>' + escapeHtml(item.home) + '</option><option value="away"' + (state.lineupSide === "away" ? " selected" : "") + '>' + escapeHtml(item.away) + '</option></select><button class="button button-secondary" data-action="back-lineup">' + icon("arrow-left", 14) + ' Match details</button></div></div>' + emptyLineupMessage + noSavedLineupMessage +
      '<div class="pitch-layout"><section class="panel pitch-panel"><div class="pitch-heading"><span>' + badge(item.home) + '<b>' + escapeHtml(item.home) + '</b><small>' + homeLineup.formation + '</small></span><span class="pitch-label">APPROXIMATE FORMATION · ' + (useLive ? "STORED DATA" : "DEMO DATA") + '</span><span><small>' + awayLineup.formation + '</small><b>' + escapeHtml(item.away) + '</b>' + badge(item.away) + '</span></div><div class="football-pitch" role="img" aria-label="Approximate formation for ' + escapeHtml(item.home) + ' and ' + escapeHtml(item.away) + '">' +
      '<span class="pitch-halfway"></span><span class="pitch-center-circle"></span><span class="pitch-center-spot"></span><span class="pitch-box home-box"></span><span class="pitch-box away-box"></span><span class="pitch-goal home-goal"></span><span class="pitch-goal away-goal"></span>' +
      (visibleHome ? homeLineup.players.map(function (player) { return pitchPlayer(player, "home"); }).join("") : "") +
      (visibleAway ? awayLineup.players.map(function (player) { return pitchPlayer(player, "away"); }).join("") : "") + '</div></section>' + detail + '</div>' +
      '<section class="panel substitutes-panel"><div class="panel-heading"><div><h2>Substitutes</h2><p>' + (useLive ? "Provider-submitted substitute details" : "Illustrative bench entries · fictional sample data") + '</p></div></div><div class="substitute-groups">' + substitutes + '</div></section>' +
      '<div class="lineup-footnote">The layout algorithm spreads players into formation rows and approximates depth across the pitch. StrikerAPI formation slots are ordinal values, not x/y coordinates. Missing live values are shown as not provided; demo values are fictional.</div>';
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
    } else if (action === "data-mode") {
      state.dataMode = target.dataset.mode;
      state.search = "";
      state.liveImportMessage = "";
      if (state.dataMode === "live") {
        state.liveMatchesLoaded = false;
        state.liveMatchesError = "";
        loadLiveMatches();
        render();
      } else {
        render();
      }
    } else if (action === "view-match") {
      state.matchId = target.dataset.id;
      state.activeMatchSource = "demo";
      state.detailTab = "overview";
      state.screen = "match";
      render();
    } else if (action === "view-live-match") {
      openLiveMatch(target.dataset.id);
    } else if (action === "toggle-save") {
      toggleSaved(target.dataset.id, false);
    } else if (action === "remove-save") {
      toggleSaved(target.dataset.id, true);
    } else if (action === "detail-tab") {
      state.detailTab = target.dataset.tab;
      if (state.activeMatchSource === "live" && state.detailTab === "lineups" && state.liveMatchDetails) {
        loadSavedLiveLineups(state.liveMatchDetails.id);
        return;
      }
      render();
    } else if (action === "open-lineup") {
      state.activeLineupPlayer = null;
      state.lineupSide = "both";
      state.screen = "lineup";
      if (state.activeMatchSource === "live" && state.liveMatchDetails) {
        loadSavedLiveLineups(state.liveMatchDetails.id);
      } else {
        state.lineupMode = "demo";
        render();
      }
    } else if (action === "load-live-lineups") {
      loadSavedLiveLineups(state.liveMatchId);
    } else if (action === "import-live-lineups") {
      sendConfirmedLineupImport();
    } else if (action === "import-live-matches") {
      sendConfirmedMatchListImport(false);
    } else if (action === "refresh-live-matches") {
      sendConfirmedMatchListImport(true);
    } else if (action === "import-live-statistics") {
      sendConfirmedStatisticsImport(false);
    } else if (action === "refresh-live-statistics") {
      sendConfirmedStatisticsImport(true);
    } else if (action === "lineup-player") {
      state.activeLineupPlayer = target.dataset.playerId;
      render();
    } else if (action === "close-player") {
      state.activeLineupPlayer = null;
      render();
    } else if (action === "back-lineup") {
      state.screen = "match";
      state.detailTab = "lineups";
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
    if (target.dataset.change === "live-season") {
      state.liveSeason = target.value;
      render();
    } else if (target.dataset.change === "season") {
      state.season = target.value;
      if (state.round !== "all" && !data.matches.some(function (item) { return item.season === state.season && String(item.round) === state.round; })) state.round = "all";
      render();
    } else if (target.dataset.change === "round") {
      state.round = target.value;
      render();
    } else if (target.dataset.change === "team") {
      state.team = target.value;
      render();
    } else if (target.dataset.change === "lineup-side") {
      state.lineupSide = target.value;
      state.activeLineupPlayer = null;
      render();
    } else if (target.dataset.change === "lineup-match") {
      state.liveImportMessage = "";
      state.liveLineupMessage = "";
      if (target.value === "demo") {
        state.lineupMode = "demo";
        state.liveMatchId = "";
        state.liveLineups = null;
        state.activeLineupPlayer = null;
        render();
      } else {
        loadSavedLiveLineups(target.value);
      }
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
