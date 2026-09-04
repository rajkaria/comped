// Copy buttons. No dependency, no analytics, nothing phoning home.
document.querySelectorAll("button.copy").forEach(function (b) {
  b.addEventListener("click", function () {
    var el = document.querySelector(b.dataset.copy);
    navigator.clipboard.writeText(el.textContent.trim()).then(function () {
      var was = b.textContent;
      b.textContent = "Copied";
      b.classList.add("done");
      setTimeout(function () { b.textContent = was; b.classList.remove("done"); }, 1600);
    });
  });
});

// The multiplier toy: pure arithmetic, entirely in the page.
var plan = document.getElementById("plan");
var spend = document.getElementById("spend");
var verdict = document.getElementById("verdict");

function quip(m) {
  if (m < 1) return "Your subscription is losing to the API. Either you barely used it, or you should be on pay-as-you-go.";
  if (m < 2) return "About break-even. You're paying roughly what the tokens are worth.";
  if (m < 5) return "Comfortably ahead. The plan is doing its job.";
  if (m < 12) return "You are getting comped properly. This is the part where you tell your team.";
  if (m < 30) return "At this point the subscription is less a purchase than a hostage situation, and you are not the hostage.";
  if (m < 80) return "Someone in a pricing meeting is going to see this and go very quiet.";
  return "Please stop. There is nothing left to comp.";
}

function render() {
  var paid = parseFloat(String(plan.value).replace(/[^0-9.]/g, "")) || 0;
  var listed = parseFloat(spend.value) || 0;
  if (paid <= 0) { verdict.textContent = ""; return; }
  var m = listed / paid;
  var money = "$" + listed.toLocaleString(undefined, { maximumFractionDigits: 0 });
  verdict.innerHTML =
    money + " of tokens for $" + paid + '. You got comped <span class="big">' +
    (m < 10 ? m.toFixed(1) : Math.round(m)) + "×</span>." +
    '<span class="quip">' + quip(m) + "</span>";
}

plan.addEventListener("change", render);
spend.addEventListener("input", render);
render();
