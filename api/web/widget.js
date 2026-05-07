const esc = s => String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
const TIERS = { points:[30,20,15], rebounds:[15,10,7], assists:[15,10,7], steals:[4,3,2], blocks:[4,3,2] };
function sc(t,v) { const s=TIERS[t]; return !s||v<=0?"":v>=s[0]?"stat-elite":v>=s[1]?"stat-great":v>=s[2]?"stat-good":""; }

let tracked = JSON.parse(localStorage.getItem("widget_tracked") || "[]");
let refreshTimer = null;

const $search = document.getElementById("search");
const $results = document.getElementById("results");
const $chips = document.getElementById("chips");
const $content = document.getElementById("content");
const $loadBtn = document.getElementById("loadBtn");
const $status = document.getElementById("status");
const $autoRefresh = document.getElementById("autoRefresh");

function save() { localStorage.setItem("widget_tracked", JSON.stringify(tracked)); }

function renderChips() {
    $chips.innerHTML = tracked.map(p =>
        `<span class="chip">${esc(p.name)} <span class="chip-x" data-id="${p.id}">&times;</span></span>`
    ).join("");
    $loadBtn.disabled = tracked.length === 0;
}

$chips.addEventListener("click", e => {
    const x = e.target.closest(".chip-x");
    if (!x) return;
    tracked = tracked.filter(p => p.id !== parseInt(x.dataset.id));
    save(); renderChips();
    if (!tracked.length) stopRefresh();
});

let searchTimeout;
$search.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    const q = $search.value.trim();
    if (q.length < 2) { $results.classList.remove("open"); return; }
    searchTimeout = setTimeout(async () => {
        try {
            const r = await fetch(`/api/players/search?q=${encodeURIComponent(q)}`);
            if (!r.ok) throw new Error();
            const data = await r.json();
            const matches = data.players.filter(p => !tracked.some(t => t.id === p.id));
            if (!matches.length) {
                $results.innerHTML = '<div class="search-result">No players found</div>';
                $results.classList.add("open");
                return;
            }
            $results.innerHTML = matches.map(p =>
                `<div class="search-result" data-id="${p.id}" data-name="${esc(p.name)}">${esc(p.name)}<span>ID: ${p.id}</span></div>`
            ).join("");
            $results.classList.add("open");
        } catch {
            $results.innerHTML = '<div class="search-result">Search error</div>';
            $results.classList.add("open");
        }
    }, 300);
});

$results.addEventListener("click", e => {
    const r = e.target.closest(".search-result");
    if (!r) return;
    tracked.push({ id: parseInt(r.dataset.id), name: r.dataset.name });
    save(); renderChips();
    $search.value = "";
    $results.classList.remove("open");
});

document.addEventListener("click", e => {
    if (!e.target.closest(".search-wrap")) $results.classList.remove("open");
});

$loadBtn.addEventListener("click", () => loadStats());

async function loadStats() {
    if (!tracked.length) return;
    $status.textContent = "Loading...";
    $status.className = "status";
    try {
        const ids = tracked.map(p => p.id).join(",");
        const r = await fetch(`/api/players/stats?ids=${ids}`);
        const data = await r.json();
        if (!data.players.length) {
            $content.innerHTML = `<div class="empty"><div class="empty-icon">&#128564;</div><div class="empty-title">No Active Games</div><p>Selected players don't have games in progress</p></div>`;
            $status.textContent = "No games";
            $status.className = "status";
            scheduleRefresh();
            return;
        }
        $content.innerHTML = `<table>
            <thead><tr>
                <th>Player</th><th>Team</th><th>MIN</th><th>PTS</th>
                <th>FG</th><th>3 PT</th><th>FT</th><th>REB</th>
                <th>AST</th><th>BLK</th><th>STL</th><th>PF</th>
            </tr></thead>
            <tbody>${data.players.map(p => `<tr>
                <td><strong>${esc(p.name)}</strong></td>
                <td>${esc(p.team)}</td>
                <td>${p.minutes}</td>
                <td class="${sc("points",p.points)}">${p.points}</td>
                <td>${p.fg}</td>
                <td>${p.threePointers}</td>
                <td>${p.ft}</td>
                <td class="${sc("rebounds",p.rebounds)}">${p.rebounds}</td>
                <td class="${sc("assists",p.assists)}">${p.assists}</td>
                <td class="${sc("blocks",p.blocks)}">${p.blocks}</td>
                <td class="${sc("steals",p.steals)}">${p.steals}</td>
                <td>${p.fouls}</td>
            </tr>`).join("")}</tbody></table>`;
        const now = new Date().toLocaleTimeString("en-US", { hour:"2-digit", minute:"2-digit", second:"2-digit" });
        $status.textContent = `Updated ${now}`;
        $status.className = "status live";
        scheduleRefresh();
    } catch (e) {
        $content.innerHTML = `<div class="empty"><div class="empty-icon">&#9888;</div><div class="empty-title">Error</div><p>${esc(e.message)}</p></div>`;
        $status.textContent = "Error";
        $status.className = "status";
        scheduleRefresh();
    }
}

function scheduleRefresh() {
    stopRefresh();
    if ($autoRefresh.checked && tracked.length) {
        refreshTimer = setTimeout(() => loadStats(), 30000);
    }
}
function stopRefresh() { clearTimeout(refreshTimer); refreshTimer = null; }

$autoRefresh.addEventListener("change", () => {
    if ($autoRefresh.checked) scheduleRefresh();
    else stopRefresh();
});

renderChips();
if (tracked.length) loadStats();
