function esc(s) {
  var v = String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
  return v;
}
let trackedPlayerIds = [],
  currentBoxscoreOffset = 0,
  currentLeadersOffset = 0;
const _abortControllers = {};
function _fetchWithAbort(t, e, s = {}, a = 15e3) {
  _abortControllers[t] && _abortControllers[t].abort();
  const n = new AbortController();
  _abortControllers[t] = n;
  const i = setTimeout(() => n.abort(), a);
  return fetch(e, { ...s, signal: n.signal }).finally(() => clearTimeout(i));
}
const TEAM_TZ = {
  ATL: "America/New_York",
  BOS: "America/New_York",
  BKN: "America/New_York",
  CHA: "America/New_York",
  CHI: "America/Chicago",
  CLE: "America/New_York",
  DAL: "America/Chicago",
  DEN: "America/Denver",
  DET: "America/Detroit",
  GSW: "America/Los_Angeles",
  HOU: "America/Chicago",
  IND: "America/Indiana/Indianapolis",
  LAC: "America/Los_Angeles",
  LAL: "America/Los_Angeles",
  MEM: "America/Chicago",
  MIA: "America/New_York",
  MIL: "America/Chicago",
  MIN: "America/Chicago",
  NOP: "America/Chicago",
  NYK: "America/New_York",
  OKC: "America/Chicago",
  ORL: "America/New_York",
  PHI: "America/New_York",
  PHX: "America/Phoenix",
  POR: "America/Los_Angeles",
  SAC: "America/Los_Angeles",
  SAS: "America/Chicago",
  TOR: "America/Toronto",
  UTA: "America/Denver",
  WAS: "America/New_York",
};
function homeTeamLocalTime(t) {
  const e = TEAM_TZ[t];
  return e
    ? new Date().toLocaleTimeString("en-US", {
        timeZone: e,
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
}
function isGameLive(t) {
  return /^(Q[1-4]|OT|Halftime|HALF|End of)/i.test(t.trim());
}
const STAT_TIERS = {
  points: [30, 20, 15],
  rebounds: [15, 10, 7],
  assists: [15, 10, 7],
  steals: [4, 3, 2],
  blocks: [4, 3, 2],
};
function statClass(t, e) {
  const s = STAT_TIERS[t];
  return !s || e <= 0
    ? ""
    : e >= s[0]
      ? "stat-elite"
      : e >= s[1]
        ? "stat-great"
        : e >= s[2]
          ? "stat-good"
          : "";
}
function _dateLabel(t) {
  const e = new Date();
  return (
    e.setDate(e.getDate() - t),
    e.toLocaleDateString("en-US", { month: "short", day: "numeric" })
  );
}
function _loadDateLabels() {
  fetch("/api/dates")
    .then((t) => t.json())
    .then((t) => {
      const e = (t) => {
        const e = new Date(t);
        return isNaN(e)
          ? t
          : e.toLocaleDateString("en-US", { month: "short", day: "numeric" });
      };
      _boxscoreDateBtns.forEach((s) => {
        const a = t.dates[parseInt(s.dataset.offset)];
        if (a) s.textContent = e(a);
        if (t.hasGames && !t.hasGames[parseInt(s.dataset.offset)])
          s.hidden = true;
      });
      _leaderDateBtns.forEach((s) => {
        const a = t.dates[parseInt(s.dataset.offset)];
        if (a) s.textContent = e(a);
        if (t.hasGames && !t.hasGames[parseInt(s.dataset.offset)])
          s.hidden = true;
      });
      if (t.hasGames) {
        const firstBox = _boxscoreDateBtns.find((b) => !b.hidden);
        if (
          firstBox &&
          _boxscoreDateBtns.find(
            (b) => b.classList.contains("active") && b.hidden,
          )
        )
          firstBox.click();
        const firstLeader = _leaderDateBtns.find((b) => !b.hidden);
        if (
          firstLeader &&
          _leaderDateBtns.find(
            (b) => b.classList.contains("active") && b.hidden,
          )
        )
          firstLeader.click();
      }
    })
    .catch(() => {});
}
const _TEAM_CODES = {
    hawks: "ATL",
    celtics: "BOS",
    nets: "BKN",
    hornets: "CHA",
    bulls: "CHI",
    cavaliers: "CLE",
    mavericks: "DAL",
    nuggets: "DEN",
    pistons: "DET",
    warriors: "GSW",
    rockets: "HOU",
    pacers: "IND",
    clippers: "LAC",
    lakers: "LAL",
    grizzlies: "MEM",
    heat: "MIA",
    bucks: "MIL",
    timberwolves: "MIN",
    pelicans: "NOP",
    knicks: "NYK",
    thunder: "OKC",
    magic: "ORL",
    "76ers": "PHI",
    suns: "PHX",
    "trail blazers": "POR",
    kings: "SAC",
    spurs: "SAS",
    raptors: "TOR",
    jazz: "UTA",
    wizards: "WAS",
    atlanta: "ATL",
    boston: "BOS",
    brooklyn: "BKN",
    charlotte: "CHA",
    chicago: "CHI",
    cleveland: "CLE",
    dallas: "DAL",
    denver: "DEN",
    detroit: "DET",
    "golden st.": "GSW",
    houston: "HOU",
    indiana: "IND",
    "l.a. clippers": "LAC",
    "l.a. lakers": "LAL",
    memphis: "MEM",
    miami: "MIA",
    milwaukee: "MIL",
    minnesota: "MIN",
    "new orleans": "NOP",
    "new york": "NYK",
    "oklahoma city": "OKC",
    orlando: "ORL",
    philadelphia: "PHI",
    phoenix: "PHX",
    portland: "POR",
    sacramento: "SAC",
    "san antonio": "SAS",
    toronto: "TOR",
    utah: "UTA",
    washington: "WAS",
  },
  _RETURN_DATE_RE = /Jan \d+|Feb \d+|Mar \d+|Apr \d+|May \d+/i,
  _navTabs = Array.from(document.querySelectorAll(".nav-tab[data-section]")),
  _sections = Array.from(document.querySelectorAll(".section"));
document.querySelectorAll(".nav-tab").forEach((t) => {
  t.addEventListener("click", () => {
    if (t.dataset.section)
      switch (
        (_navTabs.forEach((t) => t.classList.remove("active")),
        _sections.forEach((t) => t.classList.remove("active")),
        t.classList.add("active"),
        document.getElementById(t.dataset.section).classList.add("active"),
        t.dataset.section)
      ) {
        case "scoreboard":
          loadScoreboard();
          break;
        case "boxscores":
          loadBoxscores();
          break;
        case "leaders":
          loadLeaders();
          break;
        case "standings":
          loadStandings();
          break;
        case "injuries":
          loadInjuries();
          break;
        case "playoffs":
          loadPlayoffs();
          break;
        case "trades":
          loadTrades();
          break;
        case "seasonDoubles":
          loadSeasonDoubles();
          break;
        case "seasonHighs":
          loadSeasonHighs();
      }
  });
});
const _boxscoreDateBtns = Array.from(
  document.querySelectorAll("#boxscores .date-btn"),
);
_boxscoreDateBtns.forEach((t) => {
  ((t.textContent = _dateLabel(parseInt(t.dataset.offset))),
    t.addEventListener("click", () => {
      (_boxscoreDateBtns.forEach((t) => t.classList.remove("active")),
        t.classList.add("active"),
        (currentBoxscoreOffset = parseInt(t.dataset.offset)),
        loadBoxscores());
    }));
});
const _leaderDateBtns = Array.from(
  document.querySelectorAll("#leadersDateSelector .date-btn"),
);
function initPlayerSearch(t, e, s, a) {
  const n = document.getElementById(t),
    i = document.getElementById(e);
  let l,
    r = -1;
  function o() {
    return Array.from(i.querySelectorAll(".search-result-item[data-id]"));
  }
  function d(t) {
    t &&
      t.dataset.id &&
      (s(parseInt(t.dataset.id), t.dataset.name),
      (n.value = ""),
      i.classList.remove("show"),
      (r = -1));
  }
  (n.addEventListener("keydown", (t) => {
    const e = i.classList.contains("show");
    if ("ArrowDown" === t.key || "ArrowUp" === t.key) {
      if ((t.preventDefault(), !e)) return;
      const s = o();
      !(function (t, e) {
        (e.forEach((t) => t.classList.remove("active")),
          (r = t < 0 || t >= e.length ? -1 : t),
          r >= 0 &&
            (e[r].classList.add("active"),
            e[r].scrollIntoView({ block: "nearest" })));
      })(
        "ArrowDown" === t.key
          ? Math.min(r + 1, s.length - 1)
          : Math.max(r - 1, 0),
        s,
      );
    } else if ("Enter" === t.key) {
      if ((t.preventDefault(), e)) {
        const t = o();
        d(r >= 0 ? t[r] : t[0]);
      } else if (a) {
        const t = document.getElementById(a);
        t && !t.disabled && t.click();
      }
    } else "Escape" === t.key && (i.classList.remove("show"), (r = -1));
  }),
    n.addEventListener("input", () => {
      ((r = -1), clearTimeout(l));
      const e = n.value.trim();
      e.length < 2
        ? i.classList.remove("show")
        : (l = setTimeout(async () => {
            try {
              const s = await _fetchWithAbort(
                "search_" + t,
                `/api/players/search?q=${encodeURIComponent(e)}`,
              );
              if (!s.ok) throw new Error("Search failed");
              const a = await s.json();
              ((i.innerHTML =
                0 === a.players.length
                  ? '<div class="search-result-item">No players found</div>'
                  : a.players
                      .map(
                        (t) =>
                          `\n                                <div class="search-result-item" data-id="${t.id}" data-name="${esc(t.name)}">\n                                    <span>${esc(t.name)}</span>\n                                    <span style="color: var(--text-secondary); font-size: 0.85rem;">ID: ${t.id}</span>\n                                </div>\n                            `,
                      )
                      .join("")),
                i.classList.add("show"));
            } catch (t) {
              ((i.innerHTML =
                '<div class="search-result-item">Error searching</div>'),
                i.classList.add("show"));
            }
          }, 300));
    }),
    i.addEventListener("click", (t) => {
      d(t.target.closest(".search-result-item"));
    }),
    document.addEventListener("click", (t) => {
      n.contains(t.target) ||
        i.contains(t.target) ||
        (i.classList.remove("show"), (r = -1));
    }));
}
function addTrackedPlayer(t, e) {
  trackedPlayerIds.find((e) => e.id === t) ||
    (trackedPlayerIds.push({ id: t, name: e }), updateTrackedPlayersUI());
}
function removeTrackedPlayer(t) {
  ((trackedPlayerIds = trackedPlayerIds.filter((e) => e.id !== t)),
    updateTrackedPlayersUI());
}
function updateTrackedPlayersUI() {
  const t = document.getElementById("trackedPlayers"),
    e = document.getElementById("trackBtn");
  ((t.innerHTML = trackedPlayerIds
    .map(
      (t) =>
        `\n                <div class="player-chip">\n                    <span>${esc(t.name)}</span>\n                    <button class="player-chip-remove" aria-label="Remove player" data-action="removeTracked" data-player-id="${t.id}">&times;</button>\n                </div>\n            `,
    )
    .join("")),
    (e.disabled = 0 === trackedPlayerIds.length));
}
async function loadTrackedStats() {
  if (0 === trackedPlayerIds.length) return;
  const t = document.getElementById("trackerContent");
  t.innerHTML =
    '<div class="loading"><div class="spinner"></div> Loading player stats...</div>';
  try {
    const e = trackedPlayerIds.map((t) => t.id).join(","),
      s = await _fetchWithAbort("trackedStats", `/api/players/stats?ids=${e}`),
      a = await s.json();
    if (0 === a.players.length)
      return void (t.innerHTML =
        '\n                        <div class="empty-state">\n                            <div class="empty-state-icon">&#128564;</div>\n                            <div class="empty-state-title">No Active Games</div>\n                            <p>Selected players don\'t have games in progress today</p>\n                        </div>\n                    ');
    t.innerHTML = `\n                    <div class="card" style="overflow-x: auto;">\n                        <table class="player-stats-table">\n                            <thead>\n                                <tr>\n                                    <th>Player</th>\n                                    <th>Team</th>\n                                    <th>MIN</th>\n                                    <th>PTS</th>\n                                    <th>FG</th>\n                                    <th>3P</th>\n                                    <th>FT</th>\n                                    <th>REB</th>\n                                    <th>AST</th>\n                                    <th>BLK</th>\n                                    <th>STL</th>\n                                    <th>PF</th>\n                                </tr>\n                            </thead>\n                            <tbody>\n                                ${a.players.map((t) => `\n                                    <tr>\n                                        <td><strong>${esc(t.name)}</strong></td>\n                                        <td>${esc(t.team)}</td>\n                                        <td>${t.minutes}</td>\n                                        <td class="${statClass("points", t.points)}">${t.points}</td>\n                                        <td>${t.fg}</td>\n                                        <td>${t.threePointers}</td>\n                                        <td>${t.ft}</td>\n                                        <td class="${statClass("rebounds", t.rebounds)}">${t.rebounds}</td>\n                                        <td class="${statClass("assists", t.assists)}">${t.assists}</td>\n                                        <td class="${statClass("blocks", t.blocks)}">${t.blocks}</td>\n                                        <td class="${statClass("steals", t.steals)}">${t.steals}</td>\n                                        <td>${t.fouls}</td>\n                                    </tr>\n                                `).join("")}\n                            </tbody>\n                        </table>\n                    </div>\n                `;
  } catch (e) {
    t.innerHTML = `\n                    <div class="empty-state">\n                        <div class="empty-state-icon">&#9888;</div>\n                        <div class="empty-state-title">Error Loading Stats</div>\n                        <p>${esc(e.message)}</p>\n                    </div>\n                `;
  }
}
async function toggleGameDetails(t, e) {
  const s = document.getElementById(`details-${t}`);
  if ("block" !== s.style.display) {
    ((s.innerHTML =
      '<div class="loading" style="padding: 20px;"><div class="spinner"></div> Loading player stats...</div>'),
      (s.style.display = "block"));
    try {
      const e = await _fetchWithAbort(
          "gameDetails_" + t,
          `/api/games/${t}/players`,
        ),
        a = await e.json();
      s.innerHTML = a.teams
        .map((t) => {
          const e = t.players.filter(
            (t) => "0:00" !== t.minutes && "0" !== t.minutes && 0 !== t.minutes,
          );
          return `\n                    <div style="padding: 8px; border-top: 1px solid var(--border);">\n                        <h4 style="margin-bottom: 6px; color: var(--accent); font-size: 0.75rem;">${esc(t.name)} - ${esc(t.score)}</h4>\n                        <table class="boxscore-table" style="font-size: 0.72rem;">\n                            <thead>\n                                <tr>\n                                    <th style="text-align: left;">Player</th>\n                                    <th>MIN</th>\n                                    <th>PTS</th>\n                                    <th>REB</th>\n                                    <th>AST</th>\n                                    <th>FG</th>\n                                    <th>3PT</th>\n                                    <th>FT</th>\n                                    <th>STL</th>\n                                    <th>BLK</th>\n                                    <th>TO</th>\n                                </tr>\n                            </thead>\n                            <tbody>\n                                ${e.map((t) => `\n                                    <tr>\n                                        <td style="text-align: left; white-space: nowrap;">${esc(t.name)}</td>\n                                        <td>${t.minutes}</td>\n                                        <td class="${statClass("points", t.points)}">${t.points}</td>\n                                        <td class="${statClass("rebounds", t.rebounds)}">${t.rebounds}</td>\n                                        <td class="${statClass("assists", t.assists)}">${t.assists}</td>\n                                        <td>${t.fg}</td>\n                                        <td>${t.threePt}</td>\n                                        <td>${t.ft}</td>\n                                        <td class="${statClass("steals", t.steals)}">${t.steals}</td>\n                                        <td class="${statClass("blocks", t.blocks)}">${t.blocks}</td>\n                                        <td>${t.turnovers}</td>\n                                    </tr>\n                                `).join("")}\n                            </tbody>\n                        </table>\n                    </div>`;
        })
        .join("");
    } catch (t) {
      s.innerHTML = `<div style="padding: 20px; color: var(--text-secondary);">Error loading player stats</div>`;
    }
  } else s.style.display = "none";
}
let _standingsData = null;
function renderStandings() {
  const t = document.getElementById("standingsContent");
  const a = (t, e) =>
    `\n                    <div class="card" style="overflow-x: auto;">\n                        <h3 style="padding: 15px 20px; background: var(--bg-secondary); margin: 0;">${e} Conference</h3>\n                        <table class="boxscore-table">\n                            <thead>\n                                <tr>\n                                    <th>#</th>\n                                    <th style="text-align: left;">Team</th>\n                                    <th>W</th>\n                                    <th>L</th>\n                                    <th>PCT</th>\n                                    <th>GB</th>\n                                    <th>Streak</th>\n                                    <th>L10</th>\n                                </tr>\n                            </thead>\n                            <tbody>\n                                ${t.map((t, e) => `\n                                    <tr class="${e < 6 ? "playoff-row" : e < 10 ? "playin-row" : ""}">\n                                        <td style="text-align: center; font-weight: 600;">${t.rank}</td>\n                                        <td style="text-align: left; font-weight: 500;">${esc(t.name)}</td>\n                                        <td class="highlight">${t.wins}</td>\n                                        <td>${t.losses}</td>\n                                        <td>${(100 * t.winPct).toFixed(1)}%</td>\n                                        <td>${esc(t.gamesBack)}</td>\n                                        <td>${esc(t.streak)}</td>\n                                        <td>${esc(t.last10)}</td>\n                                    </tr>\n                                `).join("")}\n                            </tbody>\n                        </table>\n                    </div>\n                `;
  try {
    t.innerHTML =
      a(_standingsData.east, "Eastern") + a(_standingsData.west, "Western");
  } catch (e) {
    t.innerHTML = `\n                    <div class="empty-state">\n                        <div class="empty-state-icon">&#9888;</div>\n                        <div class="empty-state-title">Error Loading Standings</div>\n                        <p>${esc(e.message)}</p>\n                    </div>\n                `;
    t.innerHTML =
      a(_standingsData.east, "Eastern") + a(_standingsData.west, "Western");
  }
}
async function loadStandings(force = false) {
  if (_standingsData && !force) {
    renderStandings();
    return;
  }
  const t = document.getElementById("standingsContent");
  t.innerHTML =
    '<div class="loading"><div class="spinner"></div> Loading standings...</div>';
  try {
    const e = await _fetchWithAbort("standings", "/api/standings");
    _standingsData = await e.json();
    renderStandings();
  } catch (e) {
    t.innerHTML = `\n                    <div class="empty-state">\n                        <div class="empty-state-icon">&#9888;</div>\n                        <div class="empty-state-title">Error Loading Standings</div>\n                        <p>${esc(e.message)}</p>\n                    </div>\n                `;
  }
}
(_leaderDateBtns.forEach((t) => {
  ((t.textContent = _dateLabel(parseInt(t.dataset.offset))),
    t.addEventListener("click", () => {
      (_leaderDateBtns.forEach((t) => t.classList.remove("active")),
        t.classList.add("active"),
        (currentLeadersOffset = parseInt(t.dataset.offset)),
        loadLeaders());
    }));
}),
  _loadDateLabels(),
  initPlayerSearch(
    "playerSearch",
    "searchResults",
    (t, e) => {
      addTrackedPlayer(t, e);
    },
    "trackBtn",
  ));
let injuriesData = null,
  injuriesView = "list";
function setInjuriesView(t) {
  ((injuriesView = t),
    document
      .getElementById("injuriesListBtn")
      .classList.toggle("active", "list" === t),
    document
      .getElementById("injuriesGroupBtn")
      .classList.toggle("active", "grouped" === t),
    injuriesData && renderInjuries());
}
let lastNSelectedPlayer = null,
  lastNGamesCount = 5;
const _lastNDateBtns = Array.from(
  document.querySelectorAll("#lastngames .date-btn[data-n]"),
);
async function loadLastNGames() {
  if (!lastNSelectedPlayer) return;
  const t = document.getElementById("lastNContent");
  t.innerHTML =
    '<div class="loading"><div class="spinner"></div> Loading game log...</div>';
  try {
    const [e, s] = await Promise.all([
        _fetchWithAbort(
          "lastNGames",
          `/api/players/${lastNSelectedPlayer.id}/last-n-games?n=${lastNGamesCount}`,
        ),
        _fetchWithAbort(
          "lastNSeasonAvg",
          `/api/players/${lastNSelectedPlayer.id}/season-avg`,
        ),
      ]),
      a = await e.json(),
      n = s.ok ? await s.json() : null;
    if (!a.games || 0 === a.games.length)
      return void (t.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon">&#128564;</div>
                            <div class="empty-state-title">No Games Found</div>
                            <p>No recent game data available for ${esc(a.playerName)}</p>
                        </div>
                    `);

    const played = a.games.filter((g) => !g.dnp);
    const avgNum = (key) => {
      if (!played.length) return "0.0";
      return (
        played.reduce((sum, g) => sum + (Number(g[key]) || 0), 0) /
        played.length
      ).toFixed(1);
    };
    const avgMinutes = () => {
      if (!played.length) return "0.0";
      const toMinutes = (value) => {
        if (value == null) return 0;
        if (typeof value === "number") return value;
        const txt = String(value).trim();
        const m = txt.match(/^(\d+):(\d+)$/);
        if (m) {
          const mins = Number(m[1]) || 0;
          const secs = Number(m[2]) || 0;
          return mins + secs / 60;
        }
        return Number(txt) || 0;
      };
      return (
        played.reduce((sum, g) => sum + toMinutes(g.minutes), 0) / played.length
      ).toFixed(1);
    };
    const avgPair = (key) => {
      if (!played.length) return "-";
      let made = 0,
        attempt = 0,
        count = 0;
      played.forEach((g) => {
        const raw = g[key];
        const m = String(raw ?? "").match(/^(\d+)\s*[\/-]\s*(\d+)$/);
        if (m) {
          made += Number(m[1]) || 0;
          attempt += Number(m[2]) || 0;
          count += 1;
        }
      });
      if (!count) return "-";
      return `${(made / count).toFixed(1)}-${(attempt / count).toFixed(1)}`;
    };
    const pairPct = (value) => {
      const m = String(value ?? "").match(/^(\d+)\s*[\/-]\s*(\d+)$/);
      if (!m) return "-";
      const made = Number(m[1]) || 0;
      const attempt = Number(m[2]) || 0;
      if (!attempt) return "0.0%";
      return `${((made / attempt) * 100).toFixed(1)}%`;
    };
    const avgPairPct = (key) => {
      if (!played.length) return "-";
      let made = 0,
        attempt = 0,
        count = 0;
      played.forEach((g) => {
        const raw = g[key];
        const m = String(raw ?? "").match(/^(\d+)\s*[\/-]\s*(\d+)$/);
        if (m) {
          made += Number(m[1]) || 0;
          attempt += Number(m[2]) || 0;
          count += 1;
        }
      });
      if (!count || !attempt) return "0.0%";
      return `${((made / attempt) * 100).toFixed(1)}%`;
    };
    const pct1 = (value) => {
      let n = Number(value);
      if (!Number.isFinite(n)) return "-";
      if (n <= 1) n *= 100;
      return `${n.toFixed(1)}%`;
    };

    t.innerHTML = `
                    <div style="margin-bottom: 8px; color: var(--text-secondary); font-size: 0.85rem;">
                        ${played.length} games played of ${a.games.length} shown
                    </div>
                    <div class="card lastn-table-wrap">
                        <table class="player-stats-table">
                            <thead>
                                <tr>
                                    <th>Matchup</th>
                                    <th>MIN</th>
                                    <th>PTS</th>
                                    <th>FG</th>
                                    <th>3P</th>
                                    <th>FT</th>
                                    <th>REB</th>
                                    <th>AST</th>
                                    <th>BLK</th>
                                    <th>STL</th>
                                    <th>PF</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${a.games
                                  .map((g) =>
                                    g.dnp
                                      ? `
                                    <tr class="dnp-row">
                                        <td>${esc(g.matchup)}</td>
                                        <td colspan="10" class="dnp-cell">DNP</td>
                                    </tr>
                                `
                                      : `
                                    <tr>
                                        <td>${esc(g.matchup)}</td>
                                        <td>${g.minutes}</td>
                                        <td class="${statClass("points", g.points)}">${g.points}</td>
                                        <td>${g.fg}</td>
                                        <td>${g.threePointers}</td>
                                        <td>${g.ft}</td>
                                        <td class="${statClass("rebounds", g.rebounds)}">${g.rebounds}</td>
                                        <td class="${statClass("assists", g.assists)}">${g.assists}</td>
                                        <td class="${statClass("blocks", g.blocks)}">${g.blocks}</td>
                                        <td class="${statClass("steals", g.steals)}">${g.steals}</td>
                                        <td>${g.fouls}</td>
                                    </tr>
                                `,
                                  )
                                  .join("")}
                                ${
                                  n
                                    ? `
                                <tr style="border-top: 2px solid var(--accent); background: var(--bg-secondary); font-weight: 600;">
                                    <td style="text-align: left; white-space: nowrap;">
                                        <span style="color: var(--accent); font-size: 0.75rem;">${n.season}</span>
                                        <span style="color: var(--text-secondary); font-size: 0.7rem; margin-left: 4px;">(${n.gp} games)</span>
                                    </td>
                                    <td style="color: var(--text-secondary);">${n.minutes}</td>
                                    <td class="highlight">${n.points}</td>
                                    <td style="color: var(--text-secondary); font-size: 0.8rem;">${pct1(n.fgPct)}</td>
                                    <td style="color: var(--text-secondary); font-size: 0.8rem;">${pct1(n.fg3Pct)}</td>
                                    <td style="color: var(--text-secondary); font-size: 0.8rem;">${pct1(n.ftPct)}</td>
                                    <td>${n.rebounds}</td>
                                    <td>${n.assists}</td>
                                    <td>${n.blocks}</td>
                                    <td>${n.steals}</td>
                                    <td style="color: var(--text-secondary);">${n.fouls}</td>
                                </tr>`
                                    : ""
                                }
                                <tr style="background: var(--bg-secondary); border-top: 1px solid var(--border);">
                                    <td style="text-align: left; white-space: nowrap; color: var(--text-primary); font-weight: 600;">Last ${played.length} Games Average</td>
                                    <td>${avgMinutes()}</td>
                                    <td class="highlight">${avgNum("points")}</td>
                                    <td>${avgPairPct("fg")}</td>
                                    <td>${avgPairPct("threePointers")}</td>
                                    <td>${avgPairPct("ft")}</td>
                                    <td>${avgNum("rebounds")}</td>
                                    <td>${avgNum("assists")}</td>
                                    <td>${avgNum("blocks")}</td>
                                    <td>${avgNum("steals")}</td>
                                    <td>${avgNum("fouls")}</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                `;
  } catch (e) {
    t.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">&#9888;</div>
                        <div class="empty-state-title">Error Loading Stats</div>
                        <p>Error loading stats</p>
                    </div>
                `;
  }
}
(_lastNDateBtns.forEach((t) => {
  t.addEventListener("click", () => {
    (_lastNDateBtns.forEach((t) => t.classList.remove("active")),
      t.classList.add("active"),
      (lastNGamesCount = parseInt(t.dataset.n)));
  });
}),
  initPlayerSearch(
    "lastNSearch",
    "lastNSearchResults",
    (t, e) => {
      ((lastNSelectedPlayer = { id: t, name: e }),
        (document.getElementById("lastNPlayerChip").innerHTML =
          `\n                <div class="player-chip">\n                    <span>${e}</span>\n                    <button class="player-chip-remove" aria-label="Remove player" data-action="clearLastNPlayer">&times;</button>\n                </div>\n            `),
        (document.getElementById("lastNBtn").disabled = !1));
    },
    "lastNBtn",
  ));
let playoffsData = null,
  activeConference = "east";
async function loadPlayoffs(force = false) {
  if (playoffsData && !force) {
    showConference(activeConference);
    return;
  }
  const t = document.getElementById("playoffsContent");
  t.innerHTML =
    '<div class="loading"><div class="spinner"></div> Loading bracket...</div>';
  try {
    const t = await _fetchWithAbort("playoffs", "/api/playoffs");
    ((playoffsData = await t.json()), showConference(activeConference));
  } catch (e) {
    t.innerHTML = `<div class="empty-state"><div class="empty-state-icon">&#9888;</div><div class="empty-state-title">Error Loading Bracket</div><p>${esc(e.message)}</p></div>`;
  }
}
function showConference(t) {
  if (!playoffsData) return;
  ((activeConference = t),
    document
      .getElementById("playoffEastBtn")
      .classList.toggle("active", "east" === t),
    document
      .getElementById("playoffWestBtn")
      .classList.toggle("active", "west" === t));
  const e = document.getElementById("playoffsContent");
  e.innerHTML = "";
  const piA =
    "east" === t
      ? (playoffsData.playinActual && playoffsData.playinActual.east) || {}
      : (playoffsData.playinActual && playoffsData.playinActual.west) || {};
  drawBracket(
    "east" === t ? playoffsData.east : playoffsData.west,
    "east" === t ? "Eastern Conference" : "Western Conference",
    e,
    piA,
    playoffsData.seriesResults || {},
  );
}
function drawBracket(t, e, s, piActual, seriesResults) {
  const a = 220,
    n = 38,
    i = 20,
    l = 16,
    piA = piActual || {},
    seed7 = piA.seed7TeamId,
    g3w = piA.g3WinnerTeamId;
  const ts = [...t].sort((a, b) => a.rank - b.rank);
  const s7 = seed7
    ? t.find((x) => x.teamId === seed7)
    : { rank: 7, name: "Game 1 Winner", wins: "", losses: "", teamId: null };
  const s8 = g3w
    ? t.find((x) => x.teamId === g3w)
    : { rank: 8, name: "Game 3 Winner", wins: "", losses: "", teamId: null };
  let r = [ts[0], s8, ts[3], ts[4], ts[2], ts[5], ts[1], s7];
  const o = t.slice(6, 10),
    d = 788,
    c = 1.44,
    m = window.devicePixelRatio || 1,
    p = document.createElement("canvas");
  ((p.width = 1134.72 * m),
    (p.height = 778 * m),
    (p.style.cssText =
      "max-width:100%; display:block; margin-bottom:24px; width:100%;"));
  const v = p.getContext("2d");
  v.scale(c * m, c * m);
  const h = "#1a1a24",
    y = "#2a2a3a",
    f = "#ffffff",
    g = "#a0a0b0",
    u = "#ff6b35",
    b = "#f59e0b",
    T = "#3a3a4a";
  const _sr = seriesResults || {};
  const serMap = {};
  [
    [0, 1],
    [2, 3],
    [4, 5],
    [6, 7],
  ].forEach(([ai, bi]) => {
    const tA = r[ai],
      tB = r[bi];
    if (!tA || !tB || !tA.teamId || !tB.teamId) return;
    const k = `${Math.min(tA.teamId, tB.teamId)}_${Math.max(tA.teamId, tB.teamId)}`;
    const sd = _sr[k];
    if (sd) {
      serMap[tA.teamId] = {
        w: sd[String(tA.teamId)] || 0,
        l: sd[String(tB.teamId)] || 0,
      };
      serMap[tB.teamId] = {
        w: sd[String(tB.teamId)] || 0,
        l: sd[String(tA.teamId)] || 0,
      };
    }
  });
  function $(t, e, s, i) {
    ((v.fillStyle = i ? "#22222e" : h),
      x(v, t, e, a, n, 5),
      v.fill(),
      (v.strokeStyle = i ? u : y),
      (v.lineWidth = i ? 1.5 : 1),
      x(v, t, e, a, n, 5),
      v.stroke());
    const dispRank = s.rank;
    const rankColor = dispRank <= 6 ? "#4ade80" : b;
    ((v.fillStyle = rankColor + "22"),
      x(v, t + 6, e + 8, 22, 22, 3),
      v.fill(),
      (v.font = "bold 10px Inter, sans-serif"),
      (v.fillStyle = rankColor),
      (v.textAlign = "center"),
      v.fillText(dispRank, t + 17, e + 23),
      (v.font = "500 11px Inter, sans-serif"),
      (v.fillStyle = f),
      (v.textAlign = "left"));
    let r = s.name;
    for (
      v.font = "11px Inter, sans-serif";
      v.measureText(r).width > 140 && r.length > 4;
    )
      r = r.slice(0, -1);
    (r !== s.name && (r += "…"),
      v.fillText(r, t + 34, e + 23),
      (v.font = "10px Inter, sans-serif"),
      (v.fillStyle = g),
      (v.textAlign = "right"));
    const _sd = serMap[s.teamId];
    v.fillText(
      _sd ? `${_sd.w}-${_sd.l}` : `${s.wins}-${s.losses}`,
      t + a - 6,
      e + 23,
    );
  }
  function x(t, e, s, a, n, i) {
    (t.beginPath(),
      t.moveTo(e + i, s),
      t.lineTo(e + a - i, s),
      t.quadraticCurveTo(e + a, s, e + a, s + i),
      t.lineTo(e + a, s + n - i),
      t.quadraticCurveTo(e + a, s + n, e + a - i, s + n),
      t.lineTo(e + i, s + n),
      t.quadraticCurveTo(e, s + n, e, s + n - i),
      t.lineTo(e, s + i),
      t.quadraticCurveTo(e, s, e + i, s),
      t.closePath());
  }
  function L(t) {
    return i + 46 * t;
  }
  ((v.fillStyle = "#12121a"), v.fillRect(0, 0, d, 540));
  for (let t = 0; t < 8; t++) {
    const e = r[t];
    if (!e) continue;
    const s = L(t);
    $(l, s, e, !1);
  }
  const w = 284,
    A = 552;
  ((v.strokeStyle = T), (v.lineWidth = 1.5));
  const k = [];
  ([
    [0, 1],
    [2, 3],
    [4, 5],
    [6, 7],
  ].forEach(([t, e], s) => {
    const a = L(t) + 19,
      n = L(e) + 19,
      i = 260,
      l = (a + n) / 2;
    (v.beginPath(),
      v.moveTo(236, a),
      v.lineTo(i, a),
      v.stroke(),
      v.beginPath(),
      v.moveTo(236, n),
      v.lineTo(i, n),
      v.stroke(),
      v.beginPath(),
      v.moveTo(i, a),
      v.lineTo(i, n),
      v.stroke(),
      v.beginPath(),
      v.moveTo(i, l),
      v.lineTo(w, l),
      v.stroke(),
      k.push(l - 19));
  }),
    k.forEach((t, e) => {
      ((v.fillStyle = h),
        x(v, w, t, a, n, 5),
        v.fill(),
        (v.strokeStyle = y),
        (v.lineWidth = 1),
        x(v, w, t, a, n, 5),
        v.stroke(),
        (v.font = "10px Inter, sans-serif"),
        (v.fillStyle = g),
        (v.textAlign = "center"),
        v.fillText("Semifinal", 394, t + 19 + 4));
    }));
  const S = [];
  ([
    [0, 1],
    [2, 3],
  ].forEach(([t, e], s) => {
    const a = k[t] + 19,
      n = k[e] + 19,
      i = 528,
      l = (a + n) / 2;
    ((v.strokeStyle = T),
      (v.lineWidth = 1.5),
      v.beginPath(),
      v.moveTo(504, a),
      v.lineTo(i, a),
      v.stroke(),
      v.beginPath(),
      v.moveTo(504, n),
      v.lineTo(i, n),
      v.stroke(),
      v.beginPath(),
      v.moveTo(i, a),
      v.lineTo(i, n),
      v.stroke(),
      v.beginPath(),
      v.moveTo(i, l),
      v.lineTo(A, l),
      v.stroke(),
      S.push(l - 19));
  }),
    S.forEach((t) => {
      ((v.fillStyle = h),
        x(v, A, t, a, n, 5),
        v.fill(),
        (v.strokeStyle = u),
        (v.lineWidth = 1),
        x(v, A, t, a, n, 5),
        v.stroke(),
        (v.font = "bold 10px Inter, sans-serif"),
        (v.fillStyle = u),
        (v.textAlign = "center"),
        v.fillText("Conf. Finals", 662, t + 19 + 4));
    }),
    (v.font = "bold 10px Inter, sans-serif"),
    (v.fillStyle = g),
    (v.textAlign = "center"),
    v.fillText("FIRST ROUND", 126, 8),
    v.fillText("SEMIFINALS", 394, 8),
    v.fillText("CONF. FINALS", 662, 8));
  ((v.font = "bold 10px Inter, sans-serif"),
    (v.fillStyle = b),
    (v.textAlign = "left"),
    v.fillText("PLAY-IN TOURNAMENT (Seeds 7-10)", l, 414));
  const E = 220,
    piY = 436,
    piRowH = 42,
    piGap = 28;
  function drawPiTeam(tx, ty, team, highlight) {
    ((v.fillStyle = highlight ? "#1e1e2e" : h),
      x(v, tx, ty, E, n, 5),
      v.fill(),
      (v.strokeStyle = highlight ? b : y),
      (v.lineWidth = highlight ? 1.5 : 1),
      x(v, tx, ty, E, n, 5),
      v.stroke());
    const rankCol = b;
    ((v.fillStyle = rankCol + "22"),
      x(v, tx + 6, ty + 8, 22, 22, 3),
      v.fill(),
      (v.font = "bold 10px Inter, sans-serif"),
      (v.fillStyle = rankCol),
      (v.textAlign = "center"),
      v.fillText(
        (piA.initialSeeds && piA.initialSeeds[String(team.teamId)]) ||
          team.rank,
        tx + 17,
        ty + 23,
      ),
      (v.font = "10px Inter, sans-serif"),
      (v.fillStyle = f),
      (v.textAlign = "left"));
    let nm = team.name;
    for (; v.measureText(nm).width > 140 && nm.length > 4; )
      nm = nm.slice(0, -1);
    (nm !== team.name && (nm += "…"),
      v.fillText(nm, tx + 34, ty + 23),
      (v.fillStyle = g),
      (v.textAlign = "right"),
      v.fillText(
        team.gameScore != null
          ? String(team.gameScore)
          : !team.losses || team.losses === "?"
            ? "—"
            : team.wins + "-" + team.losses,
        tx + E - 6,
        ty + 23,
      ));
  }
  function drawPiMatchup(
    mx,
    my,
    topTeam,
    botTeam,
    label,
    result,
    topWin,
    botWin,
  ) {
    ((v.font = "bold 9px Inter, sans-serif"),
      (v.fillStyle = g),
      (v.textAlign = "left"),
      v.fillText(label, mx, my - 4),
      drawPiTeam(mx, my, topTeam, !!topWin),
      drawPiTeam(mx, my + piRowH, botTeam, !!botWin),
      (v.font = "9px Inter, sans-serif"),
      (v.fillStyle = b),
      (v.textAlign = "left"),
      v.fillText(result, mx, my + piRowH + n + 8));
  }
  const piCol1 = l,
    piCol2 = l + E + piGap,
    piCol3 = l + (E + piGap) * 2;
  const scrs = piA.gameScores || {};
  function piKey(a, b) {
    return a.teamId < b.teamId
      ? a.teamId + "_" + b.teamId
      : b.teamId + "_" + a.teamId;
  }
  function sT(t, sc) {
    if (!sc || sc[String(t.teamId)] == null) return t;
    const r = Object.assign({}, t);
    r.gameScore = sc[String(t.teamId)];
    return r;
  }
  const g1Sc = o[0] && o[1] ? scrs[piKey(o[0], o[1])] : null;
  const g2Sc = o[2] && o[3] ? scrs[piKey(o[2], o[3])] : null;
  const g1WinIdx = g1Sc
    ? g1Sc[String(o[0].teamId)] >= g1Sc[String(o[1].teamId)]
      ? 0
      : 1
    : -1;
  const g1Loser = g1WinIdx >= 0 ? o[1 - g1WinIdx] : null;
  const g2WinIdx = g2Sc
    ? g2Sc[String(o[2].teamId)] >= g2Sc[String(o[3].teamId)]
      ? 0
      : 1
    : -1;
  const g2Winner = g2WinIdx >= 0 ? o[2 + g2WinIdx] : null;
  const g3Top =
    piA.g1LoserTeamId && o[0]
      ? o[0].teamId === piA.g1LoserTeamId
        ? o[0]
        : o[1] && o[1].teamId === piA.g1LoserTeamId
          ? o[1]
          : null
      : { rank: "?", name: "G1 Loser", wins: "?", losses: "?" };
  const g3Bot =
    piA.g2WinnerTeamId && o[2]
      ? o[2].teamId === piA.g2WinnerTeamId
        ? o[2]
        : o[3] && o[3].teamId === piA.g2WinnerTeamId
          ? o[3]
          : null
      : { rank: "?", name: "G2 Winner", wins: "?", losses: "?" };
  const g3Sc = g3Top.teamId && g3Bot.teamId ? scrs[piKey(g3Top, g3Bot)] : null;
  const g3WTop = !!(
    piA.g3WinnerTeamId &&
    g3Top.teamId &&
    g3Top.teamId === piA.g3WinnerTeamId
  );
  const g3WBot = !!(
    piA.g3WinnerTeamId &&
    g3Bot.teamId &&
    g3Bot.teamId === piA.g3WinnerTeamId
  );
  (drawPiMatchup(
    piCol1,
    piY,
    sT(o[0], g1Sc),
    sT(o[1], g1Sc),
    "GAME 1",
    "→ Winner clinches 7th seed",
    g1WinIdx === 0,
    g1WinIdx === 1,
  ),
    drawPiMatchup(
      piCol2,
      piY,
      sT(o[2], g2Sc),
      sT(o[3], g2Sc),
      "GAME 2",
      "→ Winner advances · Loser eliminated",
      g2WinIdx === 0,
      g2WinIdx === 1,
    ),
    drawPiMatchup(
      piCol3,
      piY,
      sT(g3Top, g3Sc),
      sT(g3Bot, g3Sc),
      "GAME 3",
      "→ Winner clinches 8th seed · Loser eliminated",
      g3WTop,
      g3WBot,
    ),
    s.appendChild(p));
}
let _tradesData = null,
  _tradesMonth = "";
const _TYPE_STYLE = {
  Trade: "background:#3b82f6;color:#fff",
  Signing: "background:#4ade80;color:#000",
  Waive: "background:#ef4444;color:#fff",
  ContractConverted: "background:#f59e0b;color:#000",
};
const _TYPE_LABEL = {
  Trade: "TRADE",
  Signing: "SIGN",
  Waive: "WAIVE",
  ContractConverted: "CONVERT",
};
function _buildTradesMonthBtns() {
  const sel = document.getElementById("tradesMonthSelector");
  const now = new Date();
  const btns = [];
  for (let i = 0; i < 6; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const label = d.toLocaleDateString("en-US", {
      month: "short",
      year: "numeric",
    });
    btns.push({ key, label });
  }
  sel.innerHTML = btns
    .map(
      (b, i) =>
        `<button class="date-btn${i === 0 ? " active" : ""}" data-month="${b.key}">${b.label}</button>`,
    )
    .join("");
  _tradesMonth = btns[0].key;
  sel.querySelectorAll(".date-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      sel
        .querySelectorAll(".date-btn")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      _tradesMonth = btn.dataset.month;
      _renderTrades();
    });
  });
}
async function loadTrades(force = false) {
  if (_tradesData && !force) {
    _renderTrades();
    return;
  }
  const el = document.getElementById("tradesContent");
  el.innerHTML =
    '<div class="loading"><div class="spinner"></div> Loading transactions...</div>';
  try {
    const r = await _fetchWithAbort("trades", "/api/trades"),
      d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Failed to load trades");
    _tradesData = d;
    _renderTrades();
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><div class="empty-state-icon">&#9888;</div><div class="empty-state-title">Error Loading Trades</div><p>${esc(e.message)}</p></div>`;
  }
}
const _HL_PATTERNS = [
  [/\b10-Day Contract/gi, "#f59e0b"],
  [/\bRest-of-Season Contract/gi, "#4ade80"],
  [/\bTwo-Way Contract/gi, "#a78bfa"],
  [/\bExhibit 10 Contract/gi, "#94a3b8"],
  [/\b\d+-Year Contract/gi, "#ff6b35"],
  [/\bMinimum Contract/gi, "#60a5fa"],
  [/\bQualifying Offer/gi, "#60a5fa"],
];
_buildTradesMonthBtns();
let _seasonDoublesData = null;
async function loadSeasonDoubles(force = false) {
  if (_seasonDoublesData && !force) {
    renderSeasonDoubles();
    return;
  }
  const el = document.getElementById("seasonDoublesContent");
  el.innerHTML =
    '<div class="loading"><div class="spinner"></div> Loading season leaders...</div>';
  try {
    const r = await _fetchWithAbort("seasonDoubles", "/api/season/doubles"),
      d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Failed to load");
    _seasonDoublesData = d;
    renderSeasonDoubles();
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><div class="empty-state-icon">&#9888;</div><div class="empty-state-title">Error Loading Data</div><p>${esc(e.message)}</p></div>`;
  }
}
function renderSeasonDoubles() {
  const el = document.getElementById("seasonDoublesContent");
  const d = _seasonDoublesData;
  if (!d) return;
  const tbl = (title, list, isTd) => {
    if (!list || list.length === 0)
      return `<div class="card" style="padding:20px;"><h3 style="margin-bottom:10px;color:var(--accent);">${title}</h3><p style="color:var(--text-secondary);">No data available</p></div>`;
    return `<div class="card" style="overflow-x:auto;"><h3 style="padding:15px 20px;background:var(--bg-secondary);margin:0;border-bottom:1px solid var(--border);">${title}</h3><table class="doubles-table"><thead><tr><th>Rank</th><th style="text-align:left;">Player</th><th>Team</th><th>Count</th>${isTd ? "<th>Details</th>" : ""}</tr></thead><tbody>${list.map((p) => `<tr id="td-row-${p.playerId}"><td>${p.rank}</td><td style="text-align:left;font-weight:500;">${p.name}</td><td>${p.team}</td><td class="highlight">${p.count}</td>${isTd ? `<td><button class="refresh-btn" style="font-size:0.75rem;padding:2px 8px;" data-action="toggleTdGames" data-player-id="${p.playerId}">Details</button></td>` : ""}</tr>${isTd ? `<tr id="td-details-${p.playerId}" style="display:none;"><td colspan="5"><div id="td-games-${p.playerId}" style="padding:8px;"></div></td></tr>` : ""}`).join("")}</tbody></table></div>`;
  };
  el.innerHTML = `<div class="season-doubles-grid">${tbl("Double-Doubles", d.doubleDoubles ? d.doubleDoubles.slice(0, 20) : [], false)}${tbl("Triple-Doubles", d.tripleDoubles ? d.tripleDoubles.slice(0, 20) : [], true)}</div>`;
}
async function toggleTdGames(playerId, btn) {
  const detailRow = document.getElementById(`td-details-${playerId}`);
  if (detailRow.style.display !== "none") {
    detailRow.style.display = "none";
    btn.textContent = "Details";
    return;
  }
  detailRow.style.display = "table-row";
  const container = document.getElementById(`td-games-${playerId}`);
  container.innerHTML =
    '<div class="loading" style="padding:10px;"><div class="spinner"></div> Loading games...</div>';
  btn.textContent = "Hide";
  try {
    const r = await _fetchWithAbort(
        "tdGames_" + playerId,
        `/api/season/triple-double-games/${playerId}`,
      ),
      d = await r.json();
    if (!d.games || d.games.length === 0) {
      container.innerHTML =
        '<p style="color:var(--text-secondary);font-size:0.85rem;">No triple-double games found</p>';
      return;
    }
    container.innerHTML = `<div style="overflow-x:auto;"><table class="boxscore-table" style="font-size:0.72rem;"><thead><tr><th>Date</th><th>Matchup</th><th>PTS</th><th>REB</th><th>AST</th><th>STL</th><th>BLK</th></tr></thead><tbody>${d.games.map((g) => `<tr><td style="white-space:nowrap;">${g.date}</td><td style="white-space:nowrap;">${g.matchup}</td><td class="${statClass("points", g.points)}">${g.points}</td><td class="${statClass("rebounds", g.rebounds)}">${g.rebounds}</td><td class="${statClass("assists", g.assists)}">${g.assists}</td><td class="${statClass("steals", g.steals)}">${g.steals}</td><td class="${statClass("blocks", g.blocks)}">${g.blocks}</td></tr>`).join("")}</tbody></table></div>`;
  } catch (e) {
    container.innerHTML = '<p style="color:#ef4444;">Error loading games</p>';
  }
}
let _seasonHighsData = null;

