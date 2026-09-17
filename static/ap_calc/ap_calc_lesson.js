/**
 * AP Calculus lesson interactions: secant slider, limit approach, graph tracer.
 */
(function () {
  "use strict";

  var PURPLE = "#6a4ce6";
  var LEFT = "#2563eb";
  var RIGHT = "#ea580c";
  var GREEN = "#059669";
  var GRID = "#e8e4ff";

  function drawGrid(svg, x0, y0, x1, y1, cols, rows) {
    var g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("data-ap-grid", "");
    for (var i = 0; i <= cols; i++) {
      var x = x0 + (x1 - x0) * i / cols;
      var ln = document.createElementNS("http://www.w3.org/2000/svg", "line");
      ln.setAttribute("x1", x);
      ln.setAttribute("y1", y0);
      ln.setAttribute("x2", x);
      ln.setAttribute("y2", y1);
      ln.setAttribute("stroke", GRID);
      ln.setAttribute("stroke-width", "1");
      g.appendChild(ln);
    }
    for (var j = 0; j <= rows; j++) {
      var y = y0 + (y1 - y0) * j / rows;
      var ln2 = document.createElementNS("http://www.w3.org/2000/svg", "line");
      ln2.setAttribute("x1", x0);
      ln2.setAttribute("y1", y);
      ln2.setAttribute("x2", x1);
      ln2.setAttribute("y2", y);
      ln2.setAttribute("stroke", GRID);
      ln2.setAttribute("stroke-width", "1");
      g.appendChild(ln2);
    }
    var ax = document.createElementNS("http://www.w3.org/2000/svg", "line");
    ax.setAttribute("x1", x0);
    ax.setAttribute("y1", y1);
    ax.setAttribute("x2", x1);
    ax.setAttribute("y2", y1);
    ax.setAttribute("stroke", "#4c3d99");
    ax.setAttribute("stroke-width", "2");
    g.appendChild(ax);
    var ay = document.createElementNS("http://www.w3.org/2000/svg", "line");
    ay.setAttribute("x1", x0);
    ay.setAttribute("y1", y0);
    ay.setAttribute("x2", x0);
    ay.setAttribute("y2", y1);
    ay.setAttribute("stroke", "#4c3d99");
    ay.setAttribute("stroke-width", "2");
    g.appendChild(ay);
    svg.insertBefore(g, svg.firstChild.nextSibling);
  }

  function initSecantDemo(root) {
    var slider = root.querySelector("[data-ap-secant-slider]");
    if (!slider) return;
    var a = parseFloat(root.getAttribute("data-a") || "2");
    var slopeLimit = parseFloat(root.getAttribute("data-slope-limit") || "4");
    var hVal = root.querySelector("[data-ap-h-val]");
    var rateVal = root.querySelector("[data-ap-rate-val]");
    var riseVal = root.querySelector("[data-ap-rise-val]");
    var runVal = root.querySelector("[data-ap-run-val]");
    var formulaVal = root.querySelector("[data-ap-formula-val]");
    var svg = root.querySelector(".ap-secant-svg");
    if (!svg) return;

    var padL = 56, padR = 24, padT = 28, padB = 44;
    var W = 520, H = 320;
    var xMin = 0, xMax = 4.2, yMin = 0, yMax = 18;

    function s(t) {
      return t * t + 1;
    }

    function mapX(t) {
      return padL + (t - xMin) / (xMax - xMin) * (W - padL - padR);
    }

    function mapY(val) {
      return H - padB - (val - yMin) / (yMax - yMin) * (H - padT - padB);
    }

    if (!svg.querySelector("[data-ap-grid]")) {
      drawGrid(svg, padL, padT, W - padR, H - padB, 5, 4);
      var xLbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
      xLbl.setAttribute("x", W - padR);
      xLbl.setAttribute("y", H - 8);
      xLbl.setAttribute("text-anchor", "end");
      xLbl.setAttribute("font-size", "12");
      xLbl.setAttribute("fill", "#4c3d99");
      xLbl.textContent = "t (s)";
      svg.appendChild(xLbl);
      var yLbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
      yLbl.setAttribute("x", "14");
      yLbl.setAttribute("y", (padT + H - padB) / 2);
      yLbl.setAttribute("text-anchor", "middle");
      yLbl.setAttribute("font-size", "12");
      yLbl.setAttribute("fill", "#4c3d99");
      yLbl.setAttribute("transform", "rotate(-90 14 " + (padT + H - padB) / 2 + ")");
      yLbl.textContent = "s (m)";
      svg.appendChild(yLbl);
    }

    var curve = svg.querySelector("[data-ap-curve]");
    var secant = svg.querySelector("[data-ap-secant]");
    var tangent = svg.querySelector("[data-ap-tangent]");
    var rise = svg.querySelector("[data-ap-rise]");
    var run = svg.querySelector("[data-ap-run]");
    var risePoly = svg.querySelector("[data-ap-rise-poly]");
    var fixed = svg.querySelector("[data-ap-fixed]");
    var moving = svg.querySelector("[data-ap-moving]");
    var lblRise = svg.querySelector("[data-ap-lbl-rise]");
    var lblRun = svg.querySelector("[data-ap-lbl-run]");

    function update() {
      var h = parseFloat(slider.value);
      var rate = (s(a + h) - s(a)) / h;
      var deltaS = s(a + h) - s(a);
      if (hVal) hVal.textContent = h.toFixed(2);
      if (rateVal) rateVal.textContent = rate.toFixed(2);
      if (riseVal) riseVal.textContent = deltaS.toFixed(2);
      if (runVal) runVal.textContent = h.toFixed(2);
      if (formulaVal) {
        formulaVal.textContent =
          "[" + deltaS.toFixed(2) + " m] ÷ [" + h.toFixed(2) + " s] = " + rate.toFixed(2) + " m/s";
      }

      var pts = [];
      for (var t = 0; t <= xMax; t += 0.06) {
        pts.push(mapX(t).toFixed(1) + "," + mapY(s(t)).toFixed(1));
      }
      if (curve) curve.setAttribute("d", "M" + pts.join(" L"));

      var x0 = a;
      var y0 = s(a);
      var x1 = a + h;
      var y1 = s(x1);
      var m = (y1 - y0) / (x1 - x0);
      var sx0 = 0.4;
      var sx1 = 4.0;
      if (secant) {
        secant.setAttribute("x1", mapX(sx0));
        secant.setAttribute("y1", mapY(y0 + m * (sx0 - x0)));
        secant.setAttribute("x2", mapX(sx1));
        secant.setAttribute("y2", mapY(y0 + m * (sx1 - x0)));
      }
      if (tangent) {
        tangent.setAttribute("x1", mapX(sx0));
        tangent.setAttribute("y1", mapY(y0 + slopeLimit * (sx0 - a)));
        tangent.setAttribute("x2", mapX(sx1));
        tangent.setAttribute("y2", mapY(y0 + slopeLimit * (sx1 - a)));
      }
      var cx0 = mapX(x0), cy0 = mapY(y0);
      var cx1 = mapX(x1), cy1 = mapY(y1);
      if (rise) {
        rise.setAttribute("x1", cx1);
        rise.setAttribute("y1", cy0);
        rise.setAttribute("x2", cx1);
        rise.setAttribute("y2", cy1);
      }
      if (run) {
        run.setAttribute("x1", cx0);
        run.setAttribute("y1", cy0);
        run.setAttribute("x2", cx1);
        run.setAttribute("y2", cy0);
      }
      if (risePoly) {
        risePoly.setAttribute(
          "points",
          cx0 + "," + cy0 + " " + cx1 + "," + cy0 + " " + cx1 + "," + cy1
        );
      }
      if (fixed) {
        fixed.setAttribute("cx", cx0);
        fixed.setAttribute("cy", cy0);
      }
      if (moving) {
        moving.setAttribute("cx", cx1);
        moving.setAttribute("cy", cy1);
      }
      if (lblRise) {
        lblRise.setAttribute("x", cx1 + 8);
        lblRise.setAttribute("y", (cy0 + cy1) / 2);
        lblRise.textContent = "Δs = " + deltaS.toFixed(2);
      }
      if (lblRun) {
        lblRun.setAttribute("x", (cx0 + cx1) / 2);
        lblRun.setAttribute("y", cy0 + 18);
        lblRun.textContent = "h = " + h.toFixed(2);
      }
    }

    slider.addEventListener("input", update);
    update();
  }

  function initLimitApproach(root) {
    var slider = root.querySelector("[data-ap-limit-slider]");
    if (!slider) return;
    var c = parseFloat(root.getAttribute("data-c") || "3");
    var xRead = root.querySelector("[data-ap-x-read]");
    var yRead = root.querySelector("[data-ap-y-read]");
    var msgRead = root.querySelector("[data-ap-limit-msg]");
    var svg = root.querySelector(".ap-limit-svg");
    if (!svg) return;

    var padL = 56, padR = 24, padT = 28, padB = 44;
    var W = 520, H = 300;
    var xMin = 0, xMax = 6, yMin = 0, yMax = 12;

    function f(x) {
      return x + 2;
    }

    function mapX(x) {
      return padL + (x - xMin) / (xMax - xMin) * (W - padL - padR);
    }

    function mapY(y) {
      return H - padB - (y - yMin) / (yMax - yMin) * (H - padT - padB);
    }

    if (!svg.querySelector("[data-ap-grid]")) {
      drawGrid(svg, padL, padT, W - padR, H - padB, 6, 4);
    }

    var curve = svg.querySelector("[data-ap-curve]");
    var tracer = svg.querySelector("[data-ap-tracer]");
    var openPt = svg.querySelector("[data-ap-open]");
    var filledPt = svg.querySelector("[data-ap-filled]");

    function update() {
      var x = parseFloat(slider.value);
      var y = f(x);
      if (xRead) xRead.textContent = x.toFixed(2);
      if (yRead) yRead.textContent = y.toFixed(2);
      if (msgRead) {
        if (Math.abs(x - c) < 0.05) {
          msgRead.textContent = "At x = " + c + ", f(" + c + ") = 10 (filled dot) — but outputs still approach 5.";
        } else if (x < c) {
          msgRead.textContent = "From the left: as x → " + c + "⁻, f(x) → 5.";
        } else {
          msgRead.textContent = "From the right: as x → " + c + "⁺, f(x) → 5.";
        }
      }
      var pts = [];
      for (var t = 0.5; t <= 5.5; t += 0.08) {
        pts.push(mapX(t).toFixed(1) + "," + mapY(f(t)).toFixed(1));
      }
      if (curve) curve.setAttribute("d", "M" + pts.join(" L"));
      if (tracer) {
        tracer.setAttribute("cx", mapX(x));
        tracer.setAttribute("cy", mapY(y));
      }
      if (openPt) {
        openPt.setAttribute("cx", mapX(c));
        openPt.setAttribute("cy", mapY(5));
      }
      if (filledPt) {
        filledPt.setAttribute("cx", mapX(c));
        filledPt.setAttribute("cy", mapY(10));
      }
    }

    slider.addEventListener("input", update);
    update();
  }

  function initLimitTracer(root) {
    var slider = root.querySelector("[data-ap-trace-slider]");
    if (!slider) return;
    var c = parseFloat(root.getAttribute("data-c") || "2");
    var xRead = root.querySelector("[data-ap-trace-x]");
    var yRead = root.querySelector("[data-ap-trace-y]");
    var sideRead = root.querySelector("[data-ap-trace-side]");
    var limitRead = root.querySelector("[data-ap-trace-limit]");
    var svg = root.querySelector(".ap-trace-svg");
    if (!svg) return;

    var padL = 56, padR = 24, padT = 28, padB = 44;
    var W = 520, H = 300;
    var xMin = -0.5, xMax = 4.5, yMin = -0.5, yMax = 5;

    function fLeft(x) {
      return x + 1;
    }

    function fRight(x) {
      return -x + 5;
    }

    function mapX(x) {
      return padL + (x - xMin) / (xMax - xMin) * (W - padL - padR);
    }

    function mapY(y) {
      return H - padB - (y - yMin) / (yMax - yMin) * (H - padT - padB);
    }

    if (!svg.querySelector("[data-ap-grid]")) {
      drawGrid(svg, padL, padT, W - padR, H - padB, 5, 4);
    }

    var leftCurve = svg.querySelector("[data-ap-left]");
    var rightCurve = svg.querySelector("[data-ap-right]");
    var tracer = svg.querySelector("[data-ap-tracer]");
    var openPt = svg.querySelector("[data-ap-open]");
    var filledPt = svg.querySelector("[data-ap-filled]");
    var vLine = svg.querySelector("[data-ap-vline]");

    function update() {
      var x = parseFloat(slider.value);
      var y, side, limMsg;
      if (x < c - 0.02) {
        y = fLeft(x);
        side = "Left branch (x < " + c + ")";
        limMsg = "Approaching L⁻ = 3";
      } else if (x > c + 0.02) {
        y = fRight(x);
        side = "Right branch (x > " + c + ")";
        limMsg = "Approaching L⁺ = 3";
      } else {
        y = 1.5;
        side = "At x = " + c + " (filled dot)";
        limMsg = "f(" + c + ") = 1.5, but limit = 3";
      }
      if (xRead) xRead.textContent = x.toFixed(2);
      if (yRead) yRead.textContent = y.toFixed(2);
      if (sideRead) sideRead.textContent = side;
      if (limitRead) limitRead.textContent = limMsg;

      var lpts = [], rpts = [];
      for (var t = xMin; t <= c - 0.02; t += 0.06) {
        lpts.push(mapX(t).toFixed(1) + "," + mapY(fLeft(t)).toFixed(1));
      }
      for (var t2 = c + 0.02; t2 <= xMax; t2 += 0.06) {
        rpts.push(mapX(t2).toFixed(1) + "," + mapY(fRight(t2)).toFixed(1));
      }
      if (leftCurve) leftCurve.setAttribute("d", "M" + lpts.join(" L"));
      if (rightCurve) rightCurve.setAttribute("d", "M" + rpts.join(" L"));
      if (tracer) {
        tracer.setAttribute("cx", mapX(x));
        tracer.setAttribute("cy", mapY(y));
      }
      if (openPt) {
        openPt.setAttribute("cx", mapX(c));
        openPt.setAttribute("cy", mapY(3));
      }
      if (filledPt) {
        filledPt.setAttribute("cx", mapX(c));
        filledPt.setAttribute("cy", mapY(1.5));
      }
      if (vLine) {
        vLine.setAttribute("x1", mapX(x));
        vLine.setAttribute("x2", mapX(x));
        vLine.setAttribute("y1", padT);
        vLine.setAttribute("y2", H - padB);
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
    root.querySelectorAll("[data-ap-limit-demo]").forEach(initLimitApproach);
    root.querySelectorAll("[data-ap-trace-demo]").forEach(initLimitTracer);
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
