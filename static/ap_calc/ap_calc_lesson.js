/**
 * AP Calculus lesson interactions: secant slider, guided hints.
 */
(function () {
  "use strict";

  function initSecantDemo(root) {
    var slider = root.querySelector("[data-ap-secant-slider]");
    if (!slider) return;
    var a = parseFloat(root.getAttribute("data-a") || "2");
    var baseY = parseFloat(root.getAttribute("data-base-y") || "5");
    var slopeLimit = parseFloat(root.getAttribute("data-slope-limit") || "4");
    var hVal = root.querySelector("[data-ap-h-val]");
    var rateVal = root.querySelector("[data-ap-rate-val]");
    var curve = root.querySelector("[data-ap-curve]");
    var secant = root.querySelector("[data-ap-secant]");
    var tangent = root.querySelector("[data-ap-tangent]");
    var fixed = root.querySelector("[data-ap-fixed]");
    var moving = root.querySelector("[data-ap-moving]");

    function s(t) {
      return t * t + 1;
    }

    function mapX(t) {
      return 52 + (t / 4.2) * (480 - 76);
    }

    function mapY(val) {
      return 260 - (val / 18) * (260 - 44);
    }

    function update() {
      var h = parseFloat(slider.value);
      var rate = (s(a + h) - s(a)) / h;
      if (hVal) hVal.textContent = h.toFixed(2);
      if (rateVal) rateVal.textContent = rate.toFixed(2);

      var pts = [];
      for (var t = 0; t <= 4.2; t += 0.08) {
        pts.push(mapX(t).toFixed(1) + "," + mapY(s(t)).toFixed(1));
      }
      if (curve) curve.setAttribute("d", "M" + pts.join(" L"));

      var x0 = a;
      var y0 = s(a);
      var x1 = a + h;
      var y1 = s(x1);
      var m = (y1 - y0) / (x1 - x0);
      var sx0 = 0.4;
      var sx1 = 4.1;
      if (secant) {
        secant.setAttribute("x1", mapX(sx0));
        secant.setAttribute("y1", mapY(y0 + m * (sx0 - x0)));
        secant.setAttribute("x2", mapX(sx1));
        secant.setAttribute("y2", mapY(y0 + m * (sx1 - x0)));
      }
      if (tangent) {
        tangent.setAttribute("x1", mapX(sx0));
        tangent.setAttribute("y1", mapY(baseY + slopeLimit * (sx0 - a)));
        tangent.setAttribute("x2", mapX(sx1));
        tangent.setAttribute("y2", mapY(baseY + slopeLimit * (sx1 - a)));
      }
      if (fixed) {
        fixed.setAttribute("cx", mapX(a));
        fixed.setAttribute("cy", mapY(y0));
      }
      if (moving) {
        moving.setAttribute("cx", mapX(x1));
        moving.setAttribute("cy", mapY(y1));
      }
    }

    slider.addEventListener("input", update);
    update();
  }

  function initHints(root) {
    var btn = root.querySelector("[data-ap-reveal-hint]");
    var items = root.querySelectorAll(".ap-hint-item");
    if (!btn || !items.length) return;
    var shown = 0;
    btn.addEventListener("click", function () {
      if (shown < items.length) {
        items[shown].classList.remove("ap-hint-item--hidden");
        shown += 1;
      }
      if (shown >= items.length) {
        btn.disabled = true;
        btn.textContent = "All hints shown";
      }
    });
  }

  function initAll(scope) {
    var root = scope || document;
    root.querySelectorAll("[data-ap-secant-demo]").forEach(initSecantDemo);
    root.querySelectorAll("[data-ap-hints]").forEach(function (el) {
      initHints(el.parentElement || el);
    });
  }

  window.initApCalcLesson = initAll;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initAll();
    });
  } else {
    initAll();
  }
})();
