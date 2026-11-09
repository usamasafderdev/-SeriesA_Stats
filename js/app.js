(function () {
  const app = document.getElementById("app");
  const state = {
    screen: "landing",
    season: "all",
    round: "all",
    matchStatus: "finished",
    search: "",
    team: "",
    selectedPlayerId: null,
    chartMetric: "goals",
    detailTab: "overview",
    matches: [],
    coverage: null,
    standings: [],
    savedMatches: [],
    matchDetails: null,
    lineups: null,
    detailLoading: false,
    loading: true,
    busy: false,
    error: "",
    actionMessage: "",
    pendingApproval: null,
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
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function icon(name, size) {
    return '<i data-lucide="' + name + '" width="' + (size || 17) + '" height="' + (size || 17) + '"></i>';
  }

  function formatDate(value) {
    if (!value) return "Date not available";
    const text = String(value);
    const parsed = new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(text) ? text : text + "Z");
    return Number.isNaN(parsed.getTime()) ? "Date not available" :
      parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  }

  function formatScore(match) {
    if (match.home_score == null || match.away_score == null) return "Not available";
    return match.home_score + " – " + match.away_score;
  }

  function formatTimestamp(value) {
    if (!value) return null;
    const text = String(value);
    const parsed = new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(text) ? text : text + "Z");
    return Number.isNaN(parsed.getTime()) ? null :
      parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }

  function lastUpdated(matches) {
    const timestamps = [];
    (matches || []).forEach(function (match) {
      [match.fetched_at, match.statistics_fetched_at].forEach(function (value) {
        const formatted = formatTimestamp(value);
        if (formatted) timestamps.push({ value: value, formatted: formatted });
      });
    });
    if (!timestamps.length) return "Last updated unavailable";
    timestamps.sort(function (left, right) {
      const rightText = String(right.value);
      const leftText = String(left.value);
      const rightDate = new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(rightText) ? rightText : rightText + "Z");
      const leftDate = new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(leftText) ? leftText : leftText + "Z");
      return rightDate.getTime() - leftDate.getTime();
    });
    return "Last updated · " + timestamps[0].formatted;
  }

  function badge(name, large) {
    const initials = String(name || "?").split(/\s+/).slice(0, 2).map(function (part) {
      return part.charAt(0);
    }).join("").toUpperCase();
    return '<span class="team-badge' + (large ? " team-badge-lg" : "") +
      '" style="--team:#2879d8;--team-accent:#e5f4ff" aria-label="' + escapeHtml(name) + '">' +
      escapeHtml(initials || "?") + "</span>";
  }

  function seasonList() {
    return Array.from(new Set(state.matches.map(function (item) { return item.season; })))
      .sort().reverse();
  }

  function selectedMatches() {
    return state.matches.filter(function (item) {
      const seasonMatches = state.season === "all" || item.season === state.season;
      const statusMatches = state.matchStatus === "all" || item.status === state.matchStatus;
      const names = (item.home_team_name + " " + item.away_team_name).toLowerCase();
      return seasonMatches && statusMatches && names.includes(state.search.toLowerCase());
    }).sort(function (left, right) {
      return String(right.match_date || "").localeCompare(String(left.match_date || ""));
    });
  }

  function leagueMatches() {
    return state.matches.filter(function (item) {
      return item.status === "finished" && (state.season === "all" || item.season === state.season);
    }).sort(function (a, b) { return String(b.match_date).localeCompare(String(a.match_date)); });
  }

  function activeSeason() {
    return state.season === "all" ? seasonList()[0] : state.season;
  }

  function officialStandings() {
    return state.standings.filter(function (row) { return row.season === activeSeason(); });
  }

  function matchScreenRecords() {
    return selectedMatches().filter(function (item) {
      return state.round === "all" || item.round === state.round;
    });
  }

  function availableRounds() {
    const rounds = state.matches.filter(function (item) {
      const seasonMatches = state.season === "all" || item.season === state.season;
      const names = (item.home_team_name + " " + item.away_team_name).toLowerCase();
      return seasonMatches && names.includes(state.search.toLowerCase()) && item.round;
    }).map(function (item) { return item.round; });
    return Array.from(new Set(rounds)).sort();
  }

  function roundSelect() {
    const options = ['<option value="all"' + (state.round === "all" ? " selected" : "") + '>All rounds</option>']
      .concat(availableRounds().map(function (round) {
        return '<option value="' + escapeHtml(round) + '"' +
          (state.round === round ? " selected" : "") + ">" + escapeHtml(round) + "</option>";
      }));
    return '<label class="sr-only" for="round-select">Round</label><select class="select" id="round-select" data-change="round">' +
      options.join("") + "</select>";
  }

  function statusSelect() {
    const options = [["finished", "Finished"], ["live", "Live"], ["scheduled", "Upcoming"], ["all", "All fixtures"]];
    return '<label class="sr-only" for="status-select">Result status</label><select class="select" id="status-select" data-change="status">' +
      options.map(function (option) {
        return '<option value="' + option[0] + '"' + (state.matchStatus === option[0] ? " selected" : "") + ">" + option[1] + "</option>";
      }).join("") + "</select>";
  }

  function seasonSelect() {
    const options = ['<option value="all"' + (state.season === "all" ? " selected" : "") + '>All saved seasons</option>']
      .concat(seasonList().map(function (season) {
        return '<option value="' + escapeHtml(season) + '"' +
          (state.season === season ? " selected" : "") + ">Season " + escapeHtml(season) + "</option>";
      }));
    return '<label class="sr-only" for="season-select">Season</label><select class="select season-select" id="season-select" data-change="season">' +
      options.join("") + "</select>";
  }

  function shell(content) {
    const titles = {
      dashboard: "Welcome to Serie A Tracker", matches: "Serie A Matches",
      match: "Match Statistics", lineup: "Player Lineup",
      teams: "Team Statistics", statistics: "League Statistics",
      saved: "Saved Matches", about: "About this tracker"
    };
    const active = state.screen;
    return (state.actionMessage ? '<div class="app-notification" role="status">' + escapeHtml(state.actionMessage) + "</div>" : "") + '<div class="app-shell"><aside class="sidebar">' +
      '<a class="brand-lockup" href="#" data-action="navigate" data-screen="dashboard"><img src="assets/logo.svg" alt="" class="brand-logo"><span><strong>Serie A</strong><small>Match Tracker</small></span></a>' +
      '<nav class="side-nav" aria-label="Main navigation">' + navItems.map(function (item) {
        return '<button class="nav-link' + (active === item[0] || (["match", "lineup"].includes(active) && item[0] === "matches") ? " active" : "") +
          '" data-action="navigate" data-screen="' + item[0] + '">' + icon(item[2]) + "<span>" + item[1] + "</span></button>";
      }).join("") + '</nav><div class="sidebar-foot"><span class="status-dot"></span> Live database</div></aside>' +
      '<main class="main-content"><div class="demo-banner live-banner">' + icon("database", 14) +
      '<span>LIVE DATA — LOCAL DATABASE</span><span class="banner-note">No fictional records · missing values stay unavailable</span></div>' +
      '<header class="topbar"><div class="topbar-copy"><div class="eyebrow">SERIE A · MATCH CENTER</div><h1>' +
      (titles[active] || "Serie A Tracker") + '</h1></div><div class="topbar-actions">' +
      (["about", "lineup"].includes(active) ? "" : seasonSelect()) +
      '<button class="mobile-menu icon-button" data-action="menu" aria-label="Toggle navigation">' + icon("menu") + "</button></div></header>" +
      '<section class="page-content">' + approvalPanel() + content + '</section><footer class="page-footer">Independent tracker · Unaffiliated with any league or club</footer></main></div>';
  }

  function approvalPanel() {
    if (!state.pendingApproval) return "";
    return '<section class="panel approval-panel" role="alert"><div><strong>Provider request approval</strong><p>' +
      escapeHtml(state.pendingApproval.message) + '</p><small>No automatic retries. Requests are made only after approval.</small></div>' +
      '<div class="row-actions"><button class="button button-primary" data-action="approve-request">Approve request</button>' +
      '<button class="button button-secondary" data-action="cancel-request">Cancel</button></div></section>';
  }

  function statCard(label, value, note, iconName, tone) {
    return '<article class="stat-card ' + tone + '"><div class="stat-card-icon">' + icon(iconName, 21) +
      '</div><div class="stat-card-copy"><span>' + label + "</span><strong>" + escapeHtml(value) +
      "</strong><small>" + escapeHtml(note) + "</small></div></article>";
  }

  function emptyState(message) {
    return '<div class="panel empty-state live-empty" role="status">' + escapeHtml(message) + "</div>";
  }

  function matchRows(matches, saved) {
    return matches.map(function (item) {
      return '<tr><td><span class="date-cell">' + escapeHtml(formatDate(item.match_date)) + "</span><small class=\"sub-cell\">" +
        escapeHtml(item.status) + (item.round ? " · " + escapeHtml(item.round) : "") + '</small></td><td><span class="team-name-cell">' + badge(item.home_team_name) +
        "<b>" + escapeHtml(item.home_team_name) + '</b></span></td><td><strong class="score">' +
        escapeHtml(formatScore(item)) + '</strong></td><td><span class="team-name-cell">' + badge(item.away_team_name) +
        "<b>" + escapeHtml(item.away_team_name) + '</b></span></td><td><div class="row-actions">' +
        '<button class="table-action" data-action="view-match" data-id="' + item.id + '">View ' + icon("arrow-right", 13) + "</button>" +
        (saved ? '<button class="table-icon remove-icon" data-action="remove-save" data-id="' + item.id + '" title="Remove saved match">' + icon("trash-2", 15) + "</button>" :
          '<button class="table-icon" data-action="save-match" data-id="' + item.id + '" title="Save match">' + icon("bookmark", 15) + "</button>") +
        "</div></td></tr>";
    }).join("");
  }

  function dashboard() {
    if (state.loading) return emptyState("Loading saved match records…");
    if (state.error) return emptyState(state.error);
    const matches = leagueMatches();
    const scored = matches.filter(function (item) { return item.home_score != null && item.away_score != null; });
    const goals = scored.reduce(function (sum, item) { return sum + item.home_score + item.away_score; }, 0);
    const teams = new Set();
    matches.forEach(function (item) { teams.add(item.home_team_name); teams.add(item.away_team_name); });
    const rows = matchRows(matches.slice(0, 5), false);
    const latest = matches[0];
    const latestResult = latest ? formatScore(latest) + " · " + latest.home_team_name + " vs " + latest.away_team_name : "Not available";
    return '<div class="welcome-row"><div><p class="section-kicker">SAVED LIVE RECORDS</p><p class="muted">All figures below come from records stored in SQLite.</p><p class="live-status">' +
      escapeHtml(lastUpdated(matches)) + '</p></div>' +
      '<button class="button button-secondary" data-action="navigate" data-screen="matches">Browse matches ' + icon("arrow-up-right", 15) + "</button></div>" +
      '<div class="stats-grid">' + statCard("Completed matches", matches.length, "Finished official results", "calendar-days", "cyan") +
      statCard("Goals", scored.length ? goals : "Not available", scored.length + " matches with scores", "goal", "blue") +
      statCard("Teams", teams.size, "Distinct teams in results", "shield", "indigo") +
      statCard("Latest result", latestResult, latest ? formatDate(latest.match_date) : "No completed results", "trophy", "violet") + "</div>" +
      (state.coverage ? '<section class="panel coverage-panel"><div class="panel-heading"><div><h2>Verified detail coverage</h2><p>Cached records only · no requests made by opening this page</p></div></div>' +
        '<div class="number-grid"><div><span>Detailed statistics</span><b>' + state.coverage.detailed_statistics + " / " + state.coverage.completed_fixtures +
        '</b></div><div><span>Lineups</span><b>' + state.coverage.lineups + " / " + state.coverage.completed_fixtures +
        '</b></div><div><span>Player performance</span><b>' + state.coverage.player_performance + " / " + state.coverage.completed_fixtures +
        '</b></div><div><span>Events</span><b>' + state.coverage.events + " / " + state.coverage.completed_fixtures + "</b></div></div>" +
        '<div class="match-list-import"><label><span>Matches this batch</span><input id="highlightly-max-matches" type="number" min="1" max="10" value="1"></label>' +
        '<label><span>Request budget</span><input id="highlightly-max-requests" type="number" min="1" max="40" value="5"></label>' +
        '<label class="events-option"><input id="highlightly-include-events" type="checkbox">Include events</label><button class="button button-secondary" data-action="sync-highlightly">Review missing data</button></div></section>' : "") +
      (rows ? '<section class="panel table-panel"><div class="panel-heading"><div><h2>Recent Matches</h2><p>Saved provider records</p></div><button class="text-button" data-action="navigate" data-screen="matches">View all ' + icon("arrow-right", 14) + "</button></div>" +
        '<div class="table-wrap"><table><thead><tr><th>Date / Status</th><th>Home Team</th><th>Score</th><th>Away Team</th><th>Actions</th></tr></thead><tbody>' + rows + "</tbody></table></div></section>" :
        emptyState("No completed Serie A matches match the current filters."));
  }

  function matchesScreen() {
    if (state.loading) return emptyState("Loading saved match records…");
    if (state.error) return emptyState(state.error);
    const matches = matchScreenRecords();
    const rows = matchRows(matches, false);
    return '<div class="filter-bar panel"><label class="search-wrap">' + icon("search", 16) +
      '<span class="sr-only">Search teams</span><input type="search" data-input="search" value="' + escapeHtml(state.search) +
      '" placeholder="Search by team..."></label>' + roundSelect() +
      statusSelect() + '<button class="button button-secondary" data-action="refresh-local">Refresh saved records</button></div>' +
      '<section class="panel table-panel matches-table-panel"><div class="panel-heading"><div><h2>Saved Serie A Fixtures</h2><p>SQLite records · Provider data only · ' +
      escapeHtml(lastUpdated(matches)) + '</p></div><span class="result-count">' + matches.length + " RESULTS</span></div>" +
      '<div class="table-wrap"><table><thead><tr><th>Date / Status</th><th>Home Team</th><th>Score</th><th>Away Team</th><th>Actions</th></tr></thead><tbody>' +
      (rows || '<tr><td class="empty-state" colspan="5">' + (state.matches.length ? "No saved matches match these filters." : "No live fixtures have been imported yet.") + "</td></tr>") +
      "</tbody></table></div></section>";
  }

  function valueText(value, suffix) {
    return value == null ? "Not available" : escapeHtml(value) + (suffix || "");
  }

  function comparisonBar(label, left, right, unit) {
    if (left == null && right == null) return "";
    if (left == null || right == null) {
      return '<div class="comparison-row"><div class="compare-values"><b>' + valueText(left, unit) + "</b><span>" +
        label + "</span><b>" + valueText(right, unit) + '</b></div><div class="metric-unavailable">One or both values are not available.</div></div>';
    }
    const total = left + right || 1;
    return '<div class="comparison-row"><div class="compare-values"><b>' + left + (unit || "") + "</b><span>" + label +
      "</span><b>" + right + (unit || "") + '</b></div><div class="compare-track"><span class="home-fill" style="width:' +
      (left / total * 100) + '%"></span><span class="away-fill" style="width:' + (right / total * 100) + '%"></span></div></div>';
  }

  function contributionPanel(title, entries, field) {
    const rows = (entries || []).map(function (entry) {
      return "<li><b>" + escapeHtml(entry.player_name) + "</b><span>" +
        escapeHtml(entry.team_name) + " · " + escapeHtml(entry[field]) + "</span></li>";
    }).join("");
    return '<section class="panel detail-panel"><div class="panel-heading"><div><h2>' + title +
      '</h2><p>Saved player lineup records</p></div>' + icon("goal", 17) + "</div>" +
      (rows ? '<ul class="lineup-list">' + rows + "</ul>" : '<p class="muted">Not available. No player contributions are stored for this match.</p>') + "</section>";
  }

  function lineupCards() {
    if (!state.lineups) return emptyState("Lineups have not been loaded yet.");
    const cards = (state.lineups.lineups || []).map(function (lineup) {
      const players = lineup.starting_players || [];
      if (!players.length) return '<section class="panel detail-panel"><h2>' + escapeHtml(lineup.team_name) + '</h2><p class="muted">Starting XI not supplied.</p></section>';
      return '<section class="panel detail-panel"><div class="panel-heading"><div><h2>' + escapeHtml(lineup.team_name) +
        '</h2><p>' + escapeHtml(lineup.formation || "Formation not supplied") + " · starting XI</p></div>" +
        badge(lineup.team_name) + '</div><ol class="lineup-list">' + players.map(function (player) {
          return "<li><span>" + escapeHtml(player.shirt_number == null ? "—" : player.shirt_number) + "</span>" +
              '<button class="player-name-button" data-action="select-player" data-player-id="' + escapeHtml(player.id) + '">' + escapeHtml(player.name) + "</button>" +
              (player.rating == null ? "" : " <small class=\"muted\">★ " + escapeHtml(player.rating) + "</small>") +
              "</li>";
        }).join("") + "</ol></section>";
    }).join("");
    return cards || emptyState(state.lineups.message || "No lineups are stored for this match.");
  }

  function detailScreen() {
    if (state.detailLoading) return emptyState("Loading saved match details…");
    const item = state.matchDetails;
    if (!item) return emptyState(state.error || "Choose a saved match to see details.");
    const home = item.home_team.name;
    const away = item.away_team.name;
    const stats = item.statistics || {};
    const score = item.home_score == null || item.away_score == null
      ? "Not available" : item.home_score + '<span>:</span>' + item.away_score;
    let active;
    if (state.detailTab === "events") {
      const eventRows = (item.events || []).map(function (event) {
        return "<li><b>" + escapeHtml(event.minute == null ? "—" : (event.minute + (event.added_minute == null ? "" : "+" + event.added_minute) + "'")) + "</b> " +
          escapeHtml(event.type) + " · " + escapeHtml(event.player_name || "Player unavailable") +
          (event.assist_name ? " (assist: " + escapeHtml(event.assist_name) + ")" : "") +
          (event.detail ? " - " + escapeHtml(event.detail) : "") +
          (event.team_name ? " · " + escapeHtml(event.team_name) : "") + "</li>";
      }).join("");
      active = '<div class="detail-grid">' +
        '<section class="panel detail-panel"><div class="panel-heading"><h2>Match events</h2></div>' +
        (eventRows ? '<ul class="lineup-list">' + eventRows + "</ul>" : '<p class="muted">Events not available.</p>') + "</section>" +
        contributionPanel("Goal scorers", item.goal_scorers, "goals") +
        contributionPanel("Assists", item.goal_assists, "assists") + "</div>";
    } else if (state.detailTab === "lineups") {
      active = '<div class="lineup-open-row"><p>Saved starting XIs, substitutes and player performance. Opening this tab reads local records.</p>' +
        (state.actionMessage ? '<p class="muted" role="status">' + escapeHtml(state.actionMessage) + "</p>" : "") +
        '<button class="button button-secondary" data-action="load-lineups">Load saved lineups</button>' +
        '<button class="button button-primary" data-action="import-lineups">Fetch player lineup</button>' +
        '<button class="button button-secondary" data-action="import-player-details">Fetch player details</button>' +
        '<button class="button button-secondary" data-action="open-pitch">View pitch &amp; player performance</button></div>' +
        '<div class="lineups-grid">' + lineupCards() + "</div>";
    } else {
      const hasStats = item.statistics_available;
      active = '<div class="detail-grid"><section class="panel detail-panel"><div class="panel-heading"><div><h2>Post-match Statistics</h2><p>' +
        (hasStats ? escapeHtml(item.statistics_source || "Provider") + " · stored values · " +
          (formatTimestamp(item.statistics_fetched_at) || "Update time unavailable") : "No statistics saved yet") +
        '</p></div>' + icon("chart-no-axes-column-increasing", 17) + "</div>" +
        comparisonBar("Possession", stats.home_possession, stats.away_possession, "%") +
        comparisonBar("Total Shots", stats.home_shots, stats.away_shots, "") +
        comparisonBar("Shots on Target", stats.home_shots_on_target, stats.away_shots_on_target, "") +
        '<div class="statistics-import-row"><p>Only provider-supplied values are shown.</p>' +
        '<button class="button button-secondary" data-action="import-statistics">Review missing statistics</button></div></section>' +
        '<section class="panel detail-panel"><div class="panel-heading"><div><h2>Score &amp; goals</h2><p>Final score is shown only when supplied by the provider.</p></div>' +
        icon("goal", 17) + "</div>" + contributionPanel("Goal scorers", item.goal_scorers, "goals") + "</section></div>";
    }
    return '<div class="match-hero panel"><div class="match-hero-top"><button class="back-button" data-action="navigate" data-screen="matches">' +
      icon("arrow-left", 16) + '</button><span class="match-date">' + icon("calendar-days", 14) + " " +
      escapeHtml(formatDate(item.match_date)) + " · " + escapeHtml(item.status) + "</span>" +
      '<button class="save-inline" data-action="' + (state.savedMatches.some(function (saved) { return saved.id === item.id; }) ? "remove-save" : "save-match") +
      '" data-id="' + item.id + '">' + icon("bookmark", 14) + " " +
      (state.savedMatches.some(function (saved) { return saved.id === item.id; }) ? "Saved" : "Save match") + "</button></div>" +
      '<div class="scoreboard"><div class="score-team">' + badge(home, true) + "<strong>" + escapeHtml(home) +
      '</strong></div><div class="score-center"><div class="full-score">' + score + '</div><span class="ft-pill">' +
      escapeHtml(item.status) + "</span></div><div class=\"score-team\">" + badge(away, true) + "<strong>" +
      escapeHtml(away) + "</strong></div></div><div class=\"venue-line\">Season " + escapeHtml(item.season) +
      (item.round ? " · " + escapeHtml(item.round) : "") +
      (formatTimestamp(item.fetched_at) ? " · Fixture updated " + escapeHtml(formatTimestamp(item.fetched_at)) : "") +
      (item.status.toLowerCase() === "finished" ? " · Post-match data" : " · Score status: " + escapeHtml(item.status)) + "</div></div>" +
      '<div class="tabs" role="tablist">' + [["overview", "Overview"], ["events", "Events"], ["lineups", "Lineups"]].map(function (tab) {
        return '<button class="tab' + (state.detailTab === tab[0] ? " active" : "") + '" role="tab" aria-selected="' +
          (state.detailTab === tab[0]) + '" data-action="detail-tab" data-tab="' + tab[0] + '">' + tab[1] + "</button>";
      }).join("") + "</div>" + active;
  }

  function teamNames() {
    const names = new Set();
    leagueMatches().forEach(function (match) {
      names.add(match.home_team_name);
      names.add(match.away_team_name);
    });
    return Array.from(names).sort();
  }

  function teamRecord(name) {
    const matches = leagueMatches().filter(function (match) {
      return match.home_team_name === name || match.away_team_name === name;
    });
    const result = { played: 0, wins: 0, draws: 0, losses: 0, goals: 0, goalsAgainst: 0, points: 0, matches: [], allMatches: matches };
    matches.forEach(function (match) {
      const isHome = match.home_team_name === name;
      const goalsFor = isHome ? match.home_score : match.away_score;
      const goalsAgainst = isHome ? match.away_score : match.home_score;
      if (goalsFor == null || goalsAgainst == null) return;
      result.played += 1;
      result.goals += goalsFor;
      result.goalsAgainst += goalsAgainst;
      result.matches.push({ match: match, isHome: isHome });
      if (goalsFor > goalsAgainst) { result.wins += 1; result.points += 3; }
      else if (goalsFor === goalsAgainst) { result.draws += 1; result.points += 1; }
      else result.losses += 1;
    });
    return result;
  }

  function teamStats(name) {
    const record = teamRecord(name);
    const values = { possession: [], shots: [], target: [] };
    let assists = 0;
    let matchesWithAssists = 0;
    record.allMatches.forEach(function (match) {
      const isHome = match.home_team_name === name;
      const prefix = isHome ? "home_" : "away_";
      const value = isHome ? match.home_assists : match.away_assists;
      if (value != null) {
        assists += value;
        matchesWithAssists += 1;
      }
      const stats = match.statistics || {};
      [["possession", "possession"], ["shots", "shots"], ["target", "shots_on_target"]].forEach(function (pair) {
        const statValue = stats[prefix + pair[1]];
        if (statValue != null) values[pair[0]].push(statValue);
      });
    });
    function average(key) {
      const list = values[key];
      return list.length ? (list.reduce(function (sum, value) { return sum + value; }, 0) / list.length).toFixed(1) : "Not available";
    }
    const availableMetrics = {
      goals: record.played > 0,
      points: record.played > 0,
      possession: values.possession.length > 0,
      shots: values.shots.length > 0,
      target: values.target.length > 0
    };
    return {
      record: record,
      possession: average("possession"),
      shots: average("shots"),
      target: average("target"),
      availableMetrics: availableMetrics,
      sampleCounts: { possession: values.possession.length, shots: values.shots.length, target: values.target.length },
      assists: matchesWithAssists ? assists : "Not available",
      assistsNote: matchesWithAssists + " of " + record.allMatches.length + " matches with complete assist records"
    };
  }

  function chartTabs(stats) {
    const metrics = [["goals", "Goals"], ["points", "Points"], ["possession", "Possession"], ["shots", "Shots"], ["target", "On target"]];
    return metrics.map(function (entry) {
      if (!stats.availableMetrics[entry[0]]) return "";
      return '<button class="chart-tab' + (state.chartMetric === entry[0] ? " active" : "") +
        '" data-action="chart-tab" data-metric="' + entry[0] + '">' + entry[1] + "</button>";
    }).join("");
  }

  function teamsScreen() {
    const names = teamNames();
    if (!names.length) return emptyState("Team statistics are unavailable until live fixtures are imported.");
    if (!names.includes(state.team)) state.team = names[0];
    const stats = teamStats(state.team);
    if (!stats.availableMetrics[state.chartMetric]) {
      state.chartMetric = ["goals", "points", "possession", "shots", "target"].find(function (key) { return stats.availableMetrics[key]; }) || null;
    }
    return '<div class="team-toolbar panel"><div><label class="team-select-label" for="team-choice">Select Team</label><div class="team-picker">' +
      badge(state.team) + '<select class="select" id="team-choice" data-change="team">' +
      names.map(function (name) { return '<option value="' + escapeHtml(name) + '"' + (name === state.team ? " selected" : "") + ">" + escapeHtml(name) + "</option>"; }).join("") +
      '</select></div></div><div class="team-season">' + icon("calendar-days", 15) + " Imported results only · Season " + escapeHtml(activeSeason() || "unavailable") + "</div></div>" +
      '<div class="team-stat-grid">' + statCard("Played", stats.record.played, "Matches with a known score", "goal", "cyan") +
      statCard("Wins", stats.record.wins, "From saved scores", "trophy", "green") +
      statCard("Draws", stats.record.draws, "From saved scores", "equal", "blue") +
      statCard("Losses", stats.record.losses, "From saved scores", "circle-x", "rose") + "</div>" +
      '<div class="team-lower"><section class="panel team-number-panel"><div class="panel-heading"><div><h2>Performance Snapshot</h2><p>Calculated from selected season records</p></div></div>' +
      '<div class="number-grid"><div><span>Goals</span><b>' + (stats.record.played ? stats.record.goals : "Not available") + "</b></div>" +
      (stats.assists !== "Not available" ? '<div><span>Assists</span><b>' + escapeHtml(stats.assists) + "</b><small>" + escapeHtml(stats.assistsNote) + "</small></div>" : "") +
      (stats.availableMetrics.possession ? '<div><span>Avg. Possession</span><b>' + escapeHtml(stats.possession) + "%</b><small>" + stats.sampleCounts.possession + (stats.sampleCounts.possession === 1 ? " match" : " matches") + "</small></div>" : "") +
      (stats.availableMetrics.shots ? '<div><span>Avg. Shots</span><b>' + escapeHtml(stats.shots) + "</b><small>" + stats.sampleCounts.shots + (stats.sampleCounts.shots === 1 ? " match" : " matches") + "</small></div>" : "") +
      (stats.availableMetrics.target ? '<div><span>Avg. Shots on Target</span><b>' + escapeHtml(stats.target) + "</b><small>" + stats.sampleCounts.target + (stats.sampleCounts.target === 1 ? " match" : " matches") + "</small></div>" : "") +
      "</div></section>" +
      '<section class="panel chart-panel"><div class="chart-panel-head"><div><h2>Team Performance</h2><p>Actual saved match values · missing values are gaps</p></div><div class="chart-tabs">' +
      chartTabs(stats) + '</div></div>' +
      (stats.availableMetrics[state.chartMetric]
        ? '<div class="chart-canvas-wrap"><canvas id="team-chart" role="img" aria-label="Chart of saved match statistics for ' +
          escapeHtml(state.team) + '"></canvas></div>'
        : '<p class="metric-unavailable">No genuine saved values are available for this metric.</p>') +
      '</section></div>';
  }

  function leagueRows() {
    if (officialStandings().length) {
      return officialStandings().map(function (team) {
        return "<tr><td><span class=\"rank-pill\">" + team.position + "</span></td><td><span class=\"team-name-cell\">" +
          badge(team.team_name) + "<b>" + escapeHtml(team.team_name) + "</b></span></td><td>" + team.played + "</td><td>" +
          team.wins + "</td><td>" + team.draws + "</td><td>" + team.losses + "</td><td>" +
          team.goal_difference + "</td><td>" + team.points + "</td></tr>";
      }).join("");
    }
    const standings = teamNames().map(function (name) {
      const record = teamRecord(name);
      return { name: name, played: record.played, wins: record.wins, draws: record.draws, losses: record.losses, goals: record.goals, difference: record.goals - record.goalsAgainst, points: record.points };
    }).sort(function (left, right) {
      return right.points - left.points || right.difference - left.difference || right.goals - left.goals || left.name.localeCompare(right.name);
    });
    return standings.map(function (team, index) {
      return "<tr><td><span class=\"rank-pill\">" + (index + 1) + "</span></td><td><span class=\"team-name-cell\">" +
        badge(team.name) + "<b>" + escapeHtml(team.name) + "</b></span></td><td>" + team.played + "</td><td>" +
        team.wins + "</td><td>" + team.draws + "</td><td>" + team.losses + "</td><td>" + team.difference + "</td><td>" +
        team.points + "</td></tr>";
    }).join("");
  }

  function statisticsScreen() {
    const rows = leagueRows();
    if (!rows) return emptyState("League comparison is unavailable until live match records are imported.");
    const official = officialStandings().length > 0;
    return '<div class="welcome-row"><div><p class="section-kicker">' + (official ? "OFFICIAL PROVIDER TABLE" : "IMPORTED MATCH COMPARISON") + '</p><p class="muted">' +
      (official ? "Official football-data.org Serie A standings." : "Partial table from locally saved finished results; not official.") + '</p></div>' +
      '<span class="result-count">' + (official ? "FOOTBALL-DATA.ORG" : "LOCAL RECORDS") + '</span></div><section class="panel table-panel"><div class="panel-heading"><div><h2>' +
      (official ? "Serie A Standings" : "Team Comparison") + '</h2><p>' + (official ? "Played, results, goal difference and points" : "Ranked by points, goal difference, then goals") + '</p></div></div>' +
      '<div class="table-wrap"><table><thead><tr><th>#</th><th>Team</th><th>Played</th><th>W</th><th>D</th><th>L</th><th>GD</th><th>Points</th></tr></thead><tbody>' +
      rows + "</tbody></table></div></section>";
  }

  function savedScreen() {
    const items = state.savedMatches.filter(function (match) { return state.season === "all" || match.season === state.season; });
    const rows = matchRows(items, true);
    const outcomes = [0, 0, 0];
    items.forEach(function (match) {
      if (match.home_score == null || match.away_score == null) return;
      if (match.home_score > match.away_score) outcomes[0] += 1;
      else if (match.home_score === match.away_score) outcomes[1] += 1;
      else outcomes[2] += 1;
    });
    return (state.actionMessage ? '<p class="live-status" role="status">' + escapeHtml(state.actionMessage) + "</p>" : "") +
      '<div class="saved-layout"><section class="panel table-panel saved-table-panel"><div class="panel-heading"><div><h2>Your Collection</h2><p>' +
      items.length + " saved live matches · Season " + escapeHtml(activeSeason() || "unavailable") + '</p></div><span class="result-count">' + items.length + " SAVED</span></div>" +
      '<div class="table-wrap"><table><thead><tr><th>Date / Status</th><th>Home Team</th><th>Score</th><th>Away Team</th><th>Actions</th></tr></thead><tbody>' +
      (rows || '<tr><td class="empty-state" colspan="5">No saved live matches. Save a fixture from Matches.</td></tr>') + "</tbody></table></div></section>" +
      (outcomes.some(Boolean) ? '<section class="panel quick-analysis"><div class="panel-heading"><div><h2>Quick Analysis</h2><p>Saved match outcomes with known scores</p></div>' +
      icon("chart-pie", 17) + '</div><div class="donut-wrap"><canvas id="saved-chart" role="img" aria-label="Donut chart of saved live match outcomes"></canvas>' +
      '<div class="donut-center"><strong>' + items.length + '</strong><span>Saved</span></div></div><div class="legend-list">' +
      '<span><i class="legend-dot home-dot"></i> Home wins <b id="home-count">0</b></span><span><i class="legend-dot draw-dot"></i> Draws <b id="draw-count">0</b></span>' +
      '<span><i class="legend-dot away-dot"></i> Away wins <b id="away-count">0</b></span></div></section>' : '') + '</div>';
  }

  function aboutScreen() {
    return '<div class="about-hero panel"><div class="about-logo"><img src="assets/logo.svg" alt=""></div><div><p class="section-kicker">LOCAL LIVE-DATA APPLICATION</p>' +
      '<h2>Real records, carefully labeled.</h2><p>Official fixtures and standings come from football-data.org. Available match details come from Highlightly and preserved BigBallsData records, and are stored locally after approval. Missing values are never replaced with sample values.</p>' +
      '<span class="demo-tag">LIVE DATA · LOCAL DATABASE</span></div></div><div class="about-grid">' +
      '<article class="panel about-card"><span class="about-icon">' + icon("database", 19) + '</span><h3>Provider data</h3><p>Current-season fixtures and available match statistics only. API availability depends on the configured provider plan.</p></article>' +
      '<article class="panel about-card"><span class="about-icon">' + icon("shield-check", 19) + '</span><h3>Honest gaps</h3><p>Possession, shots, player contributions, and lineups remain unavailable unless a provider supplied and saved them.</p></article>' +
      '<article class="panel about-card"><span class="about-icon">' + icon("mouse-pointer-2", 19) + '</span><h3>Controlled refresh</h3><p>Opening pages reads SQLite only. Authenticated provider calls require an explicit confirmation, and are not automatically retried.</p></article></div>';
  }

  function pitchScreen() {
    const item = state.matchDetails;
    if (!item) return emptyState("Open a saved match before viewing its lineups.");
    if (!state.lineups) return emptyState(state.actionMessage || "Load stored lineup data from the match details page first.");
    const formations = window.SERIE_A_FORMATIONS;
    const byName = state.lineups.lineups || [];
    if (!formations) return emptyState("The local formation layout could not be loaded.");
    const allPlayers = [];
    byName.forEach(function (lineup) {
      ["starting_players", "substitutes_used", "unused_substitutes"].forEach(function (role) {
        (lineup[role] || []).forEach(function (player) {
          allPlayers.push({ player: player, teamName: lineup.team_name });
        });
      });
    });
    if (!allPlayers.length) {
      return '<div class="lineup-open-row"><button class="button button-secondary" data-action="back-detail">Back to match</button></div>' +
        emptyState(state.lineups.message || "No player lineup information is available for this match.");
    }
    const selected = allPlayers.find(function (entry) {
      return String(entry.player.id) === String(state.selectedPlayerId);
    });
    function indicators(player) {
      let html = "";
      if (player.rating != null) html += '<span class="lineup-indicator rating-indicator" title="Player rating">' + escapeHtml(player.rating) + "</span>";
      if (player.goals != null && player.goals > 0) html += '<span class="lineup-indicator goal-indicator" title="' + player.goals + ' goal(s)">G' + player.goals + "</span>";
      if (player.assists != null && player.assists > 0) html += '<span class="lineup-indicator assist-indicator" title="' + player.assists + ' assist(s)">A' + player.assists + "</span>";
      if (player.yellow_cards != null && player.yellow_cards > 0) html += '<span class="lineup-indicator card-indicator yellow-card" title="' + player.yellow_cards + ' yellow card(s)"></span>';
      if (player.red_cards != null && player.red_cards > 0) html += '<span class="lineup-indicator card-indicator red-card" title="' + player.red_cards + ' red card(s)"></span>';
      return html ? '<span class="pitch-indicators">' + html + "</span>" : "";
    }
    function selectPlayer(player, className, extraAttributes) {
      return '<button class="' + className + (String(player.id) === String(state.selectedPlayerId) ? " selected" : "") +
        '" data-action="select-player" data-player-id="' + escapeHtml(player.id) + '" aria-pressed="' +
        (String(player.id) === String(state.selectedPlayerId)) + '" title="View ' + escapeHtml(player.name) +
        ' details" ' + (extraAttributes || "") + ">";
    }
    function renderSide(teamName, side) {
      const lineup = byName.find(function (entry) { return entry.team_name === teamName; });
      if (!lineup) return '<div class="panel empty-state">Lineup not provided for ' + escapeHtml(teamName) + ".</div>";
      const positions = formations.getPitchPositions(lineup.formation);
      const hasFormation = positions.length === 11;
      const players = (lineup.starting_players || []).map(function (player, index) {
        const slot = Number(player.formation_slot);
        const positionIndex = Number.isInteger(slot) && slot >= 1 && slot <= 11 ? slot - 1 : index;
        const point = positions[positionIndex];
        if (!hasFormation) return selectPlayer(player, "substitute-player") + escapeHtml(player.name) + indicators(player) + "</button>";
        return selectPlayer(player, "pitch-player " + side, 'style="left:' + point.left + "%;top:" + point.top + '%"') +
          '<span class="pitch-shirt">' +
          escapeHtml(player.shirt_number == null ? "—" : player.shirt_number) + '</span><span class="pitch-name">' +
          escapeHtml(player.name) + '</span><span class="pitch-role">' + escapeHtml(player.position || point.role) +
          "</span>" + indicators(player) + "</button>";
      }).join("");
      return '<section class="panel detail-panel"><div class="panel-heading"><div><h2>' + escapeHtml(teamName) +
        '</h2><p>' + escapeHtml(lineup.formation || "Formation not supplied") + '</p></div></div>' + (hasFormation ? '<div class="football-pitch"><span class="pitch-halfway"></span><span class="pitch-center-circle"></span>' : '<p class="muted">Pitch positions are unavailable because no supported formation was supplied.</p><div class="substitute-list">') +
        players + "</div></section>";
    }
    function substituteList(teamName, role, heading) {
      const lineup = byName.find(function (entry) { return entry.team_name === teamName; });
      const players = lineup ? lineup[role] || [] : [];
      return '<section><div class="substitute-heading"><h3>' + escapeHtml(teamName) +
        '</h3><span>' + heading + "</span></div>" +
        (players.length ? '<div class="substitute-list">' + players.map(function (player) {
          return selectPlayer(player, "substitute-player") +
            '<span class="substitute-number">' + escapeHtml(player.shirt_number == null ? "—" : player.shirt_number) +
            '</span><span>' + escapeHtml(player.name) + '<br><small>' +
            (role === "substitutes_used" ? "Used · " + (player.minute_on == null ? "minute unavailable" : player.minute_on + "'") : (player.minutes_played === 0 ? "Unused" : "Usage not supplied")) +
            "</small></span>" + indicators(player) + "</button>";
        }).join("") + "</div>" : '<p class="muted">Not available.</p>') + "</section>";
    }
    const playerDetail = selected ? '<section class="panel player-detail"><p class="section-kicker">' +
      escapeHtml(selected.teamName) + " · " + escapeHtml(selected.player.player_role.replace(/_/g, " ")) +
      '</p><h3>' + escapeHtml(selected.player.name) + '</h3><p class="player-role-line">' +
      escapeHtml(selected.player.position || "Position not available") + " · No. " +
      escapeHtml(selected.player.shirt_number == null ? "Not available" : selected.player.shirt_number) +
      '</p><div class="player-stat-list">' +
      [["Rating", selected.player.rating], ["Minutes played", selected.player.minutes_played],
        ["Substitution on (minute)", selected.player.minute_on], ["Substitution off (minute)", selected.player.minute_off],
        ["Goals", selected.player.goals], ["Assists", selected.player.assists],
        ["Shots", selected.player.shots_total], ["Shots on target", selected.player.shots_on_target],
        ["Shots off target", selected.player.shots_off_target],
        ["Passes", selected.player.passes_total], ["Successful passes", selected.player.passes_successful],
        ["Pass accuracy", selected.player.passes_accuracy],
        ["Key passes", selected.player.passes_key], ["Tackles", selected.player.tackles_total],
        ["Interceptions", selected.player.interceptions_total],
        ["Dribbles", selected.player.dribbles_total], ["Successful dribbles", selected.player.dribbles_successful],
        ["Duels", selected.player.duels_total], ["Duels won", selected.player.duels_won],
        ["Fouls committed", selected.player.fouls_committed], ["Fouls drawn", selected.player.fouls_drawn],
        ["Saves", selected.player.goalkeeper_saves],
        ["Yellow cards", selected.player.yellow_cards], ["Red cards", selected.player.red_cards]]
        .filter(function (entry) { return entry[1] != null; })
        .map(function (entry) {
          return "<span>" + entry[0] + "<b>" + escapeHtml(entry[1] == null ? "Not available" : entry[1]) + "</b></span>";
        }).join("") + "</div></section>" :
      '<section class="panel player-detail player-detail-empty">Select a player on the pitch or from the substitutes to see saved provider statistics.</section>';
    return '<div class="lineup-open-row"><button class="button button-secondary" data-action="back-detail">Back to match</button></div>' +
      '<p class="lineup-footnote">Pitch locations are schematic and follow the supplied formation slots. Select a player for saved performance fields.</p>' +
      '<div class="lineups-grid">' + renderSide(item.home_team.name, "home") + renderSide(item.away_team.name, "away") +
      playerDetail + "</div><section class=\"panel substitutes-panel\"><div class=\"substitute-groups\">" +
      substituteList(item.home_team.name, "substitutes_used", "Used substitutes") +
      substituteList(item.away_team.name, "substitutes_used", "Used substitutes") +
      substituteList(item.home_team.name, "unused_substitutes", "Other substitutes") +
      substituteList(item.away_team.name, "unused_substitutes", "Other substitutes") +
      "</div></section>";
  }

  function content() {
    if (state.screen === "dashboard") return dashboard();
    if (state.screen === "matches") return matchesScreen();
    if (state.screen === "match") return detailScreen();
    if (state.screen === "teams") return teamsScreen();
    if (state.screen === "statistics") return statisticsScreen();
    if (state.screen === "saved") return savedScreen();
    if (state.screen === "lineup") return pitchScreen();
    return aboutScreen();
  }

  function render() {
    app.setAttribute("aria-busy", String(state.busy));
    if (state.chart) { state.chart.destroy(); state.chart = null; }
    if (state.screen === "landing") {
      app.innerHTML = '<main class="landing"><div class="landing-scrim"></div><header class="landing-top"><a href="#" class="landing-brand" data-action="navigate" data-screen="dashboard"><img src="assets/logo.svg" alt=""><span>TRACKER<br><b>SERIE A</b></span></a><span class="landing-demo">LIVE DATA · LOCAL DATABASE</span></header>' +
        '<div class="landing-content"><div class="hero-logo"><img src="assets/logo.svg" alt="Original geometric football tracker mark"></div><p class="eyebrow hero-eyebrow">SERIE A MATCH CENTER</p><h1>Serie A Match Statistics</h1><p class="hero-intro">Explore saved fixtures, results and available<br>post-match team statistics.</p><button class="button button-primary hero-button" data-action="navigate" data-screen="dashboard">Get Started <span>→</span></button>' +
        '<div class="feature-row"><div class="feature">' + icon("goal", 23) + "<span>Goals &amp; Assists</span></div><div class=\"feature\">" +
        icon("chart-no-axes-column-increasing", 23) + "<span>Match Statistics</span></div><div class=\"feature\">" +
        icon("database", 23) + "<span>SQLite Records</span></div><div class=\"feature\">" +
        icon("trending-up", 23) + "<span>Team Analysis</span></div></div></div><div class=\"landing-bottom\"><span>BUILT FOR THE BEAUTIFUL GAME</span><span>REAL PROVIDER RECORDS ONLY</span></div></main>";
    } else {
      app.innerHTML = shell(content());
    }
    if (window.lucide) window.lucide.createIcons();
    if (state.screen === "teams") renderTeamChart();
    if (state.screen === "saved") renderSavedChart();
  }

  function renderTeamChart() {
    const canvas = document.getElementById("team-chart");
    if (!canvas || !window.Chart) return;
    const record = teamRecord(state.team);
    const points = record.allMatches.slice().reverse().map(function (match) {
      return { match: match, isHome: match.home_team_name === state.team };
    });
    const metric = state.chartMetric;
    const data = points.map(function (entry) {
      const match = entry.match;
      const prefix = entry.isHome ? "home_" : "away_";
      if (metric === "goals") return entry.isHome ? match.home_score : match.away_score;
      if (metric === "points") {
        const own = entry.isHome ? match.home_score : match.away_score;
        const opponent = entry.isHome ? match.away_score : match.home_score;
        if (own == null || opponent == null) return null;
        return own > opponent ? 3 : own === opponent ? 1 : 0;
      }
      const key = metric === "target" ? "shots_on_target" : metric;
      return match.statistics ? match.statistics[prefix + key] : null;
    });
    state.chart = new Chart(canvas, {
      type: "line",
      data: { labels: points.map(function (entry) { return formatDate(entry.match.match_date); }), datasets: [{
        label: metric, data: data, spanGaps: false, borderColor: "#38a4ff",
        backgroundColor: "rgba(36,119,255,.18)", fill: true, tension: .25,
        pointRadius: 3, pointBackgroundColor: "#80dcff", borderWidth: 2
      }] },
      options: { maintainAspectRatio: false, responsive: true, plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false }, ticks: { color: "#8999b4", maxTicksLimit: 8 } },
          y: { grid: { color: "rgba(147,171,210,.09)" }, ticks: { color: "#8999b4" } } } }
    });
  }

  function renderSavedChart() {
    const canvas = document.getElementById("saved-chart");
    if (!canvas) return;
    const counts = [0, 0, 0];
    state.savedMatches.forEach(function (match) {
      if (state.season !== "all" && match.season !== state.season) return;
      if (match.home_score == null || match.away_score == null) return;
      if (match.home_score > match.away_score) counts[0] += 1;
      else if (match.home_score === match.away_score) counts[1] += 1;
      else counts[2] += 1;
    });
    ["home-count", "draw-count", "away-count"].forEach(function (id, index) {
      const element = document.getElementById(id);
      if (element) element.textContent = String(counts[index]);
    });
    if (!window.Chart) return;
    state.chart = new Chart(canvas, {
      type: "doughnut",
      data: { labels: ["Home wins", "Draws", "Away wins"], datasets: [{ data: counts,
        backgroundColor: ["#1683ff", "#59c8ed", "#ff5a69"], borderColor: "#0b172b", borderWidth: 4 }] },
      options: { maintainAspectRatio: false, cutout: "76%", plugins: { legend: { display: false } } }
    });
  }

  async function request(url, options) {
    let response;
    try {
      response = await fetch(url, options);
    } catch (_error) {
      throw new Error(
        "The local FastAPI server is unavailable. Start it with python main.py and try again."
      );
    }
    let body;
    try { body = await response.json(); } catch (_error) { body = {}; }
    if (!response.ok) throw new Error(body.detail || "The local server request failed.");
    return body;
  }

  async function refreshLocal() {
    state.loading = true;
    state.error = "";
    render();
    try {
      const results = await Promise.all([
        request("/api/matches?source=live"),
        request("/api/saved-matches"),
        request("/api/standings"),
        request("/api/data-coverage")
      ]);
      state.matches = results[0];
      state.savedMatches = results[1];
      state.standings = results[2];
      state.coverage = results[3];
      state.loading = false;
      state.error = "";
      render();
    } catch (error) {
      state.loading = false;
      state.error = error.message || "Could not load live records from SQLite.";
      render();
    }
  }

  async function loadMatch(id) {
    state.screen = "match";
    state.matchDetails = null;
    state.lineups = null;
    state.selectedPlayerId = null;
    state.detailLoading = true;
    state.error = "";
    state.detailTab = "overview";
    render();
    try {
      state.matchDetails = await request("/api/matches/" + encodeURIComponent(id));
    } catch (error) {
      state.error = error.message || "Could not load match details.";
    }
    state.detailLoading = false;
    render();
  }

  async function loadLineups() {
    if (!state.matchDetails) return;
    state.actionMessage = "Loading saved lineup data…";
    render();
    try {
      state.lineups = await request("/api/matches/" + state.matchDetails.id + "/lineups");
      state.actionMessage = state.lineups.message || "";
    } catch (error) {
      state.actionMessage = error.message || "Could not load saved lineups.";
    }
    render();
  }

  async function post(url, body) {
    return request(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  async function importStatistics(_refresh, _approved) {
    if (!state.matchDetails) return;
    await prepareSync({ match_ids: [state.matchDetails.id], categories: ["statistics"], max_matches: 1, max_requests: 2 });
  }

  async function toggleSaved(id, remove) {
    try {
      if (remove) {
        await request("/api/saved-matches/" + encodeURIComponent(id), { method: "DELETE" });
      } else {
        await post("/api/saved-matches", { match_id: Number(id) });
      }
      state.savedMatches = await request("/api/saved-matches");
      render();
    } catch (error) {
      state.actionMessage = error.message || "Could not update saved matches.";
      render();
    }
  }

  async function importLineups() {
    if (!state.matchDetails) return;
    await prepareSync({ match_ids: [state.matchDetails.id], categories: ["lineups"], max_matches: 1, max_requests: 2 });
  }

  async function importPlayerDetails() {
    if (!state.matchDetails) return;
    await prepareSync({ match_ids: [state.matchDetails.id], categories: ["box-score", "events"], max_matches: 1, max_requests: 2 });
  }

  async function prepareSync(options) {
    if (state.busy) return;
    const season = state.matchDetails && options.match_ids ? state.matchDetails.season : activeSeason();
    if (!season) { state.actionMessage = "Import official fixtures before requesting match details."; render(); return; }
    state.busy = true;
    state.actionMessage = "Checking saved coverage and quota metadata...";
    state.pendingApproval = null;
    render();
    try {
      const body = Object.assign({ season: Number(season) }, options);
      const plan = await post("/api/highlightly/plan", body);
      const budget = Math.min(options.max_requests, plan.recommended_budget);
      const names = plan.matches.map(function (match) { return match.home + " vs " + match.away; }).join("; ");
      const blocked = plan.matches.some(function (match) { return match.blocked_categories.length; });
      if (!plan.matches.length || (!budget && !plan.matches.some(function (m) { return m.cached_categories.length; }))) {
        state.actionMessage = plan.quota.remaining === 0 ? "The last saved quota is exhausted. No request was sent." :
          "No new requests are ready. Saved data is reused; unavailable categories are skipped.";
      } else if (blocked) {
        state.actionMessage = "An earlier request failed or was interrupted. Its saved status needs review before another request for that category.";
      } else {
        state.pendingApproval = { type: "highlightly-sync", body: Object.assign({}, body, {
          match_ids: plan.matches.map(function (match) { return match.match_id; }), max_requests: budget
        }), message: "Authorize up to " + budget + " Highlightly requests for " + names +
          "? Categories: " + body.categories.join(", ") + ". " +
          (plan.quota.remaining == null ? "Current RapidAPI quota is unknown; check the dashboard before approving." :
            "Last observed quota: " + plan.quota.remaining + " requests (" + formatTimestamp(plan.quota.observed_at) + ").") +
          " Saved and unavailable categories are skipped. This approval covers one batch only." };
        state.actionMessage = "Review the batch below. No authenticated request has been sent.";
      }
    } catch (error) { state.actionMessage = error.message; }
    finally { state.busy = false; render(); }
  }

  async function syncHighlightly(approved) {
    if (!approved) {
      const matches = document.getElementById("highlightly-max-matches");
      const requests = document.getElementById("highlightly-max-requests");
      const events = document.getElementById("highlightly-include-events");
      const categories = ["statistics", "lineups", "box-score"];
      if (events && events.checked) categories.push("events");
      await prepareSync({ max_matches: Math.min(10, Math.max(1, Number(matches && matches.value) || 1)),
        max_requests: Math.min(40, Math.max(1, Number(requests && requests.value) || 5)), categories: categories });
      return;
    }
    if (!state.pendingApproval || state.busy) return;
    const body = Object.assign({}, state.pendingApproval.body, { confirmed: true });
    const selectedMatch = state.matchDetails && state.matchDetails.id;
    state.pendingApproval = null;
    state.busy = true;
    state.actionMessage = "Saving the approved batch. Please keep this window open...";
    render();
    try {
      const result = await post("/api/highlightly/sync", body);
      state.actionMessage = "Saved batch: " + result.processed_matches + " matches, " + result.requests_used + " requests." +
        (result.stopped_reason ? " " + result.stopped_reason : "");
      if (selectedMatch) {
        state.matchDetails = await request("/api/matches/" + selectedMatch);
        state.lineups = await request("/api/matches/" + selectedMatch + "/lineups");
      }
      await refreshLocal();
    } catch (error) { state.actionMessage = error.message; }
    finally { state.busy = false; render(); }
  }

  app.addEventListener("click", function (event) {
    const target = event.target.closest("[data-action]");
    if (!target || state.busy) return;
    const action = target.dataset.action;
    if (action === "approve-request") {
      const approval = state.pendingApproval;
      if (!approval) return;
      if (approval.type === "statistics") importStatistics(false, true);
      else if (approval.type === "lineups") importLineups(true);
      else if (approval.type === "player-details") importPlayerDetails(true);
      else if (approval.type === "highlightly-sync") syncHighlightly(true);
    } else if (action === "cancel-request") {
      state.pendingApproval = null;
      render();
    } else if (action === "navigate") {
      event.preventDefault();
      state.screen = target.dataset.screen;
      state.actionMessage = "";
      state.pendingApproval = null;
      if (target.dataset.screen !== "matches") {
        state.search = "";
        state.round = "all";
      }
      render();
    } else if (action === "menu") {
      document.querySelector(".sidebar").classList.toggle("sidebar-open");
    } else if (action === "refresh-local") {
      refreshLocal();
    } else if (action === "view-match") {
      loadMatch(target.dataset.id);
    } else if (action === "save-match" || action === "remove-save") {
      toggleSaved(target.dataset.id, action === "remove-save");
    } else if (action === "detail-tab") {
      state.detailTab = target.dataset.tab;
      if (state.detailTab === "lineups" && !state.lineups) loadLineups();
      else render();
    } else if (action === "load-lineups") {
      loadLineups();
    } else if (action === "import-lineups") {
      importLineups(false);
    } else if (action === "import-player-details") {
      importPlayerDetails(false);
    } else if (action === "sync-highlightly") {
      syncHighlightly(false);
    } else if (action === "open-pitch") {
      state.screen = "lineup";
      if (!state.lineups) loadLineups();
      else render();
    } else if (action === "back-detail") {
      state.screen = "match";
      render();
    } else if (action === "select-player") {
      state.selectedPlayerId = target.dataset.playerId;
      state.screen = "lineup";
      render();
    } else if (action === "import-statistics" || action === "refresh-statistics") {
      importStatistics(action === "refresh-statistics", false);
    } else if (action === "chart-tab") {
      state.chartMetric = target.dataset.metric;
      render();
    }
  });

  app.addEventListener("change", function (event) {
    const target = event.target;
    if (target.dataset.change === "season") {
      state.season = target.value;
      if (!availableRounds().includes(state.round)) state.round = "all";
      render();
    } else if (target.dataset.change === "round") {
      state.round = target.value;
      render();
    } else if (target.dataset.change === "status") {
      state.matchStatus = target.value;
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
      if (!availableRounds().includes(state.round)) state.round = "all";
      const contentElement = document.querySelector(".page-content");
      contentElement.innerHTML = matchesScreen();
      if (window.lucide) window.lucide.createIcons();
      const search = document.querySelector('[data-input="search"]');
      search.focus();
      search.setSelectionRange(cursor, cursor);
    }
  });

  render();
  refreshLocal();
}());
