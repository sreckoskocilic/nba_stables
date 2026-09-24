function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
const escAttr = (value) => esc(value).replace(/`/g, "&#96;");
let trackedPlayerIds = [],
  currentBoxscoreOffset = 0,
  currentLeadersOffset = 0,
  currentLeague = localStorage.getItem("league") || "nba";
function safeParse(raw, fallback) {
  try {
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}
const _pinnedStats = safeParse(localStorage.getItem("pinnedStats"), {});
function _isPinned(pid, stat) {
  return !!_pinnedStats[pid + "_" + stat];
}
function _togglePin(pid, stat) {
  const k = pid + "_" + stat;
  if (_pinnedStats[k]) delete _pinnedStats[k];
  else _pinnedStats[k] = 1;
  localStorage.setItem("pinnedStats", JSON.stringify(_pinnedStats));
}
function leagueParam() {
  return currentLeague === "wnba" ? "&league=wnba" : "";
}
function leagueQuery() {
  return currentLeague === "wnba" ? "?league=wnba" : "";
}
const _abortControllers = {};
function _fetchWithAbort(key, url, opts = {}, timeoutMs = 15e3) {
  _abortControllers[key] && _abortControllers[key].abort();
  const ctrl = new AbortController();
  _abortControllers[key] = ctrl;
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  return fetch(url, { ...opts, signal: ctrl.signal }).finally(() => clearTimeout(timer));
}
function isGameScheduled(status) {
  return /^(\d{1,2}:\d{2}(\s|$)|ppd|postponed|tbd)/i.test(status.trim());
}
const STAT_TIERS = {
  points: [30, 20, 15],
  rebounds: [15, 10, 7],
  assists: [15, 10, 7],
  steals: [4, 3, 2],
  blocks: [4, 3, 2],
};
function statClass(stat, value) {
  const s = STAT_TIERS[stat];
  return !s || value <= 0
    ? ""
    : value >= s[0]
      ? "t-elite"
      : value >= s[1]
        ? "t-great"
        : value >= s[2]
          ? "t-good"
          : "";
}
function statVal(stat, value, extra = "") {
  const cls = [statClass(stat, value), extra].filter(Boolean).join(" ");
  return `<span class="v${cls ? " " + cls : ""}">${esc(value)}</span>`;
}
function loadingHtml(msg, inline) {
  return `<div class="loading${inline ? " inl" : ""}"><span class="spin"></span>${msg}</div>`;
}
function emptyHtml(title, msg) {
  return `<div class="empty">${title ? `<div class="empty-t">${title}</div>` : ""}<p>${msg}</p></div>`;
}
const pct = (value, digits) => {
  const n = Number(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : "-";
};
const safeVal = (value) => (value == null || value === "null" ? "-" : esc(value));
function _fmtPct(v) {
  return ((Number(v) || 0) * 100).toFixed(1) + "%";
}
function _setSegOn(buttons, active) {
  buttons.forEach((b) => {
    b.classList.toggle("on", b === active);
    b.setAttribute("aria-pressed", b === active ? "true" : "false");
  });
}

function _dateLabel(offset) {
  const d = new Date();
  d.setDate(d.getDate() - offset);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}
const _boxscoreDateBtns = Array.from(document.querySelectorAll("#bxDates button"));
const _leaderDateBtns = Array.from(document.querySelectorAll("#ldDates button"));
function _initDateSeg(buttons, onPick) {
  buttons.forEach((b) => {
    b.textContent = _dateLabel(parseInt(b.dataset.offset));
    b.addEventListener("click", () => {
      _setSegOn(buttons, b);
      onPick(parseInt(b.dataset.offset));
    });
  });
}
_initDateSeg(_boxscoreDateBtns, (o) => {
  currentBoxscoreOffset = o;
  loadBoxscores();
});
_initDateSeg(_leaderDateBtns, (o) => {
  currentLeadersOffset = o;
  loadLeaders();
});
function _loadDateLabels() {
  fetch(`/api/dates${leagueQuery()}`)
    .then((r) => r.json())
    .then((t) => {
      const fmt = (v) => {
        const d = new Date(v);
        return isNaN(d) ? v : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
      };
      [_boxscoreDateBtns, _leaderDateBtns].forEach((buttons) => {
        buttons.forEach((b) => {
          const i = parseInt(b.dataset.offset);
          if (t.dates[i]) b.textContent = fmt(t.dates[i]);
          if (t.hasGames && !t.hasGames[i]) b.hidden = true;
        });
        if (t.hasGames) {
          const first = buttons.find((b) => !b.hidden);
          if (first && buttons.find((b) => b.classList.contains("on") && b.hidden)) first.click();
        }
      });
    })
    .catch(() => {});
}

const _navRows = Array.from(document.querySelectorAll(".row[data-view]"));
const _views = Array.from(document.querySelectorAll("section.view"));
function _activeView() {
  const on = _views.find((s) => s.classList.contains("on"));
  return on ? on.id.slice(2) : "scoreboard";
}
function showView(view) {
  _navRows.forEach((b) => {
    const on = b.dataset.view === view;
    b.classList.toggle("on", on);
    if (on) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  _views.forEach((s) => s.classList.toggle("on", s.id === "v-" + view));
  document.getElementById("main").scrollTop = 0;
  switch (view) {
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
}
_navRows.forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));

function initPlayerSearch(inputId, resultsId, onSelect, buttonId) {
  const input = document.getElementById(inputId),
    list = document.getElementById(resultsId);
  let timer,
    idx = -1;
  const items = () => Array.from(list.querySelectorAll(".sr-item[data-id]"));
  const close = () => {
    list.hidden = true;
    idx = -1;
  };
  function pick(item) {
    if (!item || !item.dataset.id) return;
    onSelect(parseInt(item.dataset.id), item.dataset.name);
    input.value = "";
    close();
  }
  input.addEventListener("keydown", (e) => {
    const open = !list.hidden;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) return;
      const all = items();
      const next = e.key === "ArrowDown" ? Math.min(idx + 1, all.length - 1) : Math.max(idx - 1, 0);
      all.forEach((x) => x.classList.remove("on"));
      idx = next < 0 || next >= all.length ? -1 : next;
      if (idx >= 0) {
        all[idx].classList.add("on");
        all[idx].scrollIntoView({ block: "nearest" });
      }
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (open) {
        const all = items();
        pick(idx >= 0 ? all[idx] : all[0]);
      } else if (buttonId) {
        const btn = document.getElementById(buttonId);
        btn && !btn.disabled && btn.click();
      }
    } else if (e.key === "Escape") close();
  });
  input.addEventListener("input", () => {
    idx = -1;
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) {
      list.hidden = true;
      return;
    }
    timer = setTimeout(async () => {
      try {
        const r = await _fetchWithAbort(
          "search_" + inputId,
          `/api/players/search?q=${encodeURIComponent(q)}${leagueParam()}`,
        );
        if (!r.ok) throw new Error("Search failed");
        const d = await r.json();
        list.innerHTML =
          d.players.length === 0
            ? '<div class="sr-item m">No players found</div>'
            : d.players
                .map(
                  (p) =>
                    `<div class="sr-item" data-id="${escAttr(p.id)}" data-name="${escAttr(p.name)}"><span>${esc(p.name)}</span><span class="sr-id">ID: ${esc(p.id)}</span></div>`,
                )
                .join("");
      } catch (err) {
        list.innerHTML = '<div class="sr-item m">Error searching</div>';
      }
      list.hidden = false;
    }, 300);
  });
  list.addEventListener("click", (e) => pick(e.target.closest(".sr-item")));
  document.addEventListener("click", (e) => {
    if (!input.contains(e.target) && !list.contains(e.target)) close();
  });
}

function _chip(name, action, idAttr) {
  return `<span class="chip">${esc(name)}<button class="chip-x" aria-label="Remove player" data-action="${action}"${idAttr}>&times;</button></span>`;
}
function addTrackedPlayer(id, name) {
  if (trackedPlayerIds.find((p) => p.id === id)) return;
  trackedPlayerIds.push({ id, name });
  updateTrackedPlayersUI();
}
function removeTrackedPlayer(id) {
  trackedPlayerIds = trackedPlayerIds.filter((p) => p.id !== id);
  updateTrackedPlayersUI();
}
function updateTrackedPlayersUI() {
  document.getElementById("trackedPlayers").innerHTML = trackedPlayerIds
    .map((p) => _chip(p.name, "removeTracked", ` data-player-id="${escAttr(p.id)}"`))
    .join("");
  document.getElementById("trackBtn").disabled = trackedPlayerIds.length === 0;
}
async function loadTrackedStats() {
  if (trackedPlayerIds.length === 0) return;
  const el = document.getElementById("trackerContent");
  el.innerHTML = loadingHtml("Loading player stats...");
  try {
    const ids = trackedPlayerIds.map((p) => p.id).join(","),
      r = await _fetchWithAbort("trackedStats", `/api/players/stats?ids=${ids}${leagueParam()}`),
      d = await r.json();
    if (d.players.length === 0) {
      el.innerHTML = emptyHtml("No Active Games", "Selected players don't have games in progress today");
      return;
    }
    const cell = (p, stat, value, tierKey) => {
      const pid = escAttr(p.id);
      const pin = _isPinned(p.id, stat) ? "pin" : "";
      const inner = tierKey ? statVal(tierKey, value, pin) : `<span class="v${pin ? " pin" : ""}">${esc(value)}</span>`;
      return `<td class="n" data-pid="${pid}" data-stat="${stat}">${inner}</td>`;
    };
    el.innerHTML = `<div class="wrap"><table class="t ps pins"><thead><tr><th>Player</th><th>Team</th><th class="n">MIN</th><th class="n">PTS</th><th class="n">FG</th><th class="n">3 PT</th><th class="n">FT</th><th class="n">REB</th><th class="n">AST</th><th class="n">BLK</th><th class="n">STL</th><th class="n">PF</th></tr></thead><tbody>${d.players
      .map(
        (p) =>
          `<tr><td class="b">${esc(p.name)}</td><td>${esc(p.team)}</td>${cell(p, "min", p.minutes)}${cell(p, "pts", p.points, "points")}${cell(p, "fg", p.fg)}${cell(p, "3pt", p.threePointers)}${cell(p, "ft", p.ft)}${cell(p, "reb", p.rebounds, "rebounds")}${cell(p, "ast", p.assists, "assists")}${cell(p, "blk", p.blocks, "blocks")}${cell(p, "stl", p.steals, "steals")}${cell(p, "pf", p.fouls)}</tr>`,
      )
      .join("")}</tbody></table></div>`;
    el.querySelector(".pins").addEventListener("click", (e) => {
      const td = e.target.closest("td[data-stat]");
      if (!td) return;
      _togglePin(td.dataset.pid, td.dataset.stat);
      td.querySelector(".v").classList.toggle("pin");
    });
  } catch (e) {
    el.innerHTML = emptyHtml("Error Loading Stats", esc(e.message));
  }
}

function _renderQuarterGrid(teams) {
  if (!teams.length || !teams[0].periods || !teams[0].periods.length) return "";
  const maxPeriods = Math.max(...teams.map((t) => t.periods.length));
  const headers = [];
  for (let i = 0; i < maxPeriods; i++) headers.push(i < 4 ? `Q${i + 1}` : `OT${i - 3}`);
  const rows = teams
    .map((t) => {
      const cells = [];
      for (let i = 0; i < maxPeriods; i++) {
        const p = t.periods[i];
        cells.push(`<td class="n">${p ? esc(p.score) : "-"}</td>`);
      }
      return `<tr><td class="b">${esc(t.tricode)}</td>${cells.join("")}<td class="n hl">${esc(t.score)}</td></tr>`;
    })
    .join("");
  return `<div class="wrap"><table class="t dt-s"><thead><tr><th>Team</th>${headers.map((h) => `<th class="n">${h}</th>`).join("")}<th class="n">F</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
function _renderGameInfoTable(body) {
  const rows = [];
  if (body.arena) rows.push(`<tr><td class="k">Arena</td><td>${esc(body.arena)}</td></tr>`);
  if (body.attendance)
    rows.push(`<tr><td class="k">Attendance</td><td>${esc(body.attendance.toLocaleString("en-US"))}</td></tr>`);
  if (body.officials && body.officials.length)
    rows.push(`<tr><td class="k">Officials</td><td>${body.officials.map((o) => esc(o.name)).join(", ")}</td></tr>`);
  if (!rows.length) return "";
  return `<div class="wrap"><table class="t dt-s info"><tbody>${rows.join("")}</tbody></table></div>`;
}
function _renderTopRow(body) {
  const quarters = _renderQuarterGrid(body.teams);
  const info = _renderGameInfoTable(body);
  if (!quarters && !info) return "";
  return `<div class="bx-strip"><div class="bx-meta">${quarters}${info}</div></div>`;
}
function _renderTeamPlayers(team) {
  const players = team.players.filter((p) => p.minutes !== "0:00" && p.minutes !== "0" && p.minutes !== 0);
  return `<div class="pt"><div class="pt-cap">${esc(team.name)} - ${esc(team.score)}</div><div class="wrap"><table class="t dt-p"><colgroup><col style="width:26ch">${"<col>".repeat(12)}</colgroup><thead><tr><th>Player</th><th class="n">MIN</th><th class="n">PTS</th><th class="n reb-h">REB (O/D)</th><th class="n">AST</th><th class="n">FG</th><th class="n">FG%</th><th class="n">3 PT</th><th class="n">FT</th><th class="n">STL</th><th class="n">BLK</th><th class="n">TO</th><th class="n">PF</th></tr></thead><tbody>${players
    .map(
      (p) =>
        `<tr><td class="pl" title="${escAttr(p.name)}">${esc(p.name)}</td><td class="n m2">${esc(p.minutes)}</td><td class="n">${statVal("points", p.points)}</td><td class="n">${statVal("rebounds", p.rebounds)} <span class="od">(${esc(p.offRebounds)}/${esc(p.defRebounds)})</span></td><td class="n">${statVal("assists", p.assists)}</td><td class="n">${esc(p.fg)}</td><td class="n">${_fmtPct(p.fgPct)}</td><td class="n">${esc(p.threePt)}</td><td class="n">${esc(p.ft)}</td><td class="n">${statVal("steals", p.steals)}</td><td class="n">${statVal("blocks", p.blocks)}</td><td class="n">${esc(p.turnovers)}</td><td class="n">${esc(p.fouls)}</td></tr>`,
    )
    .join("")}</tbody></table></div></div>`;
}
async function toggleGameDetails(gameId, card) {
  const det = card.querySelector(".bx-det");
  if (card.classList.contains("open")) {
    card.classList.remove("open");
    return;
  }
  det.innerHTML = loadingHtml("Loading player stats...", true);
  card.classList.add("open");
  try {
    const r = await _fetchWithAbort("gameDetails_" + gameId, `/api/games/${encodeURIComponent(gameId)}/players`),
      d = await r.json();
    det.innerHTML = _renderTopRow(d) + `<div class="bx-teams">${d.teams.map(_renderTeamPlayers).join("")}</div>`;
  } catch (e) {
    det.innerHTML = '<p class="m det-msg">Error loading player stats</p>';
  }
}

let _standingsData = null;
function renderStandings() {
  const el = document.getElementById("standingsContent");
  const card = (rows, title, po = 6, pi = 10, style = "") =>
    `<section class="card"${style}><h3 class="card-h">${title}</h3><div class="wrap"><table class="t st-t"><thead><tr><th class="rk">#</th><th>Team</th><th class="n">W</th><th class="n">L</th><th class="n">PCT</th><th class="n">GB</th><th class="n">Streak</th><th class="n">L10</th></tr></thead><tbody>${rows
      .map(
        (t, i) =>
          `<tr class="${i < po ? "po" : i < pi ? "pi" : ""}"><td class="rk">${i + 1}</td><td class="b">${esc(t.name)}</td><td class="n hl">${esc(t.wins)}</td><td class="n">${esc(t.losses)}</td><td class="n">${(100 * t.winPct).toFixed(1)}%</td><td class="n">${esc(t.gamesBack)}</td><td class="n">${esc(t.streak)}</td><td class="n">${esc(t.last10)}</td></tr>`,
      )
      .join("")}</tbody></table></div></section>`;
  try {
    el.innerHTML = _standingsData.all
      ? card(_standingsData.all, "Standings", 8, 8, ' style="width:fit-content;max-width:100%"')
      : `<div class="two">${card(_standingsData.east, "Eastern Conference")}${card(_standingsData.west, "Western Conference")}</div>`;
  } catch (e) {
    el.innerHTML = emptyHtml("Error Loading Standings", esc(e.message));
  }
}
async function loadStandings(force = false) {
  if (_standingsData && !force) {
    renderStandings();
    return;
  }
  const el = document.getElementById("standingsContent");
  el.innerHTML = loadingHtml("Loading standings...");
  try {
    const r = await _fetchWithAbort("standings", `/api/standings${leagueQuery()}`);
    _standingsData = await r.json();
    renderStandings();
  } catch (e) {
    el.innerHTML = emptyHtml("Error Loading Standings", esc(e.message));
  }
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
  _RETURN_DATE_RE = /Jan \d+|Feb \d+|Mar \d+|Apr \d+|May \d+/i;
let injuriesData = null,
  injuriesView = "list";
function setInjuriesView(view) {
  injuriesView = view;
  const buttons = Array.from(document.querySelectorAll("#injViews button"));
  _setSegOn(buttons, buttons.find((b) => b.dataset.inj === view));
  injuriesData && renderInjuries();
}
function renderInjuries() {
  const el = document.getElementById("injuriesContent");
  const data = injuriesData;
  if (!data) return;
  if (injuriesView === "list") {
    const rows = [];
    (data.injuries || []).forEach((teamEntry) => {
      (teamEntry.players || []).forEach((player) => {
        rows.push({ name: player.name, status: player.status, team: teamEntry.team });
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
      if (statusLower.includes("out for") || statusLower === "suspension") shortStatus = "OUT";
      else if (statusLower.includes("expected") || statusLower.includes("return"))
        shortStatus = statusRaw.match(_RETURN_DATE_RE)?.[0] || "TBD";
      else if (statusLower === "day-to-day" || statusLower === "game time decision") shortStatus = "GTD";
      else if (statusLower === "out") shortStatus = "OUT";
      const cls = shortStatus === "OUT" ? "s-out" : shortStatus === "GTD" ? "s-gtd" : "s-date";
      return { shortStatus: esc(shortStatus), cls };
    };
    const rowHtml = (row) => {
      const teamName = String(row.team || "");
      const teamLower = teamName.toLowerCase();
      const teamCode =
        _TEAM_CODES[teamLower] ||
        Object.entries(_TEAM_CODES).find(([k]) => teamLower.includes(k))?.[1] ||
        teamName.substring(0, 3).toUpperCase();
      const status = statusChip(row);
      return `<tr><td class="b el">${esc(row.name)}</td><td class="c m">${esc(teamCode)}</td><td class="n ${status.cls}">${status.shortStatus}</td></tr>`;
    };
    const colHtml = (items) =>
      `<div class="card"><table class="t inj-l"><colgroup><col><col style="width:36px"><col style="width:50px"></colgroup><thead><tr><th>Player</th><th class="c">Team</th><th class="n">Status</th></tr></thead><tbody>${items.map(rowHtml).join("")}</tbody></table></div>`;
    el.innerHTML = `<p class="note">${rows.length} injured</p><div class="inj-cols">${columns.map(colHtml).join("")}</div>`;
    return;
  }
  el.innerHTML = `<p class="note">Last updated: ${esc(data.lastUpdated)} | Source: ${esc(data.source)}</p><div class="inj-grp">${(data.injuries || [])
    .map((teamEntry) => {
      const players = teamEntry.players || [];
      return `<section class="card"><h3 class="card-h sm-h">${esc(teamEntry.team)} <span class="m nb">${players.length} player${players.length !== 1 ? "s" : ""}</span></h3><div class="wrap"><table class="t inj-g"><thead><tr><th>Player</th><th>Updated</th><th>Injury</th><th>Status</th></tr></thead><tbody>${players
        .map((player) => {
          const status = String(player.status || "");
          const statusLower = status.toLowerCase();
          const cls =
            statusLower.includes("out") || statusLower === "suspension"
              ? "s-out"
              : statusLower.includes("expected")
                ? "s-date"
                : "s-gtd";
          return `<tr><td class="b">${esc(player.name)}</td><td class="m sm">${esc(player.updated)}</td><td>${esc(player.injury)}</td><td class="${cls}">${esc(status)}</td></tr>`;
        })
        .join("")}</tbody></table></div></section>`;
    })
    .join("")}</div>`;
}
async function loadInjuries() {
  const el = document.getElementById("injuriesContent");
  el.innerHTML = loadingHtml("Loading injury report...");
  try {
    const r = await _fetchWithAbort("injuries", "/api/injuries");
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Failed to load injuries");
    if (!data.injuries || data.injuries.length === 0) {
      el.innerHTML = emptyHtml("No Injuries Reported", "All players are healthy!");
      return;
    }
    injuriesData = data;
    renderInjuries();
  } catch (e) {
    el.innerHTML = emptyHtml("Error Loading Injuries", esc(e.message));
  }
}

let lastNSelectedPlayer = null;
const PROFILE_RECENT_N = 10;
function _renderProfileBio(profile, fallbackName) {
  const bio = (profile && profile.bio) || {};
  const name = bio.name || fallbackName || "";
  const teamLine = [bio.teamName, bio.jersey ? `#${bio.jersey}` : "", bio.position].filter(Boolean).join(" · ");
  let heightStr = bio.height || "";
  const hParts = heightStr.match(/^(\d+)-(\d+)$/);
  if (hParts) {
    const cm = Math.round(parseInt(hParts[1]) * 30.48 + parseInt(hParts[2]) * 2.54);
    heightStr = `${heightStr} (${cm} cm)`;
  }
  let weightStr = "";
  if (bio.weight) {
    const kg = Math.round(parseInt(bio.weight) * 0.4536);
    weightStr = `${bio.weight} lbs (${kg} kg)`;
  }
  const physical = [heightStr, weightStr, bio.age ? `Age ${bio.age}` : "", bio.country].filter(Boolean).join(" · ");
  const draft = bio.draftYear
    ? `Draft ${esc(bio.draftYear)}${bio.draftNumber ? " #" + esc(bio.draftNumber) : ""}`
    : "";
  const meta = [
    draft,
    bio.school ? `College: ${esc(bio.school)}` : "",
    bio.experience != null ? `Experience: ${esc(bio.experience)} yrs` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  return `<div class="bio card"><div class="bio-n">${esc(name)}</div>${teamLine ? `<div class="bio-l1">${esc(teamLine)}</div>` : ""}${physical ? `<div class="bio-l2">${esc(physical)}</div>` : ""}${meta ? `<div class="bio-l3">${meta}</div>` : ""}</div>`;
}
function _renderProfileCareer(profile, pct1) {
  const career = (profile && profile.career) || [];
  if (!career.length) return "";
  return `<div class="wrap"><table class="t ps"><thead><tr><th>Season</th><th>Team</th><th class="n">GP</th><th class="n">MIN</th><th class="n">PTS</th><th class="n">REB</th><th class="n">AST</th><th class="n">STL</th><th class="n">BLK</th><th class="n">FG%</th><th class="n">3 PT%</th><th class="n">FT%</th></tr></thead><tbody>${career
    .map(
      (r) =>
        `<tr><td class="b">${esc(r.season)}</td><td>${esc(r.team)}</td><td class="n">${esc(r.gp)}</td><td class="n">${esc(r.minutes)}</td><td class="n">${statVal("points", r.points)}</td><td class="n">${statVal("rebounds", r.rebounds)}</td><td class="n">${statVal("assists", r.assists)}</td><td class="n">${esc(r.steals)}</td><td class="n">${esc(r.blocks)}</td><td class="n">${pct1(r.fgPct)}</td><td class="n">${pct1(r.fg3Pct)}</td><td class="n">${pct1(r.ftPct)}</td></tr>`,
    )
    .join("")}</tbody></table></div>`;
}
async function loadPlayerProfile() {
  if (!lastNSelectedPlayer) return;
  const el = document.getElementById("lastNContent");
  el.innerHTML = loadingHtml("Loading profile...");
  try {
    const [e, s, p] = await Promise.all([
        _fetchWithAbort(
          "lastNGames",
          `/api/players/${lastNSelectedPlayer.id}/last-n-games?n=${PROFILE_RECENT_N}${leagueParam()}`,
        ),
        _fetchWithAbort("lastNSeasonAvg", `/api/players/${lastNSelectedPlayer.id}/season-avg${leagueQuery()}`),
        _fetchWithAbort("playerProfile", `/api/players/${lastNSelectedPlayer.id}/profile${leagueQuery()}`),
      ]),
      a = await e.json(),
      n = s.ok ? await s.json() : null,
      profile = p.ok ? await p.json() : null;
    const hasGames = a.games && a.games.length > 0;
    const hasProfile = profile && (profile.bio || (profile.career && profile.career.length));
    if (!hasGames && !hasProfile) {
      el.innerHTML = emptyHtml(
        "No Data Found",
        `No profile data available for ${esc((a && a.playerName) || lastNSelectedPlayer.name)}`,
      );
      return;
    }
    const played = (a.games || []).filter((g) => !g.dnp);
    const avgNum = (key) => {
      if (!played.length) return "0.0";
      return (played.reduce((sum, g) => sum + (Number(g[key]) || 0), 0) / played.length).toFixed(1);
    };
    const avgMinutes = () => {
      if (!played.length) return "0.0";
      const toMinutes = (value) => {
        if (value == null) return 0;
        if (typeof value === "number") return value;
        const txt = String(value).trim();
        const m = txt.match(/^(\d+):(\d+)$/);
        if (m) return (Number(m[1]) || 0) + (Number(m[2]) || 0) / 60;
        return Number(txt) || 0;
      };
      return (played.reduce((sum, g) => sum + toMinutes(g.minutes), 0) / played.length).toFixed(1);
    };
    const avgPairPct = (key) => {
      if (!played.length) return "-";
      let made = 0,
        attempt = 0,
        count = 0;
      played.forEach((g) => {
        const m = String(g[key] ?? "").match(/^(\d+)\s*[\/-]\s*(\d+)$/);
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
      let v = Number(value);
      if (!Number.isFinite(v)) return "-";
      if (v <= 1) v *= 100;
      return `${v.toFixed(1)}%`;
    };
    const recentHtml = hasGames
      ? `<div class="wrap"><table class="t ps"><thead><tr><th>Matchup</th><th class="n">MIN</th><th class="n">PTS</th><th class="n">FG</th><th class="n">3 PT</th><th class="n">FT</th><th class="n">REB</th><th class="n">AST</th><th class="n">BLK</th><th class="n">STL</th><th class="n">PF</th></tr></thead><tbody>${a.games
          .map((g, i) => {
            const po = i < a.playoffGames;
            return g.dnp
              ? `<tr class="dnp${po ? " pg" : ""}"><td>${esc(g.matchup)}</td><td colspan="10" class="dnp-c">DNP</td></tr>`
              : `<tr${po ? ' class="pg"' : ""}><td>${esc(g.matchup)}</td><td class="n">${esc(g.minutes)}</td><td class="n">${statVal("points", g.points)}</td><td class="n">${esc(g.fg)}</td><td class="n">${esc(g.threePointers)}</td><td class="n">${esc(g.ft)}</td><td class="n">${statVal("rebounds", g.rebounds)}</td><td class="n">${statVal("assists", g.assists)}</td><td class="n">${statVal("blocks", g.blocks)}</td><td class="n">${statVal("steals", g.steals)}</td><td class="n">${esc(g.fouls)}</td></tr>`;
          })
          .join("")}${
          n
            ? `<tr class="avg sa"><td><span class="sa-s">${esc(n.season)}</span><span class="m sa-g">(${esc(n.gp)} games)</span></td><td class="n m">${esc(n.minutes)}</td><td class="n hl">${esc(n.points)}</td><td class="n m sm">${pct1(n.fgPct)}</td><td class="n m sm">${pct1(n.fg3Pct)}</td><td class="n m sm">${pct1(n.ftPct)}</td><td class="n">${esc(n.rebounds)}</td><td class="n">${esc(n.assists)}</td><td class="n">${esc(n.blocks)}</td><td class="n">${esc(n.steals)}</td><td class="n m">${esc(n.fouls)}</td></tr>`
            : ""
        }<tr class="avg"><td class="b">Last ${played.length} Games Average</td><td class="n">${avgMinutes()}</td><td class="n hl">${avgNum("points")}</td><td class="n">${avgPairPct("fg")}</td><td class="n">${avgPairPct("threePointers")}</td><td class="n">${avgPairPct("ft")}</td><td class="n">${avgNum("rebounds")}</td><td class="n">${avgNum("assists")}</td><td class="n">${avgNum("blocks")}</td><td class="n">${avgNum("steals")}</td><td class="n">${avgNum("fouls")}</td></tr></tbody></table></div>`
      : "";
    const careerHtml = _renderProfileCareer(profile, pct1);
    const panel = (title, html, fallback) =>
      `<section class="card"><h3 class="card-h">${title}</h3>${html || `<p class="m det-msg">${fallback}</p>`}</section>`;
    el.innerHTML =
      _renderProfileBio(profile, lastNSelectedPlayer.name) +
      `<div class="prof">${panel("Last 10 Games", recentHtml, "No recent games")}${panel("Career Stats", careerHtml, "No career data")}</div>`;
  } catch (e) {
    el.innerHTML = emptyHtml("Error Loading Stats", "Error loading stats");
  }
}
function clearLastNPlayer() {
  lastNSelectedPlayer = null;
  document.getElementById("lastNPlayerChip").innerHTML = "";
  document.getElementById("lastNBtn").disabled = true;
}

let playoffsData = null,
  activeConference = "east";
const _poButtons = Array.from(document.querySelectorAll("#poConfs button"));
async function loadPlayoffs(force = false) {
  if (playoffsData && !force) {
    showConference(activeConference);
    return;
  }
  const el = document.getElementById("playoffsContent");
  el.innerHTML = loadingHtml("Loading bracket...");
  try {
    const r = await _fetchWithAbort("playoffs", `/api/playoffs${leagueQuery()}`);
    playoffsData = await r.json();
    showConference(activeConference);
  } catch (e) {
    el.innerHTML = emptyHtml("Error Loading Bracket", esc(e.message));
  }
}
function showConference(conf) {
  if (!playoffsData) return;
  const el = document.getElementById("playoffsContent");
  const seg = document.getElementById("poConfs");
  if (playoffsData.all) {
    seg.hidden = true;
    el.innerHTML = drawBracket(playoffsData.all, "Playoff Bracket", {}, playoffsData.seriesResults || {}, { wnba: true });
    return;
  }
  seg.hidden = false;
  activeConference = conf;
  _setSegOn(_poButtons, _poButtons.find((b) => b.dataset.conference === conf));
  const piA = (playoffsData.playinActual && playoffsData.playinActual[conf]) || {};
  el.innerHTML = drawBracket(
    conf === "east" ? playoffsData.east : playoffsData.west,
    conf === "east" ? "Eastern Conference" : "Western Conference",
    piA,
    playoffsData.seriesResults || {},
  );
}
function showFinals() {
  if (!playoffsData) return;
  const el = document.getElementById("playoffsContent");
  _setSegOn(_poButtons, _poButtons.find((b) => b.dataset.action === "showFinals"));
  const f = playoffsData.finals;
  if (!f || (!f.east && !f.west)) {
    el.innerHTML = emptyHtml("NBA Finals", "Conference Finals still in progress");
    return;
  }
  const eastName = f.east ? esc(f.east.name) : "TBD";
  const westName = f.west ? esc(f.west.name) : "TBD";
  const eastW = f.east && f.seriesScore ? f.seriesScore[String(f.east.teamId)] || 0 : 0;
  const westW = f.west && f.seriesScore ? f.seriesScore[String(f.west.teamId)] || 0 : 0;
  const header = `<div class="card fin-h"><div class="fin-t"><div class="fin-c">East</div><div class="fin-n">${eastName}</div></div><div class="fin-s">${esc(eastW)} - ${esc(westW)}</div><div class="fin-t"><div class="fin-c">West</div><div class="fin-n">${westName}</div></div></div>`;
  if (!f.games || f.games.length === 0) {
    el.innerHTML = `<div class="fin">${header}${emptyHtml("", "No games played yet")}</div>`;
    return;
  }
  const games = f.games
    .map((g, i) => {
      const d = g.date ? new Date(g.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "";
      return `<article class="bxg" data-action="toggleGameDetails" data-game-id="${escAttr(g.gameId)}"><div class="fin-row"><span class="fin-gn">Game ${i + 1}<span class="m">${esc(d)}</span></span><span class="fin-sc">${esc(g.home?.tricode || "—")} <b>${esc(g.home?.score ?? "—")}</b> - <b>${esc(g.away?.score ?? "—")}</b> ${esc(g.away?.tricode || "—")}</span></div><div class="bx-more" title="Player details">▼</div><div class="bx-det"></div></article>`;
    })
    .join("");
  el.innerHTML = `<div class="fin">${header}${games}</div>`;
}
function drawBracket(t, title, piActual, seriesResults, opts) {
  const SW = 320,
    X = [0, 376, 752],
    piA = piActual || {},
    seed7 = piA.seed7TeamId,
    g3w = piA.g3WinnerTeamId;
  const ts = [...t].sort((a, b) => a.rank - b.rank);
  const wnba = opts && opts.wnba,
    _wR1 = wnba ? 2 : 4,
    _wSF = wnba ? 3 : 4;
  const s7 = wnba
    ? ts[6]
    : seed7
      ? t.find((x) => x.teamId === seed7)
      : { rank: 7, name: "Game 1 Winner", wins: "", losses: "", teamId: null };
  const s8 = wnba
    ? ts[7]
    : g3w
      ? t.find((x) => x.teamId === g3w)
      : { rank: 8, name: "Game 3 Winner", wins: "", losses: "", teamId: null };
  const r = [ts[0], s8, ts[3], ts[4], ts[2], ts[5], ts[1], s7];
  const _sr = seriesResults || {};
  const serMap = {};
  const pairs = [
    [0, 1],
    [2, 3],
    [4, 5],
    [6, 7],
  ];
  pairs.forEach(([ai, bi]) => {
    const tA = r[ai],
      tB = r[bi];
    if (!tA || !tB || !tA.teamId || !tB.teamId) return;
    const sd = _sr[`${Math.min(tA.teamId, tB.teamId)}_${Math.max(tA.teamId, tB.teamId)}`];
    if (sd) {
      serMap[tA.teamId] = { w: sd[String(tA.teamId)] || 0, l: sd[String(tB.teamId)] || 0 };
      serMap[tB.teamId] = { w: sd[String(tB.teamId)] || 0, l: sd[String(tA.teamId)] || 0 };
    }
  });
  const _r1Winners = pairs.map(([ai, bi]) => {
    const tA = r[ai],
      tB = r[bi];
    if (!tA || !tB || !tA.teamId || !tB.teamId) return null;
    const sA = serMap[tA.teamId];
    if (sA && sA.w >= _wR1) return tA;
    const sB = serMap[tB.teamId];
    if (sB && sB.w >= _wR1) return tB;
    return null;
  });
  function _getSeries(tA, tB) {
    if (!tA || !tB || !tA.teamId || !tB.teamId) return null;
    const sd = _sr[`${Math.min(tA.teamId, tB.teamId)}_${Math.max(tA.teamId, tB.teamId)}`];
    if (!sd) return null;
    return {
      [tA.teamId]: { w: sd[String(tA.teamId)] || 0, l: sd[String(tB.teamId)] || 0 },
      [tB.teamId]: { w: sd[String(tB.teamId)] || 0, l: sd[String(tA.teamId)] || 0 },
    };
  }
  function _findWinner(tA, tB, sr, win = _wSF) {
    if (!sr) return null;
    if (tA && sr[tA.teamId] && sr[tA.teamId].w >= win) return tA;
    if (tB && sr[tB.teamId] && sr[tB.teamId].w >= win) return tB;
    return null;
  }
  const _semiSr = [_getSeries(_r1Winners[0], _r1Winners[1]), _getSeries(_r1Winners[2], _r1Winners[3])];
  const _semiWinners = [
    _findWinner(_r1Winners[0], _r1Winners[1], _semiSr[0]),
    _findWinner(_r1Winners[2], _r1Winners[3], _semiSr[1]),
  ];
  const _cfSr = _getSeries(_semiWinners[0], _semiWinners[1]);
  const _cfWinner = _findWinner(_semiWinners[0], _semiWinners[1], _cfSr, 4);
  function _recStr(sr, team) {
    if (!sr || !team || !sr[team.teamId]) return "";
    const e = sr[team.teamId];
    return `${e.w}-${e.l}`;
  }
  function slot(x, y, team, cls, recOverride) {
    const sd = serMap[team.teamId];
    const rec = recOverride !== undefined ? recOverride : sd ? `${sd.w}-${sd.l}` : `${team.wins}-${team.losses}`;
    const seedCls = team.rank <= (wnba ? 8 : 6) ? "sd-po" : "sd-pi";
    return `<div class="slot${team.teamId ? "" : " ph"}${cls}" style="left:${x}px;top:${y}px"><span class="sd ${seedCls}">${esc(team.rank)}</span><span class="sn">${esc(team.name)}</span><span class="sr">${esc(rec)}</span></div>`;
  }
  const placeholder = (x, y, label, cls) =>
    `<div class="slot ph mid${cls}" style="left:${x}px;top:${y}px"><span class="sn">${label}</span></div>`;
  const joint = (x, top, height) =>
    `<i class="br" style="left:${x}px;top:${top}px;height:${height}px;width:28px"></i><i class="hz" style="left:${x + 28}px;top:${top + height / 2}px;width:28px"></i>`;
  const parts = [
    `<div class="bh" style="left:${X[0]}px;width:${SW}px">FIRST ROUND</div>`,
    `<div class="bh" style="left:${X[1]}px;width:${SW}px">SEMIFINALS</div>`,
    `<div class="bh" style="left:${X[2]}px;width:${SW}px">${wnba ? "FINALS" : "CONF. FINALS"}</div>`,
  ];
  const semiTops = [];
  pairs.forEach(([ai, bi], i) => {
    const top = 26 + 82 * i;
    if (r[ai]) parts.push(slot(X[0], top, r[ai], ""));
    if (r[bi]) parts.push(slot(X[0], top + 36, r[bi], ""));
    parts.push(joint(SW, top + 16, 36));
    semiTops.push(top + 18);
  });
  semiTops.forEach((top, i) => {
    const team = _r1Winners[i];
    parts.push(
      team ? slot(X[1], top, team, "", _recStr(_semiSr[Math.floor(i / 2)], team)) : placeholder(X[1], top, "Semifinal", ""),
    );
  });
  [0, 1].forEach((i) => {
    const c0 = semiTops[2 * i] + 16,
      c1 = semiTops[2 * i + 1] + 16,
      top = (c0 + c1) / 2 - 16,
      team = _semiWinners[i];
    parts.push(joint(X[1] + SW, c0, c1 - c0));
    parts.push(
      team
        ? slot(X[2], top, team, _cfWinner && team === _cfWinner ? " cf" : "", _recStr(_cfSr, team))
        : placeholder(X[2], top, wnba ? "Finals" : "Conf. Finals", " cf"),
    );
  });
  let html = `<div class="bracket-wrap wrap"><div class="bracket" style="width:${X[2] + SW}px;height:340px" aria-label="${escAttr(title)} bracket">${parts.join("")}</div></div>`;
  if (!wnba) html += _drawPlayIn(t.slice(6, 10), piA);
  return html;
}
function _drawPlayIn(o, piA) {
  const scrs = piA.gameScores || {};
  const piKey = (a, b) => (a.teamId < b.teamId ? a.teamId + "_" + b.teamId : b.teamId + "_" + a.teamId);
  function sT(t, sc) {
    if (!t || !sc || sc[String(t.teamId)] == null) return t;
    return Object.assign({}, t, { gameScore: sc[String(t.teamId)] });
  }
  function piSlot(team, win) {
    if (!team) team = { rank: "?", name: "—", wins: "?", losses: "?" };
    const seed = (piA.initialSeeds && piA.initialSeeds[String(team.teamId)]) || team.rank;
    const rec =
      team.gameScore != null
        ? String(team.gameScore)
        : !team.losses || team.losses === "?"
          ? "—"
          : team.wins + "-" + team.losses;
    return `<div class="slot pis${team.teamId ? "" : " ph"}${win ? " piw" : ""}"><span class="sd sd-pi">${esc(seed)}</span><span class="sn">${esc(team.name)}</span><span class="sr">${esc(rec)}</span></div>`;
  }
  const matchup = (top, bot, label, result, topWin, botWin) =>
    `<div class="pig"><div class="pig-l">${label}</div>${piSlot(top, topWin)}${piSlot(bot, botWin)}<div class="pig-r">${result}</div></div>`;
  const g1Sc = o[0] && o[1] ? scrs[piKey(o[0], o[1])] : null;
  const g2Sc = o[2] && o[3] ? scrs[piKey(o[2], o[3])] : null;
  const g1WinIdx = g1Sc ? (g1Sc[String(o[0].teamId)] >= g1Sc[String(o[1].teamId)] ? 0 : 1) : -1;
  const g2WinIdx = g2Sc ? (g2Sc[String(o[2].teamId)] >= g2Sc[String(o[3].teamId)] ? 0 : 1) : -1;
  const g3TopPh = { rank: "?", name: "G1 Loser", wins: "?", losses: "?" };
  const g3BotPh = { rank: "?", name: "G2 Winner", wins: "?", losses: "?" };
  const g3Top =
    piA.g1LoserTeamId && o[0]
      ? o[0].teamId === piA.g1LoserTeamId
        ? o[0]
        : o[1] && o[1].teamId === piA.g1LoserTeamId
          ? o[1]
          : g3TopPh
      : g3TopPh;
  const g3Bot =
    piA.g2WinnerTeamId && o[2]
      ? o[2].teamId === piA.g2WinnerTeamId
        ? o[2]
        : o[3] && o[3].teamId === piA.g2WinnerTeamId
          ? o[3]
          : g3BotPh
      : g3BotPh;
  const g3Sc = g3Top.teamId && g3Bot.teamId ? scrs[piKey(g3Top, g3Bot)] : null;
  const g3WTop = !!(piA.g3WinnerTeamId && g3Top.teamId && g3Top.teamId === piA.g3WinnerTeamId);
  const g3WBot = !!(piA.g3WinnerTeamId && g3Bot.teamId && g3Bot.teamId === piA.g3WinnerTeamId);
  return `<div class="playin"><div class="pi-h">PLAY-IN TOURNAMENT (Seeds 7-10)</div><div class="pi-g">${matchup(
    sT(o[0], g1Sc),
    sT(o[1], g1Sc),
    "GAME 1",
    "→ Winner clinches 7th seed",
    g1WinIdx === 0,
    g1WinIdx === 1,
  )}${matchup(
    sT(o[2], g2Sc),
    sT(o[3], g2Sc),
    "GAME 2",
    "→ Winner advances · Loser eliminated",
    g2WinIdx === 0,
    g2WinIdx === 1,
  )}${matchup(
    sT(g3Top, g3Sc),
    sT(g3Bot, g3Sc),
    "GAME 3",
    "→ Winner clinches 8th seed · Loser eliminated",
    g3WTop,
    g3WBot,
  )}</div></div>`;
}

let _tradesData = null,
  _tradesMonth = "";
const _TYPE_CLASS = {
  Trade: "mv-trade",
  Signing: "mv-sign",
  Waive: "mv-waive",
  ContractConverted: "mv-conv",
};
const _TYPE_LABEL = {
  Trade: "TRADE",
  Signing: "SIGN",
  Waive: "WAIVE",
  ContractConverted: "CONVERT",
};
const _HL_PATTERNS = [
  [/\b10-Day Contract/gi, "kw-a"],
  [/\bRest-of-Season Contract/gi, "kw-m"],
  [/\bTwo-Way Contract/gi, "kw-s"],
  [/\bExhibit 10 Contract/gi, "kw-x"],
  [/\b\d+-Year Contract/gi, "kw-a"],
  [/\bMinimum Contract/gi, "kw-t"],
  [/\bQualifying Offer/gi, "kw-t"],
];
function _buildTradesMonthBtns() {
  const sel = document.getElementById("tradesMonthSelector");
  const now = new Date();
  const btns = [];
  for (let i = 0; i < 6; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    btns.push({
      key: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`,
      label: d.toLocaleDateString("en-US", { month: "short", year: "numeric" }),
    });
  }
  sel.innerHTML = btns
    .map(
      (b, i) =>
        `<button class="${i === 0 ? "on" : ""}" aria-pressed="${i === 0}" data-month="${b.key}">${b.label}</button>`,
    )
    .join("");
  _tradesMonth = btns[0].key;
  const buttons = Array.from(sel.querySelectorAll("button"));
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      _setSegOn(buttons, btn);
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
  el.innerHTML = loadingHtml("Loading transactions...");
  try {
    const r = await _fetchWithAbort("trades", "/api/trades"),
      d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Failed to load trades");
    _tradesData = d;
    _renderTrades();
  } catch (e) {
    el.innerHTML = emptyHtml("Error Loading Trades", esc(e.message));
  }
}
function _hlDesc(desc) {
  let safe = esc(desc);
  _HL_PATTERNS.forEach(([re, cls]) => {
    safe = safe.replace(re, (m) => `<span class="${cls}">${m}</span>`);
  });
  return safe;
}
function _renderTrades() {
  const el = document.getElementById("tradesContent");
  if (!_tradesData) return;
  const transactions = Array.isArray(_tradesData.transactions) ? _tradesData.transactions : [];
  const filtered = transactions.filter((t) => String(t.date || "").startsWith(_tradesMonth));
  document.getElementById("tradesCount").textContent = `${filtered.length} Moves`;
  if (filtered.length === 0) {
    el.innerHTML = emptyHtml("No Transactions", "No player movement for this month");
    return;
  }
  el.innerHTML = `<div class="wrap"><table class="t ps tr-t"><thead><tr><th>Date</th><th>Team</th><th>Player</th><th>Movement</th><th>Description</th></tr></thead><tbody>${filtered
    .map((t) => {
      const dateStr = new Date(`${t.date}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
      const badge = `<span class="mv ${_TYPE_CLASS[t.type] || "mv-other"}">${esc(_TYPE_LABEL[t.type] || t.type)}</span>`;
      return `<tr><td class="nw">${esc(dateStr)}</td><td class="nw">${esc(t.teamName)}</td><td class="nw b">${esc(t.playerName)}</td><td>${badge}</td><td class="desc">${_hlDesc(t.description)}</td></tr>`;
    })
    .join("")}</tbody></table></div>`;
}

let _seasonDoublesData = null;
async function loadSeasonDoubles(force = false) {
  if (_seasonDoublesData && !force) {
    renderSeasonDoubles();
    return;
  }
  const el = document.getElementById("seasonDoublesContent");
  el.innerHTML = loadingHtml("Loading season leaders...");
  try {
    const r = await _fetchWithAbort("seasonDoubles", "/api/season/doubles" + leagueQuery()),
      d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Failed to load");
    _seasonDoublesData = d;
    renderSeasonDoubles();
  } catch (e) {
    el.innerHTML = emptyHtml("Error Loading Data", esc(e.message));
  }
}
function renderSeasonDoubles() {
  const el = document.getElementById("seasonDoublesContent");
  const d = _seasonDoublesData;
  if (!d) return;
  const tbl = (title, list, isTd) => {
    const head = `<thead><tr><th class="rk">Rank</th><th>Player</th><th class="c">Team</th><th class="n">Count</th>${isTd ? '<th class="c">Details</th>' : ""}</tr></thead>`;
    const body =
      !list || list.length === 0
        ? `<tr><td class="rk"></td><td class="m">No ${isTd ? "triple" : "double"}-doubles yet</td><td></td><td></td>${isTd ? "<td></td>" : ""}</tr>`
        : list
            .map((p) => {
              const pid = escAttr(p.playerId);
              return `<tr><td class="rk">${esc(p.rank)}</td><td class="b">${esc(p.name)}</td><td class="c">${esc(p.team)}</td><td class="n hl">${p.playoff ? `${esc(p.count)}/${esc(p.playoff)}` : esc(p.count)}</td>${
                isTd
                  ? `<td class="c"><button class="mini" data-action="toggleTdGames" data-player-id="${pid}" aria-expanded="false">Details</button></td></tr><tr class="tdd" id="td-details-${pid}" hidden><td colspan="5"><div class="wrap" id="td-games-${pid}"></div></td>`
                  : ""
              }</tr>`;
            })
            .join("");
    return `<section class="card"><h3 class="card-h">${title}</h3><div class="wrap"><table class="t db-t">${head}<tbody>${body}</tbody></table></div></section>`;
  };
  el.innerHTML = `<div class="dbl">${tbl("Double-Doubles", d.doubleDoubles ? d.doubleDoubles.slice(0, 20) : [], false)}${tbl("Triple-Doubles", d.tripleDoubles ? d.tripleDoubles.slice(0, 20) : [], true)}</div>`;
}
async function toggleTdGames(playerId, btn) {
  const detailRow = document.getElementById(`td-details-${playerId}`);
  if (!detailRow.hidden) {
    detailRow.hidden = true;
    btn.textContent = "Details";
    btn.setAttribute("aria-expanded", "false");
    return;
  }
  detailRow.hidden = false;
  btn.textContent = "Hide";
  btn.setAttribute("aria-expanded", "true");
  const container = document.getElementById(`td-games-${playerId}`);
  container.innerHTML = '<p class="m sm">Loading games...</p>';
  try {
    const r = await _fetchWithAbort("tdGames_" + playerId, `/api/season/triple-double-games/${playerId}` + leagueQuery()),
      d = await r.json();
    if (!d.games || d.games.length === 0) {
      container.innerHTML = '<p class="m sm">No triple-double games found</p>';
      return;
    }
    container.innerHTML = `<table class="t dt-s tdg"><thead><tr><th>Date</th><th>Matchup</th><th class="n">PTS</th><th class="n">REB</th><th class="n">AST</th><th class="n">STL</th><th class="n">BLK</th></tr></thead><tbody>${d.games
      .map(
        (g) =>
          `<tr><td class="nw">${esc(g.date)}</td><td class="nw">${esc(g.matchup)}</td><td class="n">${statVal("points", g.points)}</td><td class="n">${statVal("rebounds", g.rebounds)}</td><td class="n">${statVal("assists", g.assists)}</td><td class="n">${statVal("steals", g.steals)}</td><td class="n">${statVal("blocks", g.blocks)}</td></tr>`,
      )
      .join("")}</tbody></table>`;
  } catch (e) {
    container.innerHTML = '<p class="s-out sm">Error loading games</p>';
  }
}

async function loadScoreboard() {
  const content = document.getElementById("scoreboardContent");
  const dateEl = document.getElementById("sbDate");
  content.innerHTML = loadingHtml("Loading games...");
  try {
    const response = await _fetchWithAbort("scoreboard", `/api/scoreboard${leagueQuery()}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Failed to load scoreboard");
    const games = Array.isArray(data.games) ? data.games : [];
    const firstEt = games.length && games[0].gameEt ? new Date(games[0].gameEt) : null;
    dateEl.textContent =
      firstEt && !isNaN(firstEt)
        ? firstEt.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" })
        : "";
    if (games.length === 0) {
      content.innerHTML = emptyHtml("No Games Today", "Check back later for live games");
      return;
    }
    const hasLeader = (leader) => leader && leader.name && leader.name !== "null";
    const leaderCells = (leader) =>
      hasLeader(leader)
        ? `<td class="ldn">${esc(leader.name)}</td><td class="n">${safeVal(leader.points)}</td><td class="n">${safeVal(leader.rebounds)}</td><td class="n">${safeVal(leader.assists)}</td>`
        : '<td class="ldn z">-</td><td class="n z">-</td><td class="n z">-</td><td class="n z">-</td>';
    const toNum = (value) => {
      const parsed = parseInt(value, 10);
      return Number.isFinite(parsed) ? parsed : null;
    };
    const body = games
      .map((game) => {
        const homeScore = toNum(game.homeTeam?.score);
        const awayScore = toNum(game.awayTeam?.score);
        const decided = homeScore != null && awayScore != null && homeScore !== awayScore;
        const homeCls = decided ? (homeScore > awayScore ? "win" : "lose") : "";
        const awayCls = decided ? (awayScore > homeScore ? "win" : "lose") : "";
        const statusRaw = String(game.status ?? "");
        const stCls = statusRaw.toLowerCase().includes("final")
          ? "st-final"
          : isGameScheduled(statusRaw)
            ? "st-sched"
            : "st-live";
        const s = game.series;
        let series = "";
        if (s) {
          const home = Number(s.home) || 0;
          const away = Number(s.away) || 0;
          const homeTri = game.homeTeam?.tricode ?? "";
          const awayTri = game.awayTeam?.tricode ?? "";
          const [leadTri, trailTri, leadW, trailW] =
            home >= away ? [homeTri, awayTri, home, away] : [awayTri, homeTri, away, home];
          series = `<span class="ser">${esc(leadTri)}-${esc(trailTri)} ${leadW}-${trailW}</span>`;
        }
        return `<tbody><tr class="${homeCls} g1"><td class="stc" rowspan="2"><span class="st ${stCls}">${esc(statusRaw)}</span>${series}</td><td class="tm">${esc(game.homeTeam?.name ?? "-")}</td><td class="n sc">${safeVal(game.homeTeam?.score)}</td>${leaderCells(game.homeTeam?.leader)}</tr><tr class="${awayCls}"><td class="tm">${esc(game.awayTeam?.name ?? "-")}</td><td class="n sc">${safeVal(game.awayTeam?.score)}</td>${leaderCells(game.awayTeam?.leader)}</tr></tbody>`;
      })
      .join("");
    content.innerHTML = `<div class="wrap"><table class="t sb"><thead><tr><th>Status</th><th>Team</th><th class="n">Score</th><th>Leader</th><th class="n">PTS</th><th class="n">REB</th><th class="n">AST</th></tr></thead>${body}</table></div>`;
  } catch (e) {
    content.innerHTML = emptyHtml("Error Loading Games", esc(e.message));
  }
}

function _playerLines(players, fn) {
  return players.length ? players.map(fn).join("<br>") : "-";
}
async function loadLeaders() {
  const content = document.getElementById("leadersContent");
  content.innerHTML = loadingHtml("Loading leaders...");
  try {
    const response = await _fetchWithAbort("leaders", `/api/leaders?days_offset=${currentLeadersOffset}${leagueParam()}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Failed to load leaders");
    const leaders = Object.values(data.leaders || {});
    if (leaders.length === 0) {
      const activeBtn = _leaderDateBtns.find((b) => b.classList.contains("on"));
      if (activeBtn) activeBtn.hidden = true;
      const nextBtn = _leaderDateBtns.find((b) => !b.hidden);
      if (nextBtn) {
        nextBtn.click();
        return;
      }
      content.innerHTML = emptyHtml("No Stats Available", `No completed games for ${esc(data.date)}`);
      return;
    }
    content.innerHTML = `<div class="wrap"><table class="t lt-t"><thead><tr><th>Category</th><th class="n">Best</th><th>Player</th><th>Team</th></tr></thead><tbody>${leaders
      .map((leader) => {
        const players = Array.isArray(leader.players) ? leader.players : [];
        return `<tr><td>${esc(leader.label)}</td><td class="n hl">${esc(leader.value)}</td><td>${_playerLines(players, (p) => esc(p.name))}</td><td>${_playerLines(players, (p) => esc(p.team))}</td></tr>`;
      })
      .join("")}</tbody></table></div>`;
  } catch (e) {
    content.innerHTML = emptyHtml("Error Loading Leaders", esc(e.message));
  }
}

let _seasonHighsData = null;
async function loadSeasonHighs(force = false) {
  if (_seasonHighsData && !force) {
    renderSeasonHighs();
    return;
  }
  const content = document.getElementById("seasonHighsContent");
  document.getElementById("seasonHighsNote").textContent = "";
  content.innerHTML = loadingHtml("Loading season highs...");
  try {
    const response = await _fetchWithAbort("seasonHighs", "/api/season/highs" + leagueQuery());
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Failed to load season highs");
    _seasonHighsData = data;
    renderSeasonHighs();
  } catch (e) {
    content.innerHTML = emptyHtml("Error Loading Season Highs", esc(e.message));
  }
}
function renderSeasonHighs() {
  const content = document.getElementById("seasonHighsContent");
  const note = document.getElementById("seasonHighsNote");
  const data = _seasonHighsData;
  if (!data) return;
  const highs = Object.values(data.highs || {});
  if (highs.length === 0) {
    note.textContent = "";
    content.innerHTML = emptyHtml("No Data Available", "Season highs not available yet");
    return;
  }
  note.textContent = `Best single-game performances this season (${data.season || ""})`;
  const fmtDate = (p) => {
    if (!p.date) return "-";
    const d = new Date(p.date + "T12:00:00");
    return isNaN(d) ? esc(p.date) : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };
  content.innerHTML = `<div class="wrap"><table class="t lt-t"><thead><tr><th>Category</th><th class="n">High</th><th>Player</th><th>Team</th><th>Date</th><th>Matchup</th></tr></thead><tbody>${highs
    .map((high) => {
      const players = Array.isArray(high.players) ? high.players : [];
      const isPlayoff = players.some((p) => p.playoff);
      return `<tr${isPlayoff ? ' class="pg"' : ""}><td>${esc(high.label)}</td><td class="n hl">${esc(high.value)}</td><td>${_playerLines(players, (p) => esc(p.name))}</td><td>${_playerLines(players, (p) => esc(p.team))}</td><td class="m sm nw">${_playerLines(players, fmtDate)}</td><td class="m sm nw">${_playerLines(players, (p) => esc(p.matchup || "-"))}</td></tr>`;
    })
    .join("")}</tbody></table></div>`;
}

const _BX_COLS =
  '<colgroup><col style="width:calc(22ch + 10px)">' +
  '<col style="width:calc(5ch + 16px)">'.repeat(2) +
  ('<col style="width:calc(6ch + 16px)">' + '<col style="width:calc(5ch + 16px)">').repeat(2) +
  '<col style="width:calc(6ch + 16px)">' +
  '<col style="width:calc(3ch + 16px)">'.repeat(5) +
  "<col>" +
  '<col style="width:calc(3ch + 16px)">'.repeat(3) +
  "</colgroup>";
async function loadBoxscores() {
  const content = document.getElementById("boxscoresContent");
  content.innerHTML = loadingHtml("Loading box scores...");
  try {
    const response = await _fetchWithAbort(
      "boxscores",
      `/api/boxscores?days_offset=${currentBoxscoreOffset}${leagueParam()}`,
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Failed to load box scores");
    const boxscores = Array.isArray(data.boxscores) ? data.boxscores : [];
    if (boxscores.length === 0) {
      const activeBtn = _boxscoreDateBtns.find((b) => b.classList.contains("on"));
      if (activeBtn) activeBtn.hidden = true;
      const nextBtn = _boxscoreDateBtns.find((b) => !b.hidden);
      if (nextBtn) {
        nextBtn.click();
        return;
      }
      content.innerHTML = emptyHtml("No Box Scores Available", `No completed games for ${esc(data.date)}`);
      return;
    }
    const mobile = window.innerWidth <= 768;
    const tail = '<div class="bx-more" title="Player details">▼</div><div class="bx-det"></div>';
    content.innerHTML = `<div class="bx-list">${boxscores
      .map((game) => {
        const teams = Array.isArray(game.teams) ? game.teams : [];
        const open = `<article class="bxg" data-action="toggleGameDetails" data-game-id="${escAttr(game.gameId ?? "")}">`;
        if (mobile) {
          return `${open}${teams
            .map((team) => {
              const leader = team.leader || {};
              return `<div class="bxm"><div class="bxm-h"><span class="tm">${esc(team.name)}</span><span class="sc">${safeVal(team.score)}</span></div><div class="bxm-s"><span>FG ${pct(team.stats?.fgPct, 0)}</span><span>3 PT ${pct(team.stats?.threePtPct, 0)}</span><span>FT ${pct(team.stats?.ftPct, 0)}</span><span>REB ${safeVal(team.stats?.rebounds)}</span><span>AST ${safeVal(team.stats?.assists)}</span><span>TO ${safeVal(team.stats?.turnovers)}</span></div><div class="bxm-l">${esc(leader.name)} <span>${safeVal(leader.points)}/${safeVal(leader.rebounds)}/${safeVal(leader.assists)}</span></div></div>`;
            })
            .join("")}${tail}</article>`;
        }
        return `${open}<div class="bx-top"><div class="wrap grow"><table class="t bxs">${_BX_COLS}<thead><tr><th>Team</th><th class="n">Score</th><th class="n">FG</th><th class="n">FG%</th><th class="n">3 PT</th><th class="n">3 PT%</th><th class="n">FT</th><th class="n">FT%</th><th class="n">REB</th><th class="n">AST</th><th class="n">STL</th><th class="n">BLK</th><th class="n">TO</th><th class="ldh">Leader</th><th class="n">PTS</th><th class="n">REB</th><th class="n">AST</th></tr></thead><tbody>${teams
          .map((team) => {
            const leader = team.leader || {};
            const st = team.stats || {};
            return `<tr><td class="tm">${esc(team.name)}</td><td class="n sc">${safeVal(team.score)}</td><td class="n">${safeVal(st.fg)}</td><td class="n">${pct(st.fgPct, 1)}</td><td class="n">${safeVal(st.threePt)}</td><td class="n">${pct(st.threePtPct, 1)}</td><td class="n">${safeVal(st.ft)}</td><td class="n">${pct(st.ftPct, 1)}</td><td class="n">${safeVal(st.rebounds)}</td><td class="n">${safeVal(st.assists)}</td><td class="n">${safeVal(st.steals)}</td><td class="n">${safeVal(st.blocks)}</td><td class="n">${safeVal(st.turnovers)}</td><td class="ldn">${esc(leader.name)}</td><td class="n">${safeVal(leader.points)}</td><td class="n">${safeVal(leader.rebounds)}</td><td class="n">${safeVal(leader.assists)}</td></tr>`;
          })
          .join("")}</tbody></table></div></div>${tail}</article>`;
      })
      .join("")}</div>`;
  } catch (e) {
    content.innerHTML = emptyHtml("Error Loading Box Scores", esc(e.message));
  }
}

const _ACTIONS = {
  loadScoreboard: () => loadScoreboard(),
  loadBoxscores: () => loadBoxscores(),
  loadLeaders: () => loadLeaders(),
  loadTrackedStats: () => loadTrackedStats(),
  loadStandings: () => loadStandings(true),
  loadInjuries: () => loadInjuries(),
  loadPlayerProfile: () => loadPlayerProfile(),
  loadPlayoffs: () => loadPlayoffs(true),
  loadTrades: () => loadTrades(true),
  loadSeasonDoubles: () => loadSeasonDoubles(true),
  loadSeasonHighs: () => loadSeasonHighs(true),
  setInjuriesView: (t) => setInjuriesView(t.dataset.inj),
  showConference: (t) => showConference(t.dataset.conference),
  showFinals: () => showFinals(),
  removeTracked: (t) => removeTrackedPlayer(parseInt(t.dataset.playerId, 10)),
  toggleTdGames: (t) => toggleTdGames(parseInt(t.dataset.playerId, 10), t),
  toggleGameDetails: (t) => toggleGameDetails(t.dataset.gameId, t),
  clearLastNPlayer: () => clearLastNPlayer(),
};
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-action]");
  if (!t) return;
  const fn = _ACTIONS[t.dataset.action];
  if (fn) fn(t, e);
});

const _NBA_ONLY_TABS = ["injuries", "trades"];
const _leagueBtns = Array.from(document.querySelectorAll(".league [data-league]"));
function _applyLeagueToggle() {
  document.body.classList.toggle("wnba", currentLeague === "wnba");
  _setSegOn(_leagueBtns, _leagueBtns.find((b) => b.dataset.league === currentLeague));
  document.getElementById("slMode").textContent = currentLeague === "wnba" ? "WNBA" : "NBA";
}
function setLeague(league) {
  if (league === currentLeague) return;
  currentLeague = league;
  localStorage.setItem("league", currentLeague);
  _applyLeagueToggle();
  ["playerSearch", "lastNSearch"].forEach((id) => (document.getElementById(id).value = ""));
  ["searchResults", "lastNSearchResults"].forEach((id) => {
    const el = document.getElementById(id);
    el.innerHTML = "";
    el.hidden = true;
  });
  trackedPlayerIds = [];
  updateTrackedPlayersUI();
  document.getElementById("trackerContent").innerHTML = emptyHtml(
    "Track Your Favorite Players",
    "Search and select players above to see their live game stats",
  );
  clearLastNPlayer();
  document.getElementById("lastNContent").innerHTML = emptyHtml("Player Profile", "Search and select a player above");
  _standingsData = null;
  playoffsData = null;
  _seasonDoublesData = null;
  _seasonHighsData = null;
  _boxscoreDateBtns.forEach((b) => (b.hidden = false));
  _leaderDateBtns.forEach((b) => (b.hidden = false));
  _loadDateLabels();
  const view = _activeView();
  if (_NBA_ONLY_TABS.includes(view)) {
    showView("scoreboard");
    return;
  }
  switch (view) {
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
      loadStandings(true);
      break;
    case "tracker":
      loadTrackedStats();
      break;
    case "lastngames":
      if (lastNSelectedPlayer) loadPlayerProfile();
      break;
    case "playoffs":
      loadPlayoffs(true);
      break;
    case "seasonDoubles":
      loadSeasonDoubles(true);
      break;
    case "seasonHighs":
      loadSeasonHighs(true);
      break;
  }
}
_leagueBtns.forEach((b) => b.addEventListener("click", () => setLeague(b.dataset.league)));
document.getElementById("slMode").addEventListener("click", () => setLeague(currentLeague === "wnba" ? "nba" : "wnba"));

(function initHelp() {
  const help = document.getElementById("help"),
    btn = document.getElementById("helpBtn");
  const names = [
    ["elite", "t-elite"],
    ["great", "t-great"],
    ["good", "t-good"],
  ];
  const cols = ["points", "rebounds", "assists", "steals", "blocks"];
  document.getElementById("tierRows").innerHTML = names
    .map(
      ([label, cls], i) =>
        `<tr><td><span class="v ${cls}">${label}</span></td>${cols.map((c) => `<td class="n">${STAT_TIERS[c][i]}</td>`).join("")}</tr>`,
    )
    .join("");
  const setHelp = (open) => {
    help.hidden = !open;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  };
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    setHelp(help.hidden);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") setHelp(false);
  });
  document.addEventListener("click", (e) => {
    if (!help.hidden && !help.contains(e.target)) setHelp(false);
  });
})();

initPlayerSearch("playerSearch", "searchResults", addTrackedPlayer, "trackBtn");
initPlayerSearch(
  "lastNSearch",
  "lastNSearchResults",
  (id, name) => {
    lastNSelectedPlayer = { id, name };
    document.getElementById("lastNPlayerChip").innerHTML = _chip(name, "clearLastNPlayer", "");
    document.getElementById("lastNBtn").disabled = false;
  },
  "lastNBtn",
);
_buildTradesMonthBtns();
_applyLeagueToggle();
_loadDateLabels();
loadScoreboard();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker
    .getRegistrations()
    .then((regs) => {
      regs.forEach((r) => r.scope.endsWith("/web/") && r.unregister());
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    })
    .catch(() => {});
}
