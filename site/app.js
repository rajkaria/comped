// Everything on this page is arithmetic and animation done in your browser.
// No dependency, no analytics, no third party. The one fetch this site makes is board.js asking
// this same origin for the leaderboard.
(function () {
  "use strict";

  var calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- copy buttons ------------------------------------------------------------------------
  document.querySelectorAll("button.copy").forEach(function (b) {
    b.addEventListener("click", function () {
      var el = document.querySelector(b.dataset.copy);
      var text = el.textContent.trim();
      var done = function () {
        var was = b.textContent;
        b.textContent = "Copied";
        b.classList.add("done");
        setTimeout(function () { b.textContent = was; b.classList.remove("done"); }, 1600);
      };
      if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(done, function () {});
      }
    });
  });

  // ---- "Get my comp score": scroll to the one line and put the Copy button in focus ----------
  document.querySelectorAll('a[href="#get"]').forEach(function (a) {
    a.addEventListener("click", function (e) {
      var target = document.getElementById("get");
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
      setTimeout(function () {
        var b = target.querySelector("button.copy");
        if (b) b.focus({ preventScroll: true });
      }, calm ? 0 : 500);
    });
  });

  // ---- the plan ladder ---------------------------------------------------------------------
  // The point of the toy is the point of the tool: you pick nothing. One number in, every plan
  // priced at once, and the row that matches your subscription is yours to read.
  var spend = document.getElementById("spend");
  var spendOut = document.getElementById("spend-out");
  var ladder = document.getElementById("ladder");
  var verdict = document.getElementById("verdict");

  function money(n) { return "$" + Math.round(n).toLocaleString(); }

  function mult(m) { return (m < 10 ? m.toFixed(1) : Math.round(m)) + "×"; }

  function quip(m) {
    if (m < 1) return "Your subscription is losing to the API. Either you barely used it, or you should be on pay-as-you-go.";
    if (m < 2) return "About break-even. You're paying roughly what the tokens are worth.";
    if (m < 5) return "Comfortably ahead. The plan is doing its job.";
    if (m < 12) return "You are getting comped properly. This is the part where you tell your team.";
    if (m < 30) return "At this point the subscription is less a purchase than a hostage situation, and you are not the hostage.";
    if (m < 80) return "Someone in a pricing meeting is going to see this and go very quiet.";
    return "Please stop. There is nothing left to comp.";
  }

  function renderLadder() {
    if (!spend || !ladder) return;
    var listed = parseFloat(spend.value) || 0;
    var rows = Array.prototype.slice.call(ladder.querySelectorAll("li"));
    var best = 0;
    var assumed = 1;
    rows.forEach(function (li) {
      var cost = parseFloat(li.dataset.cost) || 0;
      var m = cost > 0 ? listed / cost : 0;
      if (m > best) best = m;
      if (li.classList.contains("on")) assumed = m;
      li.querySelector(".pm").textContent = mult(m);
    });
    rows.forEach(function (li) {
      var m = (parseFloat(li.dataset.cost) || 0) > 0 ? listed / parseFloat(li.dataset.cost) : 0;
      // A log scale, because a $20 row against a $200 row is otherwise all bar and no bar.
      var w = best > 0 ? Math.max(6, 100 * Math.log(1 + m) / Math.log(1 + best)) : 6;
      li.querySelector(".pbar i").style.width = w.toFixed(1) + "%";
    });
    if (spendOut) spendOut.textContent = money(listed);
    if (verdict) {
      verdict.innerHTML = "On the safe assumption — <b>Claude Max 20×</b> — your score is <b>" +
        mult(assumed) + "</b>. " + quip(assumed);
    }
  }

  if (spend) {
    spend.addEventListener("input", renderLadder);
    renderLadder();
  }

  // ---- count the three big numbers up when they scroll into view ----------------------------
  function finalText(el) {
    var dp = parseInt(el.dataset.dp || "0", 10);
    return (el.dataset.prefix || "") + parseFloat(el.dataset.count).toLocaleString(undefined, {
      minimumFractionDigits: dp, maximumFractionDigits: dp
    }) + (el.dataset.suffix || "");
  }

  function countUp(el) {
    var target = parseFloat(el.dataset.count);
    var dp = parseInt(el.dataset.dp || "0", 10);
    var pre = el.dataset.prefix || "";
    var post = el.dataset.suffix || "";
    var started = null;
    var dur = 1100;
    // The finished number goes in first. If frames never come — a throttled tab, a headless
    // renderer, a browser that dislikes us — the reader sees the real figure, not a zero.
    el.textContent = finalText(el);
    setTimeout(function () { el.textContent = finalText(el); }, dur + 400);
    function frame(t) {
      if (started === null) started = t;
      var k = Math.min(1, (t - started) / dur);
      var eased = 1 - Math.pow(1 - k, 3);
      var v = target * eased;
      el.textContent = pre + v.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp }) + post;
      if (k < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  // ---- the detection terminal, one line at a time -------------------------------------------
  function playTerminal(term) {
    var lines = term.querySelectorAll(".ln");
    term.setAttribute("data-anim", "on");
    lines.forEach(function (ln, i) {
      setTimeout(function () { ln.classList.add("show"); }, 90 * i);
    });
    // Failsafe: whatever happened to those timers, the terminal is readable a moment later.
    setTimeout(function () { term.setAttribute("data-anim", "off"); }, 90 * lines.length + 1500);
  }

  if (!("IntersectionObserver" in window) || calm) {
    document.querySelectorAll("[data-count]").forEach(function (el) { el.textContent = finalText(el); });
    return;
  }

  // Reveal-on-scroll for the section blocks. Applied from script, so a reader without JS gets
  // the whole page rather than a column of invisible divs.
  var revealables = document.querySelectorAll(".stats li, .tile, .note, .promises li, ol.steps li, ol.howto li, .reassure div, .faq details, figure.card, .toy, .term");
  revealables.forEach(function (el) { el.classList.add("reveal"); });
  // The hidden-until-revealed state only exists while this class is on <html>, and it comes off
  // on a timer: a page whose content depends on an observer firing is a page that can go blank.
  var root = document.documentElement;
  root.classList.add("js-anim");
  setTimeout(function () { root.classList.remove("js-anim"); }, 2500);

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      var el = e.target;
      el.classList.add("in");
      if (el.hasAttribute("data-count")) countUp(el);
      if (el.id === "term") playTerminal(el);
      io.unobserve(el);
    });
  }, { rootMargin: "0px 0px -12% 0px", threshold: 0.15 });

  revealables.forEach(function (el) { io.observe(el); });
  document.querySelectorAll("[data-count]").forEach(function (el) { io.observe(el); });
})();