// === Consolidated views (formerly api/web/overrides.js) ===

async function loadScoreboard() {
  const content = document.getElementById("scoreboardContent");
  content.classList.remove("cards-grid-compact");
  content.classList.add("scoreboard-table-shell");
  content.innerHTML =
    '<div class="loading"><div class="spinner"></div> Loading games...</div>';
  try {
    const response = await _fetchWithAbort("scoreboard", "/api/scoreboard");
    const data = await response.json();
    if (!response.ok)
      throw new Error(data.detail || "Failed to load scoreboard");
    const games = Array.isArray(data.games) ? data.games : [];
    document.getElementById("gamesCount").textContent = `${games.length} Games`;
    if (games.length === 0) {
      content.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">&#127944;</div>
                    <div class="empty-state-title">No Games Today</div>
                    <p>Check back later for live games</p>
                </div>
            `;
      return;
    }

    const safeVal = (value) =>
      value == null || value === "null" ? "-" : value;
    const hasLeader = (leader) =>
      leader && leader.name && leader.name !== "null";
    const leaderLine = (leader) => {
      if (!hasLeader(leader)) return "-";
      return `${esc(leader.name)} ${esc(safeVal(leader.points))}|${esc(safeVal(leader.rebounds))}|${esc(safeVal(leader.assists))}`;
    };
    const toNum = (value) => {
      const parsed = parseInt(value, 10);
      return Number.isFinite(parsed) ? parsed : null;
    };
    const renderTable = (items, startIndex) => `
            <div class="card scoreboard-table-wrap">
                <table class="scoreboard-table">
                    <thead>
                        <tr>
                            <th>Team</th>
                            <th>Score</th>
                            <th>Leader (PTS|REB|AST)</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${items
                          .map((game, idx) => {
                            const homeScore = toNum(game.homeTeam?.score);
                            const awayScore = toNum(game.awayTeam?.score);
                            const scoresValid =
                              homeScore != null && awayScore != null;
                            const homeWinner =
                              scoresValid && homeScore > awayScore;
                            const awayWinner =
                              scoresValid && awayScore > homeScore;
                            const statusRaw = String(game.status ?? "");
                            const statusClass = statusRaw
                              .toLowerCase()
                              .includes("final")
                              ? "final"
                              : "live";
                            const localTime = isGameLive(statusRaw)
                              ? homeTeamLocalTime(game.homeTeam?.tricode)
                              : "";
                            const homeName = esc(game.homeTeam?.name ?? "-");
                            const awayName = esc(game.awayTeam?.name ?? "-");
                            const homeScoreText = esc(
                              safeVal(game.homeTeam?.score),
                            );
                            const awayScoreText = esc(
                              safeVal(game.awayTeam?.score),
                            );
                            return `
                                    <tr class="scoreboard-game-meta">
                                        <td>
                                            <span class="game-status ${statusClass}">${esc(statusRaw)}</span>
                                            ${
                                              localTime
                                                ? `<span class="game-local-time" style="margin-left:8px;">${esc(localTime)}</span>`
                                                : ""
                                            }
                                        </td>
                                        <td class="scoreboard-game-meta-label" colspan="2">${game.gameEt ? new Date(game.gameEt).toLocaleDateString("en-US", { month: "long", day: "2-digit", year: "numeric" }) : ""}</td>
                                    </tr>
                                    <tr class="scoreboard-team-row${homeWinner ? " winner" : ""}">
                                        <td class="scoreboard-team"><code>Home</code><span class="scoreboard-team-name">${homeName}</span></td>
                                        <td class="scoreboard-score">${homeScoreText}</td>
                                        <td class="scoreboard-leader">${leaderLine(game.homeTeam?.leader)}</td>
                                    </tr>
                                    <tr class="scoreboard-team-row${awayWinner ? " winner" : ""}">
                                        <td class="scoreboard-team"><code>Away</code><span class="scoreboard-team-name">${awayName}</span></td>
                                        <td class="scoreboard-score">${awayScoreText}</td>
                                        <td class="scoreboard-leader">${leaderLine(game.awayTeam?.leader)}</td>
                                    </tr>
                                `;
                          })
                          .join("")}
                    </tbody>
                </table>
            </div>
        `;
    const splitAt = Math.ceil(games.length / 2);
    const leftGames = games.slice(0, splitAt);
    const rightGames = games.slice(splitAt);

    content.innerHTML = `
            <div class="scoreboard-split">
                ${renderTable(leftGames, 0)}
                ${rightGames.length ? renderTable(rightGames, splitAt) : ""}
            </div>
        `;
  } catch (e) {
    content.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">&#9888;</div>
                <div class="empty-state-title">Error Loading Games</div>
                <p>${esc(e.message)}</p>
            </div>
        `;
  }
}

async function loadLeaders() {
  const content = document.getElementById("leadersContent");
  content.innerHTML =
    '<div class="loading"><div class="spinner"></div> Loading leaders...</div>';
  try {
    const response = await _fetchWithAbort(
      "leaders",
      `/api/leaders?days_offset=${currentLeadersOffset}`,
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Failed to load leaders");
    const leaders = Object.values(data.leaders || {});
    if (leaders.length === 0) {
      const activeBtn = document.querySelector(
        "#leadersDateSelector .date-btn.active",
      );
      if (activeBtn) activeBtn.hidden = true;
      const nextBtn = document.querySelector(
        "#leadersDateSelector .date-btn:not([hidden])",
      );
      if (nextBtn) {
        nextBtn.click();
        return;
      }
      content.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">&#127942;</div>
                    <div class="empty-state-title">No Stats Available</div>
                    <p>No completed games for ${esc(data.date)}</p>
                </div>
            `;
      return;
    }

    content.innerHTML = `
            <div class="card leaders-table-wrap">
                <table class="leaders-table">
                    <thead>
                        <tr>
                            <th>Category</th>
                            <th>Best</th>
                            <th>Player</th>
                            <th>Team</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${leaders
                          .map((leader) => {
                            const players = Array.isArray(leader.players)
                              ? leader.players
                              : [];
                            const playerNames = players.length
                              ? players.map((p) => esc(p.name)).join("<br>")
                              : "-";
                            const playerTeams = players.length
                              ? players.map((p) => esc(p.team)).join("<br>")
                              : "-";
                            return `
                                <tr>
                                    <td>${esc(leader.label)}</td>
                                    <td>${esc(leader.value)}</td>
                                    <td>${playerNames}</td>
                                    <td>${playerTeams}</td>
                                </tr>
                            `;
                          })
                          .join("")}
                    </tbody>
                </table>
            </div>
        `;
  } catch (e) {
    content.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">&#9888;</div>
                <div class="empty-state-title">Error Loading Leaders</div>
                <p>${esc(e.message)}</p>
            </div>
        `;
  }
}

async function loadSeasonHighs(force = false) {
  if (window._seasonHighsData && !force) {
    renderSeasonHighs();
    return;
  }
  const content = document.getElementById("seasonHighsContent");
  content.innerHTML =
    '<div class="loading"><div class="spinner"></div> Loading season highs...</div>';
  try {
    const response = await _fetchWithAbort("seasonHighs", "/api/season/highs");
    const data = await response.json();
    if (!response.ok)
      throw new Error(data.detail || "Failed to load season highs");
    window._seasonHighsData = data;
    renderSeasonHighs();
  } catch (e) {
    content.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">&#9888;</div>
                <div class="empty-state-title">Error Loading Season Highs</div>
                <p>${esc(e.message)}</p>
            </div>
        `;
  }
}

function renderSeasonHighs() {
  const content = document.getElementById("seasonHighsContent");
  const data = window._seasonHighsData;
  if (!data) return;

  const highs = Object.values(data.highs || {});
  if (highs.length === 0) {
    content.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">&#127942;</div>
                <div class="empty-state-title">No Data Available</div>
                <p>Season highs not available yet</p>
            </div>
        `;
    return;
  }

  content.innerHTML = `
        <p style="color: var(--text-secondary); margin-bottom: 12px; font-size: 0.8rem;">
            Best single-game performances this season (${esc(data.season || "")})
        </p>
        <div class="card leaders-table-wrap">
            <table class="leaders-table">
                <thead>
                    <tr>
                        <th>Category</th>
                        <th>High</th>
                        <th>Player</th>
                        <th>Team</th>
                        <th>Date</th>
                        <th>Matchup</th>
                    </tr>
                </thead>
                <tbody>
                    ${highs
                      .map((high) => {
                        const players = Array.isArray(high.players)
                          ? high.players
                          : [];
                        const fmtDate = (p) => {
                          if (!p.date) return "-";
                          const d = new Date(p.date + "T12:00:00");
                          return isNaN(d)
                            ? esc(p.date)
                            : d.toLocaleDateString("en-US", {
                                month: "short",
                                day: "numeric",
                              });
                        };
                        const playerNames = players.length
                          ? players.map((p) => esc(p.name)).join("<br>")
                          : "-";
                        const playerTeams = players.length
                          ? players.map((p) => esc(p.team)).join("<br>")
                          : "-";
                        const playerDates = players.length
                          ? players.map(fmtDate).join("<br>")
                          : "-";
                        const playerMatchups = players.length
                          ? players
                              .map((p) => esc(p.matchup || "-"))
                              .join("<br>")
                          : "-";
                        return `
                        <tr>
                            <td>${esc(high.label)}</td>
                            <td>${esc(high.value)}</td>
                            <td>${playerNames}</td>
                            <td>${playerTeams}</td>
                            <td style="white-space: nowrap; color: var(--text-secondary); font-size: 0.85em;">${playerDates}</td>
                            <td style="white-space: nowrap; color: var(--text-secondary); font-size: 0.85em;">${playerMatchups}</td>
                        </tr>
                    `;
                      })
                      .join("")}
                </tbody>
            </table>
        </div>
    `;
}
// Trigger initial scoreboard render.
loadScoreboard();

// Keep keyword highlighting, but only on escaped text.

function _hlDesc(desc) {
  let safe = esc(desc);
  _HL_PATTERNS.forEach(([re, col]) => {
    safe = safe.replace(
      re,
      (m) => `<span style="color:${col};font-weight:600;">${m}</span>`,
    );
  });
  return safe;
}

// Trades renderer with escaped API fields.

function _renderTrades() {
  const el = document.getElementById("tradesContent");
  if (!_tradesData) return;

  const transactions = Array.isArray(_tradesData.transactions)
    ? _tradesData.transactions
    : [];
  const filtered = transactions.filter((t) =>
    String(t.date || "").startsWith(_tradesMonth),
  );
  document.getElementById("tradesCount").textContent =
    `${filtered.length} Moves`;

  if (filtered.length === 0) {
    el.innerHTML =
      '<div class="empty-state"><div class="empty-state-icon">&#128257;</div><div class="empty-state-title">No Transactions</div><p>No player movement for this month</p></div>';
    return;
  }

  el.innerHTML = `<div class="card" style="overflow-x:auto;"><table class="player-stats-table"><thead><tr><th style="white-space:nowrap;">Date</th><th style="white-space:nowrap;">Team</th><th style="white-space:nowrap;">Player</th><th style="white-space:nowrap;">Movement</th><th>Description</th></tr></thead><tbody>${filtered
    .map((t) => {
      const dateStr = new Date(`${t.date}T12:00:00`).toLocaleDateString(
        "en-US",
        {
          month: "short",
          day: "numeric",
        },
      );
      const badgeStyle =
        _TYPE_STYLE[t.type] ||
        "background:var(--bg-hover);color:var(--text-primary)";
      const badgeLabel = esc(_TYPE_LABEL[t.type] || t.type);
      const badge = `<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.7rem;font-weight:700;white-space:nowrap;${badgeStyle}">${badgeLabel}</span>`;
      return `<tr><td style="white-space:nowrap;">${esc(dateStr)}</td><td style="white-space:nowrap;">${esc(t.teamName)}</td><td style="white-space:nowrap;">${esc(t.playerName)}</td><td>${badge}</td><td style="color:var(--text-secondary);font-size:0.82rem;">${_hlDesc(t.description)}</td></tr>`;
    })
    .join("")}</tbody></table></div>`;
}

const escAttr = (value) => esc(value).replace(/`/g, "&#96;");
const pct = (value, digits) => {
  const n = Number(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : "-";
};
const safeVal = (value) =>
  value == null || value === "null" ? "-" : esc(value);

async function loadBoxscores() {
  const content = document.getElementById("boxscoresContent");
  content.innerHTML =
    '<div class="loading"><div class="spinner"></div> Loading box scores...</div>';
  try {
    const response = await _fetchWithAbort(
      "boxscores",
      `/api/boxscores?days_offset=${currentBoxscoreOffset}`,
    );
    const data = await response.json();
    if (!response.ok)
      throw new Error(data.detail || "Failed to load box scores");
    const boxscores = Array.isArray(data.boxscores) ? data.boxscores : [];
    if (boxscores.length === 0) {
      const activeBtn = document.querySelector("#boxscores .date-btn.active");
      if (activeBtn) activeBtn.hidden = true;
      const nextBtn = document.querySelector(
        "#boxscores .date-btn:not([hidden])",
      );
      if (nextBtn) {
        nextBtn.click();
        return;
      }
      content.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">&#128202;</div>
                    <div class="empty-state-title">No Box Scores Available</div>
                    <p>No completed games for ${esc(data.date)}</p>
                </div>
            `;
      return;
    }

    const mobile = window.innerWidth <= 768;
    content.innerHTML = boxscores
      .map((game) => {
        const teams = Array.isArray(game.teams) ? game.teams : [];
        const gameId = escAttr(game.gameId ?? "");
        if (mobile) {
          return `
                        <div class="card boxscore-card" style="margin-bottom: 16px; cursor: pointer;" data-action="toggleGameDetails" data-game-id="${gameId}">
                            ${teams
                              .map((team, idx) => {
                                const leader = team.leader || {};
                                return `
                                        <div style="padding: 12px; ${idx === 0 ? "border-bottom: 1px solid var(--border);" : ""}">
                                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                                <span style="font-weight: 600; font-size: 0.95rem;">${esc(team.name)}</span>
                                                <span style="font-size: 1.3rem; font-weight: 700; color: var(--accent);">${safeVal(team.score)}</span>
                                            </div>
                                            <div style="display: flex; gap: 8px; flex-wrap: wrap; font-size: 0.7rem; color: var(--text-secondary);">
                                                <span>FG ${pct(team.stats?.fgPct, 0)}</span>
                                                <span>3P ${pct(team.stats?.threePtPct, 0)}</span>
                                                <span>FT ${pct(team.stats?.ftPct, 0)}</span>
                                                <span>REB ${safeVal(team.stats?.rebounds)}</span>
                                                <span>AST ${safeVal(team.stats?.assists)}</span>
                                                <span>TO ${safeVal(team.stats?.turnovers)}</span>
                                            </div>
                                            <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 6px;">
                                                ${esc(leader.name)} <span style="color: var(--accent);">${safeVal(leader.points)}/${safeVal(leader.rebounds)}/${safeVal(leader.assists)}</span>
                                            </div>
                                        </div>
                                    `;
                              })
                              .join("")}
                            <div style="text-align: center; padding: 8px; color: var(--text-secondary); font-size: 0.75rem; border-top: 1px solid var(--border);">
                                Tap for player details ▼
                            </div>
                            <div class="game-details" id="details-${gameId}" style="display: none;"></div>
                        </div>
                    `;
        }

        return `
                    <div class="card boxscore-card" style="margin-bottom: 20px; cursor: pointer;" data-action="toggleGameDetails" data-game-id="${gameId}">
                        <table class="boxscore-table">
                            <thead>
                                <tr>
                                    <th>Team</th>
                                    <th>Score</th>
                                    <th>FG</th>
                                    <th>FG%</th>
                                    <th>3PT</th>
                                    <th>3P%</th>
                                    <th>FT</th>
                                    <th>FT%</th>
                                    <th>REB</th>
                                    <th>AST</th>
                                    <th>STL</th>
                                    <th>BLK</th>
                                    <th>TO</th>
                                    <th>Leader  |PTS|REB|AST|</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${teams
                                  .map((team) => {
                                    const leader = team.leader || {};
                                    return `
                                            <tr>
                                                <td>${esc(team.name)}</td>
                                                <td class="highlight">${safeVal(team.score)}</td>
                                                <td>${safeVal(team.stats?.fg)}</td>
                                                <td>${pct(team.stats?.fgPct, 1)}</td>
                                                <td>${safeVal(team.stats?.threePt)}</td>
                                                <td>${pct(team.stats?.threePtPct, 1)}</td>
                                                <td>${safeVal(team.stats?.ft)}</td>
                                                <td>${pct(team.stats?.ftPct, 1)}</td>
                                                <td>${safeVal(team.stats?.rebounds)}</td>
                                                <td>${safeVal(team.stats?.assists)}</td>
                                                <td>${safeVal(team.stats?.steals)}</td>
                                                <td>${safeVal(team.stats?.blocks)}</td>
                                                <td>${safeVal(team.stats?.turnovers)}</td>
                                                <td>${esc(leader.name)}  |${safeVal(leader.points)}|${safeVal(leader.rebounds)}|${safeVal(leader.assists)}|</td>
                                            </tr>
                                        `;
                                  })
                                  .join("")}
                            </tbody>
                        </table>
                        <div style="text-align: center; padding: 8px; color: var(--text-secondary); font-size: 0.8rem;">
                            Click to see player details ▼
                        </div>
                        <div class="game-details" id="details-${gameId}" style="display: none;"></div>
                    </div>
                `;
      })
      .join("");
  } catch (e) {
    content.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">&#9888;</div>
                <div class="empty-state-title">Error Loading Box Scores</div>
                <p>${esc(e.message)}</p>
            </div>
        `;
  }
}

function renderInjuries() {
  const content = document.getElementById("injuriesContent");
  const data = injuriesData;
  if (!data) return;

  if (injuriesView === "list") {
    const rows = [];
    (data.injuries || []).forEach((teamEntry) => {
      (teamEntry.players || []).forEach((player) => {
        rows.push({
          name: player.name,
          status: player.status,
          team: teamEntry.team,
        });
      });
    });
    const perCol = Math.ceil(rows.length / 4);
    const columns = [
      rows.slice(0, perCol),
      rows.slice(perCol, 2 * perCol),
      rows.slice(2 * perCol, 3 * perCol),
      rows.slice(3 * perCol),
    ];

    const statusChip = (row) => {
      const statusRaw = String(row.status || "");
      const statusLower = statusRaw.toLowerCase();
      let shortStatus = "GTD";
      if (statusLower.includes("out for") || statusLower === "suspension")
        shortStatus = "OUT";
      else if (
        statusLower.includes("expected") ||
        statusLower.includes("return")
      )
        shortStatus = statusRaw.match(_RETURN_DATE_RE)?.[0] || "TBD";
      else if (
        statusLower === "day-to-day" ||
        statusLower === "game time decision"
      )
        shortStatus = "GTD";
      else if (statusLower === "out") shortStatus = "OUT";
      const color =
        shortStatus === "OUT"
          ? "#ef4444"
          : shortStatus === "GTD"
            ? "#4ade80"
            : "#f59e0b";
      return { shortStatus: esc(shortStatus), color };
    };

    const rowHtml = (row) => {
      const teamName = String(row.team || "");
      const teamLower = teamName.toLowerCase();
      const teamCode =
        _TEAM_CODES[teamLower] ||
        Object.entries(_TEAM_CODES).find(([k]) => teamLower.includes(k))?.[1] ||
        teamName.substring(0, 3).toUpperCase();
      const status = statusChip(row);
      return `<div style="display: flex; justify-content: space-between; padding: 3px 6px; border-bottom: 1px solid var(--border); font-size: 10px;">
                <span style="flex: 1; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${esc(row.name)}</span>
                <span style="width: 30px; color: var(--text-secondary); text-align: center;">${esc(teamCode)}</span>
                <span style="width: 45px; text-align: right; color: ${status.color}; font-weight: 600;">${status.shortStatus}</span>
            </div>`;
    };

    const colHtml = (items) => `
            <div class="card" style="padding: 0; overflow: hidden;">
                <div style="padding: 4px 6px; background: var(--bg-secondary); font-size: 9px; color: var(--text-secondary); display: flex; justify-content: space-between;">
                    <span style="flex: 1;">Player</span>
                    <span style="width: 30px; text-align: center;">Team</span>
                    <span style="width: 45px; text-align: right;">Status</span>
                </div>
                ${items.map(rowHtml).join("")}
            </div>
        `;

    content.innerHTML = `
            <p style="color: var(--text-secondary); margin-bottom: 10px; font-size: 0.75rem;">
                ${rows.length} injured | GTD=Game Time Decision | OUT=Season | Date=Return
            </p>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(min(250px, 100%), 1fr)); gap: 10px;">
                ${columns.map(colHtml).join("")}
            </div>
        `;
    return;
  }

  content.innerHTML = `
        <p style="color: var(--text-secondary); margin-bottom: 20px; font-size: 0.9rem;">
            Last updated: ${esc(data.lastUpdated)} | Source: ${esc(data.source)}
        </p>
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(min(450px, 100%), 1fr)); gap: 20px;">
            ${(data.injuries || [])
              .map(
                (teamEntry) => `
                    <div class="card" style="overflow: hidden;">
                        <div style="padding: 15px 20px; background: var(--bg-secondary); font-weight: 600; border-bottom: 1px solid var(--border);">
                            ${esc(teamEntry.team)}
                            <span style="color: var(--text-secondary); font-weight: normal; font-size: 0.85rem; margin-left: 10px;">${(teamEntry.players || []).length} player${(teamEntry.players || []).length !== 1 ? "s" : ""}</span>
                        </div>
                        <table class="boxscore-table" style="font-size: 0.92rem;">
                            <thead>
                                <tr>
                                    <th style="text-align: left;">Player</th>
                                    <th>Updated</th>
                                    <th>Injury</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${(teamEntry.players || [])
                                  .map((player) => {
                                    const status = String(player.status || "");
                                    const statusLower = status.toLowerCase();
                                    const statusColor =
                                      statusLower.includes("out") ||
                                      statusLower === "suspension"
                                        ? "#ef4444"
                                        : statusLower.includes("expected")
                                          ? "#f59e0b"
                                          : "var(--success)";
                                    return `
                                            <tr>
                                                <td style="text-align: left; font-weight: 500;">${esc(player.name)}</td>
                                                <td style="color: var(--text-secondary); font-size: 0.8rem;">${esc(player.updated)}</td>
                                                <td>${esc(player.injury)}</td>
                                                <td style="color: ${statusColor}; font-weight: 500;">${esc(status)}</td>
                                            </tr>
                                        `;
                                  })
                                  .join("")}
                            </tbody>
                        </table>
                    </div>
                `,
              )
              .join("")}
        </div>
    `;
}

async function loadInjuries() {
  const content = document.getElementById("injuriesContent");
  content.innerHTML =
    '<div class="loading"><div class="spinner"></div> Loading injury report...</div>';
  try {
    const response = await _fetchWithAbort("injuries", "/api/injuries");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Failed to load injuries");
    if (!data.injuries || data.injuries.length === 0) {
      content.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">&#128170;</div>
                    <div class="empty-state-title">No Injuries Reported</div>
                    <p>All players are healthy!</p>
                </div>
            `;
      return;
    }
    injuriesData = data;
    renderInjuries();
  } catch (e) {
    content.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">&#9888;</div>
                <div class="empty-state-title">Error Loading Injuries</div>
                <p>${esc(e.message)}</p>
            </div>
        `;
  }
}

// === Delegated click dispatcher (replaces former inline on* handlers) ===
const _ACTIONS = {
  openCookieSettings: (_t, e) => {
    e.preventDefault();
    window.openCookieSettings && window.openCookieSettings();
  },
  loadScoreboard: () => loadScoreboard(),
  loadBoxscores: () => loadBoxscores(),
  loadLeaders: () => loadLeaders(),
  loadTrackedStats: () => loadTrackedStats(),
  loadStandings: () => loadStandings(),
  loadInjuries: () => loadInjuries(),
  loadLastNGames: () => loadLastNGames(),
  loadPlayoffs: () => loadPlayoffs(),
  loadTrades: () => loadTrades(true),
  loadSeasonDoubles: () => loadSeasonDoubles(true),
  loadSeasonHighs: () => loadSeasonHighs(true),
  setInjuriesView: (t) => setInjuriesView(t.dataset.view),
  showConference: (t) => showConference(t.dataset.conference),
  removeTracked: (t) => removeTrackedPlayer(parseInt(t.dataset.playerId, 10)),
  toggleTdGames: (t) => toggleTdGames(parseInt(t.dataset.playerId, 10), t),
  toggleGameDetails: (t) => toggleGameDetails(t.dataset.gameId, t),
  clearLastNPlayer: () => {
    lastNSelectedPlayer = null;
    document.getElementById("lastNPlayerChip").innerHTML = "";
    document.getElementById("lastNBtn").disabled = true;
  },
};
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-action]");
  if (!t) return;
  const fn = _ACTIONS[t.dataset.action];
  if (fn) fn(t, e);
});

"serviceWorker" in navigator && navigator.serviceWorker.register("/web/sw.js");
