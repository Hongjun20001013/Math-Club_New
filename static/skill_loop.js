(function () {
  var wrap = document.querySelector("[data-skill-loop-phase]");
  if (!wrap) return;
  var itemId = wrap.getAttribute("data-item-id");
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  function postEvent(kind, extra, onDone) {
    fetch("/practice/skill-loop/sat.alg.linear_rate_remaining/event", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify(Object.assign({ kind: kind, item_id: itemId }, extra || {}))
    })
      .then(function (res) { return res.json(); })
      .then(function (data) { if (onDone) onDone(data); })
      .catch(function () { /* keep scoring server-side */ });
  }
  function showPanel(node, html) {
    if (!node) return;
    node.hidden = false;
    node.innerHTML = html;
  }
  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  var hintCrit = document.getElementById("sl-hint-critical");
  var hintLight = document.getElementById("sl-hint-light");
  var sol = document.getElementById("sl-solution");
  var hintPanel = document.getElementById("sl-hint-panel");
  var solPanel = document.getElementById("sl-solution-panel");
  if (hintLight) {
    hintLight.addEventListener("click", function () {
      var field = document.getElementById("sl-hint-level");
      if (field && field.value !== "critical") field.value = "light";
      postEvent("hint", { level: "light" }, function (data) {
        showPanel(
          hintPanel,
          "<h2>Small hint</h2><p data-sl-hint-text data-level=\"light\">" +
            escapeHtml(data && data.hint_text) +
            "</p>"
        );
      });
    });
  }
  if (hintCrit) {
    hintCrit.addEventListener("click", function () {
      var field = document.getElementById("sl-hint-level");
      if (field) field.value = "critical";
      postEvent("hint", { level: "critical" }, function (data) {
        showPanel(
          hintPanel,
          "<h2>Stronger hint</h2><p data-sl-hint-text data-level=\"critical\">" +
            escapeHtml(data && data.hint_text) +
            "</p>"
        );
      });
    });
  }
  if (sol) {
    sol.addEventListener("click", function () {
      var field = document.getElementById("sl-solution-viewed");
      if (field) field.value = "1";
      postEvent("solution", {}, function (data) {
        var solution = (data && data.solution) || {};
        var steps = solution.worked_steps || [];
        var html = "<h2>Walkthrough</h2>";
        html += "<p data-sl-solution-answer><strong>Correct answer:</strong> " +
          escapeHtml(solution.answer_display) + "</p>";
        html += "<ol data-sl-solution-steps>";
        steps.forEach(function (step) {
          html += "<li><strong>Step " + escapeHtml(step.step) + ".</strong> " +
            escapeHtml(step.do) +
            " <em class=\"sl-why\">Why: " + escapeHtml(step.why) + "</em></li>";
        });
        html += "</ol>";
        if (solution.explanation_check) {
          html += "<p data-sl-explanation-check><strong>Check:</strong> " +
            escapeHtml(solution.explanation_check) + "</p>";
        }
        showPanel(solPanel, html);
      });
    });
  }
})();
