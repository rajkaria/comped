// The leaderboard. One fetch to this site's own /api/leaderboard, rendered in place; nothing else
// is contacted. Used by the home page (top ten) and by leaderboard.html (the whole board).
(function () {
  "use strict";

  var PROVIDERS = {
    anthropic: "Claude", openai: "OpenAI", moonshot: "Kimi", zai: "GLM", deepseek: "DeepSeek", google: "Gemini",
    xai: "Grok", alibaba: "Qwen", minimax: "MiniMax", mistral: "Mistral", meta: "Llama", amazon: "Nova", cohere: "Command"
  };
  var HARNESSES = { "claude-code": "Claude Code", codex: "Codex", pi: "Pi", opencode: "OpenCode" };

  function money(n) { return "$" + Math.round(Number(n) || 0).toLocaleString(); }
  function mult(m) { m = Number(m); return (m < 10 ? m.toFixed(1) : Math.round(m).toLocaleString()) + "×"; }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function name(map, k) { return map[k] || (k ? k.charAt(0).toUpperCase() + k.slice(1) : ""); }
  function ago(iso) {
    var t = Date.parse(iso); if (!t) return "";
    var s = Math.max(0, (Date.now() - t) / 1000);
    if (s < 90) return "just now";
    if (s < 5400) return Math.round(s / 60) + " min ago";
    if (s < 129600) return Math.round(s / 3600) + " h ago";
    return Math.round(s / 86400) + " d ago";
  }
  function tierSlug(t) { return "t-" + String(t || "").toLowerCase().replace(/[^a-z]+/g, "-"); }

  function rowHtml(r, opts) {
    var provs = (r.providers || []).map(function (k) { return "<span class=\"chip\">" + esc(name(PROVIDERS, k)) + "</span>"; }).join("");
    var tools = (r.harnesses || []).map(function (k) { return esc(name(HARNESSES, k)); }).join(", ");
    var who = r.anonymous ? "<span class=\"anon\">" + esc(r.handle) + "</span>" : "<b>" + esc(r.handle) + "</b>";
    var medal = r.rank === 1 ? "🥇" : r.rank === 2 ? "🥈" : r.rank === 3 ? "🥉" : "#" + r.rank;
    return "<tr id=\"" + (r.anonymous ? "" : "h-" + esc(r.handle)) + "\" class=\"" + tierSlug(r.tier) + "\">" +
      "<td class=\"rk\">" + medal + "</td>" +
      "<td class=\"who\">" + who + (opts.full ? "<small>" + esc(tools) + "</small>" : "") + "</td>" +
      "<td class=\"sc\"><b>" + mult(r.multiplier) + "</b><small>" + esc(r.tier || "") + "</small></td>" +
      "<td class=\"usd\">" + money(r.comped_usd) + "<small>for " + money(r.plan_usd) + " · " + esc(r.plan || "") + "</small></td>" +
      (opts.full ? "<td class=\"pv\">" + provs + "</td>" : "") +
      (opts.full ? "<td class=\"dy\">" + r.active_days + " of " + r.days_back + " days<small>" + esc(ago(r.updated_at)) + "</small></td>" : "") +
      "</tr>";
  }

  function tableHtml(rows, opts) {
    if (!rows.length) {
      return "<div class=\"board-empty\">" + (opts.emptyText || "Nobody yet. The first run in the world lands at #1.") + "</div>";
    }
    return "<div class=\"board-scroll\"><table class=\"board\"><thead><tr><th></th><th>who</th><th>comp score</th><th>at full price</th>" +
      (opts.full ? "<th>AI</th><th>window</th>" : "") + "</tr></thead><tbody>" +
      rows.map(function (r) { return rowHtml(r, opts); }).join("") + "</tbody></table></div>";
  }

  function load(sort, limit) {
    // no-store: the edge caches this for 30 s; the browser must not serve a stale copy of the
    // board from before your own run posted.
    return fetch("/api/leaderboard?sort=" + encodeURIComponent(sort) + "&limit=" + limit, { credentials: "omit", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)); })
      .then(function (d) { if (!d || !d.ok) throw new Error("bad reply"); return d; });
  }

  // ---- home page: the top ten and the live count -------------------------------------------
  var top = document.getElementById("board-top");
  if (top) {
    load("multiplier", 10).then(function (d) {
      top.innerHTML = tableHtml(d.rows, { full: false });
      var n = document.getElementById("board-count");
      if (n) n.textContent = d.count === 1 ? "1 person on the board" : d.count.toLocaleString() + " people on the board";
      var stat = document.getElementById("stat-board");
      if (stat) { stat.textContent = d.count.toLocaleString(); stat.removeAttribute("data-count"); }
      var lead = document.getElementById("board-lead");
      if (lead && d.rows.length) {
        lead.textContent = "#1 right now: " + mult(d.rows[0].multiplier) + " — " + d.rows[0].handle + " on " + (d.rows[0].plan || "their plan") + ".";
      }
    }).catch(function () {
      top.innerHTML = "<div class=\"board-empty\">The board is taking a moment. <a href=\"leaderboard.html\">Open it in full.</a></div>";
    });
  }

  // ---- leaderboard.html: the whole board, sortable, filterable, searchable -----------------
  var full = document.getElementById("board-full");
  if (!full) return;
  var state = { sort: "multiplier", provider: "", q: "", data: null };
  var status = document.getElementById("board-status");
  var chips = document.getElementById("board-providers");
  var search = document.getElementById("board-search");

  function visible() {
    var rows = state.data ? state.data.rows : [];
    var q = state.q.trim().toLowerCase();
    return rows.filter(function (r) {
      if (state.provider && (r.providers || []).indexOf(state.provider) < 0) return false;
      if (q && String(r.handle).toLowerCase().indexOf(q) < 0) return false;
      return true;
    });
  }

  function draw() {
    var rows = visible();
    full.innerHTML = tableHtml(rows, { full: true, emptyText: state.data && state.data.rows.length
      ? "Nobody matches that." : "Nobody yet. The first run in the world lands at #1." });
    if (status && state.data) {
      var d = state.data;
      status.textContent = (d.count === 1 ? "1 person" : d.count.toLocaleString() + " people") + " ranked · " +
        (d.submissions === 1 ? "1 run posted" : d.submissions.toLocaleString() + " runs posted") + (d.updated ? " · last one " + ago(d.updated) : "") +
        (rows.length !== d.rows.length ? " · showing " + rows.length : "");
    }
    jumpToHash();
  }

  function jumpToHash() {
    var h = decodeURIComponent((location.hash || "").slice(1));
    if (!h) return;
    var row = document.getElementById("h-" + h);
    if (!row) return;
    row.classList.add("me");
    row.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  function drawChips() {
    if (!chips || !state.data) return;
    var seen = {};
    state.data.rows.forEach(function (r) { (r.providers || []).forEach(function (k) { seen[k] = (seen[k] || 0) + 1; }); });
    var keys = Object.keys(seen).sort(function (a, b) { return seen[b] - seen[a]; });
    chips.innerHTML = "<button class=\"chip" + (state.provider ? "" : " on") + "\" data-p=\"\">Everyone</button>" +
      keys.map(function (k) { return "<button class=\"chip" + (state.provider === k ? " on" : "") + "\" data-p=\"" + esc(k) + "\">" + esc(name(PROVIDERS, k)) + " <i>" + seen[k] + "</i></button>"; }).join("");
    chips.querySelectorAll("button").forEach(function (b) {
      b.addEventListener("click", function () { state.provider = b.dataset.p; drawChips(); draw(); });
    });
  }

  function refresh() {
    if (status) status.textContent = "Loading the board…";
    load(state.sort, 500).then(function (d) { state.data = d; drawChips(); draw(); }).catch(function (e) {
      full.innerHTML = "<div class=\"board-empty\">Couldn't load the board (" + esc(e.message) + "). Try again in a moment.</div>";
      if (status) status.textContent = "";
    });
  }

  document.querySelectorAll("[data-sort]").forEach(function (b) {
    b.addEventListener("click", function () {
      state.sort = b.dataset.sort;
      document.querySelectorAll("[data-sort]").forEach(function (x) { x.classList.toggle("on", x === b); });
      refresh();
    });
  });
  if (search) search.addEventListener("input", function () { state.q = search.value; draw(); });
  window.addEventListener("hashchange", jumpToHash);
  refresh();
})();
