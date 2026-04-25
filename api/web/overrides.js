        (function () {
            const _fetchWithAbort = window._fetchWithAbort;

            const esc = (value) =>
                String(value ?? "")
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;")
                    .replace(/'/g, "&#39;");

            async function loadScoreboardSafe() {
                const content = document.getElementById("scoreboardContent");
                content.classList.remove("cards-grid-compact");
                content.classList.add("scoreboard-table-shell");
                content.innerHTML = '<div class="loading"><div class="spinner"></div> Loading games...</div>';
                try {
                    const response = await _fetchWithAbort("scoreboard", "/api/scoreboard");
                    const data = await response.json();
                    if (!response.ok) throw new Error(data.detail || "Failed to load scoreboard");
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

                    const safeVal = (value) => (value == null || value === "null" ? "-" : value);
                    const hasLeader = (leader) => leader && leader.name && leader.name !== "null";
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
                                            const scoresValid = homeScore != null && awayScore != null;
                                            const homeWinner = scoresValid && homeScore > awayScore;
                                            const awayWinner = scoresValid && awayScore > homeScore;
                                            const statusRaw = String(game.status ?? "");
                                            const statusClass = statusRaw.toLowerCase().includes("final")
                                                ? "final"
                                                : "live";
                                            const localTime = isGameLive(statusRaw)
                                                ? homeTeamLocalTime(game.homeTeam?.tricode)
                                                : "";
                                            const homeName = esc(game.homeTeam?.name ?? "-");
                                            const awayName = esc(game.awayTeam?.name ?? "-");
                                            const homeScoreText = esc(safeVal(game.homeTeam?.score));
                                            const awayScoreText = esc(safeVal(game.awayTeam?.score));
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
                                                    <td class="scoreboard-game-meta-label" colspan="2">${game.gameEt ? new Date(game.gameEt).toLocaleDateString("en-US", {month: "long", day: "2-digit", year: "numeric"}) : ""}</td>
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

            async function loadLeadersSafe() {
                const content = document.getElementById("leadersContent");
                content.innerHTML = '<div class="loading"><div class="spinner"></div> Loading leaders...</div>';
                try {
                    const response = await _fetchWithAbort(
                        "leaders",
                        `/api/leaders?days_offset=${currentLeadersOffset}`
                    );
                    const data = await response.json();
                    if (!response.ok) throw new Error(data.detail || "Failed to load leaders");
                    const leaders = Object.values(data.leaders || {});
                    if (leaders.length === 0) {
                        const activeBtn = document.querySelector("#leadersDateSelector .date-btn.active");
                        if (activeBtn) activeBtn.hidden = true;
                        const nextBtn = document.querySelector("#leadersDateSelector .date-btn:not([hidden])");
                        if (nextBtn) { nextBtn.click(); return; }
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
                                            const players = Array.isArray(leader.players) ? leader.players : [];
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

            async function loadSeasonHighsSafe(force = false) {
                if (window._seasonHighsData && !force) {
                    renderSeasonHighsSafe();
                    return;
                }
                const content = document.getElementById("seasonHighsContent");
                content.innerHTML = '<div class="loading"><div class="spinner"></div> Loading season highs...</div>';
                try {
                    const response = await _fetchWithAbort("seasonHighs", "/api/season/highs");
                    const data = await response.json();
                    if (!response.ok) throw new Error(data.detail || "Failed to load season highs");
                    window._seasonHighsData = data;
                    renderSeasonHighsSafe();
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

            function renderSeasonHighsSafe() {
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
                                ${highs.map((high) => {
                                    const players = Array.isArray(high.players) ? high.players : [];
                                    const fmtDate = (p) => {
                                        if (!p.date) return "-";
                                        const d = new Date(p.date + "T12:00:00");
                                        return isNaN(d) ? esc(p.date) : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                                    };
                                    const playerNames = players.length ? players.map((p) => esc(p.name)).join("<br>") : "-";
                                    const playerTeams = players.length ? players.map((p) => esc(p.team)).join("<br>") : "-";
                                    const playerDates = players.length ? players.map(fmtDate).join("<br>") : "-";
                                    const playerMatchups = players.length ? players.map((p) => esc(p.matchup || "-")).join("<br>") : "-";
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
                                }).join("")}
                            </tbody>
                        </table>
                    </div>
                `;
            }

            // Override legacy renderers with safe versions.
            window.loadScoreboard = loadScoreboardSafe;
            window.loadLeaders = loadLeadersSafe;
            window.loadSeasonHighs = loadSeasonHighsSafe;
            window.renderSeasonHighs = renderSeasonHighsSafe;

            // Ensure first render uses override.
            loadScoreboardSafe();

            // Keep keyword highlighting, but only on escaped text.
            _hlDesc = function (desc) {
                let safe = esc(desc);
                _HL_PATTERNS.forEach(([re, col]) => {
                    safe = safe.replace(re, (m) => `<span style="color:${col};font-weight:600;">${m}</span>`);
                });
                return safe;
            };

            // Override trades renderer to escape all API-provided fields before insertion.
            _renderTrades = function () {
                const el = document.getElementById("tradesContent");
                if (!_tradesData) return;

                const transactions = Array.isArray(_tradesData.transactions) ? _tradesData.transactions : [];
                const filtered = transactions.filter((t) => String(t.date || "").startsWith(_tradesMonth));
                document.getElementById("tradesCount").textContent = `${filtered.length} Moves`;

                if (filtered.length === 0) {
                    el.innerHTML =
                        '<div class="empty-state"><div class="empty-state-icon">&#128257;</div><div class="empty-state-title">No Transactions</div><p>No player movement for this month</p></div>';
                    return;
                }

                el.innerHTML = `<div class="card" style="overflow-x:auto;"><table class="player-stats-table"><thead><tr><th style="white-space:nowrap;">Date</th><th style="white-space:nowrap;">Team</th><th style="white-space:nowrap;">Player</th><th style="white-space:nowrap;">Movement</th><th>Description</th></tr></thead><tbody>${filtered
                    .map((t) => {
                        const dateStr = new Date(`${t.date}T12:00:00`).toLocaleDateString("en-US", {
                            month: "short",
                            day: "numeric",
                        });
                        const badgeStyle =
                            _TYPE_STYLE[t.type] || "background:var(--bg-hover);color:var(--text-primary)";
                        const badgeLabel = esc(_TYPE_LABEL[t.type] || t.type);
                        const badge = `<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.7rem;font-weight:700;white-space:nowrap;${badgeStyle}">${badgeLabel}</span>`;
                        return `<tr><td style="white-space:nowrap;">${esc(dateStr)}</td><td style="white-space:nowrap;">${esc(t.teamName)}</td><td style="white-space:nowrap;">${esc(t.playerName)}</td><td>${badge}</td><td style="color:var(--text-secondary);font-size:0.82rem;">${_hlDesc(t.description)}</td></tr>`;
                    })
                    .join("")}</tbody></table></div>`;
            };

            const escAttr = (value) => esc(value).replace(/`/g, "&#96;");
            const pct = (value, digits) => {
                const n = Number(value);
                return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : "-";
            };
            const safeVal = (value) => (value == null || value === "null" ? "-" : esc(value));

            loadBoxscores = async function () {
                const content = document.getElementById("boxscoresContent");
                content.innerHTML = '<div class="loading"><div class="spinner"></div> Loading box scores...</div>';
                try {
                    const response = await _fetchWithAbort(
                        "boxscores",
                        `/api/boxscores?days_offset=${currentBoxscoreOffset}`
                    );
                    const data = await response.json();
                    if (!response.ok) throw new Error(data.detail || "Failed to load box scores");
                    const boxscores = Array.isArray(data.boxscores) ? data.boxscores : [];
                    if (boxscores.length === 0) {
                        const activeBtn = document.querySelector("#boxscores .date-btn.active");
                        if (activeBtn) activeBtn.hidden = true;
                        const nextBtn = document.querySelector("#boxscores .date-btn:not([hidden])");
                        if (nextBtn) { nextBtn.click(); return; }
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
                                    <div class="card boxscore-card" style="margin-bottom: 16px; cursor: pointer;" onclick="toggleGameDetails('${gameId}', this)">
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
                                <div class="card boxscore-card" style="margin-bottom: 20px; cursor: pointer;" onclick="toggleGameDetails('${gameId}', this)">
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
            };

            renderInjuries = function () {
                const content = document.getElementById("injuriesContent");
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
                        else if (statusLower === "day-to-day" || statusLower === "game time decision")
                            shortStatus = "GTD";
                        else if (statusLower === "out") shortStatus = "OUT";
                        const color = shortStatus === "OUT" ? "#ef4444" : shortStatus === "GTD" ? "#4ade80" : "#f59e0b";
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
                            .map((teamEntry) => `
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
                                                        statusLower.includes("out") || statusLower === "suspension"
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
                            `)
                            .join("")}
                    </div>
                `;
            };

            loadInjuries = async function () {
                const content = document.getElementById("injuriesContent");
                content.innerHTML = '<div class="loading"><div class="spinner"></div> Loading injury report...</div>';
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
            };
        })();
