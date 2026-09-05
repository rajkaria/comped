// The share card, drawn in the browser. Two ways in, and neither uploads anything:
//
//   card.html?h=<handle>   looks your row up in this site's own public /api/leaderboard, the same
//                          list leaderboard.html renders.
//   card.html#c=<payload>  carries the numbers comped printed on your own machine. Everything
//                          after the "#" stays in the browser: it is never sent in the request.
//
// The card is an SVG built here, rasterised to PNG through a canvas, and handed to you as a file.
// It uses the same palette and the same wording as comped_core/render_svg.py, so the picture the
// tool writes locally and the picture this page makes are the same card.
(function () {
  "use strict";

  var stage = document.getElementById("card-stage");
  if (!stage) return;

  var SITE = "gotcomped.com";
  var W = 1200, H = 675;
  var FONT = "ui-rounded, 'SF Pro Rounded', 'Arial Rounded MT Bold', Nunito, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif";
  var MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

  var THEMES = {
    dark: { bg: "#1e1b2e", panel: "#2a2640", line: "#3d3859", fg: "#fff8ee", muted: "#b3accb", accent: "#ff6b4a",
            accent2: "#8f74ff", yellow: "#ffd23f", mint: "#3be0b0", bar: "#3a3556", blob1: "#ff6b4a", blob2: "#8f74ff", ink: "#1e1b2e" },
    light: { bg: "#fff7ea", panel: "#ffffff", line: "#eadfcb", fg: "#1e1b2e", muted: "#6b6478", accent: "#e4522f",
             accent2: "#6a4bff", yellow: "#ffd23f", mint: "#12a37f", bar: "#f1e7d6", blob1: "#ffb59f", blob2: "#c9bbff", ink: "#1e1b2e" }
  };

  // Two names per provider: the company that sells the plan, and the thing you actually talk to.
  // Same split as comped_core/detect.py, which is where these come from.
  var PROVIDERS = {
    anthropic: ["Anthropic", "Claude"], openai: ["OpenAI", "GPT / Codex"], moonshot: ["Moonshot", "Kimi"],
    zai: ["Z.ai", "GLM"], deepseek: ["DeepSeek", "DeepSeek"], google: ["Google", "Gemini"], xai: ["xAI", "Grok"],
    alibaba: ["Alibaba", "Qwen"], minimax: ["MiniMax", "MiniMax"], mistral: ["Mistral", "Mistral"],
    meta: ["Meta", "Llama"], amazon: ["Amazon", "Nova"], cohere: ["Cohere", "Command"]
  };
  var HARNESSES = { "claude-code": "Claude Code", codex: "Codex CLI", pi: "Pi", opencode: "OpenCode" };

  var TIERS = [[1, "Paying customer"], [2, "Break-even"], [5, "Comped"], [12, "Properly comped"],
               [30, "All-you-can-eat"], [80, "Hostage situation"], [Infinity, "Please stop"]];

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function num(n) { n = Number(n); return isFinite(n) ? n : null; }
  function money(n) { return "$" + Math.round(Number(n) || 0).toLocaleString("en-US"); }
  function mult(m) {
    if (m == null) return "no plan";
    m = Number(m);
    return (m < 10 ? m.toFixed(1) : Math.round(m).toLocaleString("en-US")) + "×";
  }
  function tierName(m) {
    if (m == null) return "";
    for (var i = 0; i < TIERS.length; i++) if (Number(m) < TIERS[i][0]) return TIERS[i][1];
    return TIERS[TIERS.length - 1][1];
  }
  function label(key, which) { var p = PROVIDERS[key]; return p ? p[which] : (key ? key.charAt(0).toUpperCase() + key.slice(1) : ""); }
  // Rough advance width. The card leaves generous gaps, so an estimate within a few percent is
  // enough to place a word after a number without measuring text we have not rendered yet.
  function wide(text, size, factor) { return Math.round(String(text).length * size * (factor || 0.58)); }

  // ---- the card ------------------------------------------------------------------------------

  function sticker(text, t) {
    var l = String(text).toUpperCase(), w = 44 + Math.round(l.length * 14.5), x = 1128 - w;
    return '<g transform="rotate(-3 ' + (x + w / 2) + ' 84)"><rect x="' + x + '" y="58" width="' + w + '" height="52" rx="26" fill="' + t.yellow + '"/>' +
      '<text x="' + (x + w / 2) + '" y="93" font-size="22" font-weight="800" letter-spacing="1.5" text-anchor="middle" fill="' + t.ink + '">' + esc(l) + '</text></g>';
  }

  function rankPill(v, t, x) {
    if (!v.rank) return "";
    var l = "#" + v.rank + (v.of ? " of " + v.of : ""), w = 34 + wide(l, 24, 0.6);
    return '<rect x="' + x + '" y="156" width="' + w + '" height="42" rx="21" fill="' + t.accent + '" opacity="0.18"/>' +
      '<text x="' + (x + w / 2) + '" y="185" font-size="24" font-weight="800" text-anchor="middle" fill="' + t.accent + '">' + esc(l) + '</text>';
  }

  function chips(v, t, y) {
    var keys = (v.providers || []).slice(0, 4);
    if (!keys.length) return "";
    var colors = [t.accent, t.accent2, t.mint, t.yellow], out = [], x = 72;
    for (var i = 0; i < keys.length; i++) {
      var l = label(keys[i], 1), w = 26 + wide(l, 20, 0.57) + 12;
      out.push('<rect x="' + x + '" y="' + y + '" width="' + w + '" height="38" rx="19" fill="' + colors[i % 4] + '" opacity="0.18"/>' +
        '<circle cx="' + (x + 18) + '" cy="' + (y + 19) + '" r="6" fill="' + colors[i % 4] + '"/>' +
        '<text x="' + (x + 32) + '" y="' + (y + 26) + '" font-size="20" font-weight="700" fill="' + t.fg + '">' + esc(l) + '</text>');
      x += w + 20;
      if (x > 640) break;   // the panel owns everything from x=716
    }
    return out.join("");
  }

  function planPanel(v, t) {
    // The right third of the card. It answers the question every reader of a comp score asks
    // first: measured against what? The plan and its price for the window, nothing else.
    var parts = String(v.plan || "").split(" + ").filter(Boolean).slice(0, 2);
    if (!parts.length) parts = ["no subscription matched"];
    var out = ['<rect x="716" y="246" width="412" height="264" rx="22" fill="' + t.panel + '" stroke="' + t.line + '" stroke-width="2"/>',
      '<text x="744" y="290" font-size="17" font-weight="800" letter-spacing="3" fill="' + t.muted + '">SCORED AGAINST</text>'];
    for (var i = 0; i < parts.length; i++) {
      out.push('<text x="744" y="' + (340 + i * 34) + '" font-size="' + (parts[i].length > 22 ? 21 : 26) +
        '" font-weight="800" fill="' + t.fg + '">' + esc(parts[i].slice(0, 32)) + '</text>');
    }
    var cy = 340 + 34 * parts.length + 46;
    var priced = v.plan_usd != null && Number(v.plan_usd) > 0;
    out.push('<text x="744" y="' + cy + '" font-size="40" font-weight="800" fill="' + t.accent + '">' +
      esc(priced ? money(v.plan_usd) : "list price only") + '</text>');
    out.push('<text x="744" y="' + (cy + 32) + '" font-size="18" fill="' + t.muted + '">' +
      esc(priced ? "what you paid for these " + (v.days_back == null ? 30 : v.days_back) + " days" : "nothing to measure against") + '</text>');
    return out.join("");
  }

  function svgFor(v, themeName) {
    var t = THEMES[themeName] || THEMES.dark;
    var total = money(v.comped_usd);
    var m = num(v.multiplier);
    var tier = v.tier || tierName(m);
    var who = v.handle ? "@" + v.handle : "anonymous";
    var tools = (v.harnesses || []).map(function (k) { return HARNESSES[k] || k; }).join(", ") || "your AI tools";
    var vs = m == null ? "no subscription matched, so this is list price only" : "";
    var cache = v.cache_share == null ? null : Math.round(Number(v.cache_share) * 100);
    var meta = [];
    if (cache != null) meta.push("cache read " + cache + "%");
    if (v.active_days != null && v.days_back != null) meta.push(v.active_days + " of " + v.days_back + " days active");
    if (v.sessions) meta.push(v.sessions.toLocaleString("en-US") + " sessions");
    meta.push("read from " + tools);

    var scoreLine = m == null
      ? '<text x="72" y="440" font-size="30" font-weight="700" fill="' + t.fg + '">' + esc(vs) + '</text>'
      : '<text x="72" y="440" font-size="60" font-weight="800" fill="' + t.accent + '">' + esc(mult(m)) + '</text>' +
        '<text x="' + (72 + wide(mult(m), 60, 0.62) + 18) + '" y="440" font-size="26" font-weight="700" fill="' + t.fg + '">comp score</text>';

    return '<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" font-family="' + FONT + '" role="img" aria-label="' +
      esc(who + ", comp score " + mult(m) + ", " + total + " of AI at full price") + '">' +
      '<rect width="' + W + '" height="' + H + '" fill="' + t.bg + '"/>' +
      '<defs><linearGradient id="cg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="' + t.accent + '"/><stop offset="1" stop-color="' + t.accent2 + '"/></linearGradient></defs>' +
      '<circle cx="1180" cy="-40" r="300" fill="' + t.blob1 + '" opacity="0.16"/>' +
      '<circle cx="40" cy="720" r="260" fill="' + t.blob2 + '" opacity="0.16"/>' +
      '<text x="72" y="96" font-size="34" font-weight="800" letter-spacing="-1" fill="' + t.fg + '">comped<tspan fill="' + t.accent + '">.</tspan></text>' +
      '<text x="212" y="96" font-size="20" font-weight="700" letter-spacing="2" fill="' + t.muted + '">LAST ' + esc(v.days_back == null ? 30 : v.days_back) + ' DAYS</text>' +
      (tier ? sticker(tier, t) : "") +
      '<text x="72" y="186" font-size="40" font-weight="800" fill="' + t.accent2 + '">' + esc(who) + '</text>' +
      rankPill(v, t, 72 + wide(who, 40, 0.6) + 22) +
      '<text x="72" y="322" font-size="104" font-weight="800" letter-spacing="-4" fill="' + t.fg + '">' + esc(total) + '</text>' +
      '<text x="72" y="372" font-size="30" font-weight="700" fill="' + t.muted + '">at full price</text>' +
      scoreLine +
      planPanel(v, t) +
      chips(v, t, 490) +
      '<rect x="72" y="548" width="1056" height="2" fill="' + t.line + '"/>' +
      '<text x="72" y="596" font-size="19" font-family="' + MONO + '" fill="' + t.muted + '">' + esc(meta.join(" · ")) + '</text>' +
      '<text x="72" y="636" font-size="17" font-family="' + MONO + '" fill="' + t.muted + '">list price, not a bill</text>' +
      '<text x="1128" y="638" font-size="26" font-weight="800" text-anchor="end" fill="' + t.accent + '">' + SITE + '</text>' +
      '</svg>';
  }

  function shareLine(v) {
    // The wording comped_core/render_report.share_text uses, so the line under the card and the
    // line in ~/comped/comped-share.txt read the same.
    var m = num(v.multiplier), total = money(v.comped_usd);
    var where = v.rank && v.of ? ", #" + v.rank + " of " + v.of + " on the " + SITE + " leaderboard" : "";
    if (m == null) {
      return total + " of AI at full price in the last " + (v.days_back == null ? 30 : v.days_back) +
        " days, comped by my subscription. What's your comp score? One line: " + SITE + " #gotcomped";
    }
    var names = (v.providers || []).slice(0, 2).map(function (k) { return label(k, 0); });
    var vendor = names.length ? names.join(" and ") : "My subscription";
    return "My comp score is " + mult(m) + " (" + (v.tier || tierName(m)) + ")" + where + ". " +
      vendor + " gave me " + total + " of AI for " + money(v.plan_usd) + " this month. What's yours? One line: " + SITE + " #gotcomped";
  }

  // ---- getting the numbers -------------------------------------------------------------------

  function b64urlDecode(s) {
    s = String(s).replace(/-/g, "+").replace(/_/g, "/");
    while (s.length % 4) s += "=";
    var bin = atob(s), bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder("utf-8").decode(bytes);
  }

  // The short keys comped_core/render_report.card_url writes. Kept short because the whole thing
  // has to survive being pasted into a terminal and back out again.
  function fromLink(raw) {
    var d = JSON.parse(b64urlDecode(raw));
    return {
      handle: d.h || "", multiplier: d.m == null ? null : d.m, tier: d.t || "", comped_usd: d.u,
      plan_usd: d.p == null ? null : d.p, plan: d.pl || "", providers: d.pv || [], harnesses: d.hs || [],
      days_back: d.d == null ? 30 : d.d, active_days: d.a, cache_share: d.c == null ? null : d.c,
      sessions: d.s || 0, rank: d.r || null, of: d.n || null, source: "link"
    };
  }

  function fromRow(r, of) {
    return {
      handle: r.anonymous ? r.handle : r.handle, multiplier: r.multiplier, tier: r.tier, comped_usd: r.comped_usd,
      plan_usd: r.plan_usd, plan: r.plan, providers: r.providers || [], harnesses: r.harnesses || [],
      days_back: r.days_back, active_days: r.active_days, cache_share: r.cache_share, sessions: 0,
      rank: r.rank, of: of, source: "board"
    };
  }

  function findOnBoard(handle) {
    return fetch("/api/leaderboard?sort=multiplier&limit=500", { credentials: "omit", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)); })
      .then(function (d) {
        if (!d || !d.ok) throw new Error("the board answered with something unexpected");
        var want = String(handle).toLowerCase();
        var row = null;
        for (var i = 0; i < d.rows.length; i++) {
          if (String(d.rows[i].handle).toLowerCase() === want) { row = d.rows[i]; break; }
        }
        if (!row) throw new Error("no row for " + handle);
        return fromRow(row, d.count);
      });
  }

  // ---- the page ------------------------------------------------------------------------------

  var state = { v: null, theme: "dark", svg: "" };
  var status = document.getElementById("card-status");
  var actions = document.getElementById("card-actions");
  var lineBox = document.getElementById("card-line");
  var input = document.getElementById("card-handle");
  var form = document.getElementById("card-find");

  function say(text) { if (status) status.textContent = text; }

  function draw() {
    if (!state.v) return;
    state.svg = svgFor(state.v, state.theme);
    stage.innerHTML = state.svg;
    if (actions) actions.hidden = false;
    if (lineBox) { lineBox.hidden = false; lineBox.textContent = shareLine(state.v); }
    var text = shareLine(state.v);
    var x = document.getElementById("post-x");
    var li = document.getElementById("post-li");
    if (x) x.href = "https://x.com/intent/post?text=" + encodeURIComponent(text);
    if (li) li.href = "https://www.linkedin.com/feed/?shareActive=true&text=" + encodeURIComponent(text);
  }

  function show(v, note) {
    state.v = v;
    draw();
    say(note);
  }

  function pngBlob(scale) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () {
        var c = document.createElement("canvas");
        c.width = W * scale; c.height = H * scale;
        var ctx = c.getContext("2d");
        ctx.drawImage(img, 0, 0, c.width, c.height);
        c.toBlob(function (b) { b ? resolve(b) : reject(new Error("the browser would not make a PNG")); }, "image/png");
      };
      img.onerror = function () { reject(new Error("the browser would not draw the card")); };
      // A data: URL, so the canvas is never tainted and toBlob is allowed to hand the file back.
      img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(state.svg);
    });
  }

  function fileName() {
    var h = (state.v && state.v.handle ? state.v.handle : "comped").replace(/[^A-Za-z0-9_-]+/g, "-");
    return "comped-card-" + h + ".png";
  }

  var dl = document.getElementById("dl-png");
  if (dl) dl.addEventListener("click", function () {
    dl.disabled = true;
    pngBlob(2).then(function (b) {
      var url = URL.createObjectURL(b);
      var a = document.createElement("a");
      a.href = url; a.download = fileName();
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
      say("Saved " + fileName() + ", 2400×1350, ready to attach.");
    }).catch(function (e) {
      say("Couldn't make the PNG here (" + e.message + "). Right-click the card and save the image instead.");
    }).then(function () { dl.disabled = false; });
  });

  var cp = document.getElementById("copy-png");
  if (cp) cp.addEventListener("click", function () {
    if (!window.ClipboardItem || !navigator.clipboard || !navigator.clipboard.write) {
      return say("This browser can't copy images. Use Download the PNG instead.");
    }
    cp.disabled = true;
    pngBlob(2).then(function (b) {
      return navigator.clipboard.write([new window.ClipboardItem({ "image/png": b })]);
    }).then(function () {
      cp.textContent = "Copied";
      setTimeout(function () { cp.textContent = "Copy the image"; }, 1800);
    }).catch(function () {
      say("Copying the image was refused. Use Download the PNG instead.");
    }).then(function () { cp.disabled = false; });
  });

  var cl = document.getElementById("copy-link");
  if (cl) cl.addEventListener("click", function () {
    var url = location.href;
    var done = function () { cl.textContent = "Copied"; setTimeout(function () { cl.textContent = "Copy the link"; }, 1800); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(done, function () { say(url); });
    else say(url);
  });

  Array.prototype.forEach.call(document.querySelectorAll("[data-card-theme]"), function (b) {
    b.addEventListener("click", function () {
      state.theme = b.getAttribute("data-card-theme");
      Array.prototype.forEach.call(document.querySelectorAll("[data-card-theme]"), function (x) { x.classList.toggle("on", x === b); });
      draw();
    });
  });

  function lookup(handle) {
    handle = String(handle || "").trim().replace(/^@/, "");
    if (!handle) return say("Type the handle you posted under.");
    say("Looking for " + handle + " on the board…");
    findOnBoard(handle).then(function (v) {
      history.replaceState(null, "", "card.html?h=" + encodeURIComponent(v.handle));
      show(v, "Drawn from " + v.handle + "'s row on the board.");
    }).catch(function (e) {
      say(/^no row/.test(e.message)
        ? "Nothing on the board under \u201c" + handle + "\u201d yet. Run comped with handle=" + handle + " and it will be there in about ten seconds."
        : "Couldn't read the board (" + e.message + "). Try again in a moment.");
    });
  }

  if (form) form.addEventListener("submit", function (e) { e.preventDefault(); lookup(input && input.value); });

  // Boot: the link comped printed wins, then ?h=, then an empty page waiting for a handle.
  var frag = /(?:^|[#&])c=([A-Za-z0-9_-]+)/.exec(location.hash || "");
  var q = /(?:^|[?&])h=([^&]*)/.exec(location.search || "");
  if (frag) {
    try {
      show(fromLink(frag[1]), "Drawn from the link comped printed on your machine. Nothing after the hash was sent anywhere.");
      if (input && state.v.handle) input.value = state.v.handle;
    } catch (e) {
      say("That link is damaged. Copy the whole line comped printed, including everything after the hash.");
    }
  } else if (q) {
    var h = decodeURIComponent(q[1].replace(/\+/g, " "));
    if (input) input.value = h;
    lookup(h);
  }
})();
