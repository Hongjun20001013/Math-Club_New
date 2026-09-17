/**
 * AP Calculus Interactive Math Lab — unified spec-driven labs for 1.1–1.3.
 */
(function (global) {
  "use strict";

  var COLORS = {
    curve: "#6c4eff",
    rise: "#2563eb",
    run: "#ea580c",
    secant: "#475569",
    tangent: "#059669",
    left: "#2563eb",
    right: "#ea580c",
    grid: "#e8e4ff",
    axis: "#4c3d99",
  };

  var MISCONCEPTION_HINTS = {
    "average-vs-instantaneous": "An average rate needs a time interval. Instantaneous rate is the limiting value as the interval shrinks.",
    "finite-interval-called-instantaneous": "A secant slope on [a, a+h] is still an average over that interval.",
    "substitute-h-zero-too-early": "h = 0 gives 0/0 — undefined. Approach h → 0 with h ≠ 0.",
    "numerator-denominator-confusion": "Secant slope = rise Δs divided by run h.",
    "missing-units": "Include units: meters per second, not just the number.",
    "limit-equals-function-value": "The limit describes approach heights; f(c) is read from the filled point.",
    "swaps-input-output-targets": "x → c is the input target; L is the output height approached.",
    "approach-means-equality": "Near c is not the same as at c.",
    "notation-direction-error": "x → c⁻ means x stays less than c; x → c⁺ means x stays greater than c.",
    "filled-point-first": "Trace both branches before reading f(c) from the filled dot.",
    "checks-one-side-only": "Complete a left trace and a right trace before comparing.",
    "averages-unequal-one-sided-limits": "Do not average L⁻ and L⁺ — they must match exactly.",
    "endpoint-requires-two-sides": "At a domain endpoint, only the valid one-sided limit exists.",
    "infinite-limit-treated-as-finite": "If |y| grows without bound, the finite limit does not exist.",
    "open-closed-point-confusion": "Open circle = approach height; filled dot = function value.",
  };

  function prefersReducedMotion() {
    return global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function safeEval(expr, x) {
    var t = x;
    if (!/^[0-9x+\-*/().\s^t]+$/.test(String(expr).replace(/\*\*/g, "^"))) return NaN;
    var js = String(expr).replace(/\^/g, "**").replace(/\bt\b/g, "(" + t + ")");
    try {
      // eslint-disable-next-line no-new-func
      return Function("x", "t", "return " + js)(x, t);
    } catch (e) {
      return NaN;
    }
  }

  function el(tag, cls, html) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (html != null) node.innerHTML = html;
    return node;
  }

  function parseSpec(root) {
    var script = root.querySelector("[data-ap-lab-spec]");
    if (!script) return null;
    try {
      return JSON.parse(script.textContent || "{}");
    } catch (e) {
      return null;
    }
  }

  function emitLearningState(payload) {
    var detail = Object.assign({ timestamp: Date.now() }, payload);
    try {
      rootDispatch(rootFromPayload(payload), detail);
    } catch (e) { /* noop */ }
    if (global.ApCalcMathLab && global.ApCalcMathLab.onStateChange) {
      global.ApCalcMathLab.onStateChange(detail);
    }
    return detail;
  }

  var _lastRoot = null;
  function rootFromPayload(p) {
    return _lastRoot;
  }

  function rootDispatch(root, detail) {
    if (root) {
      root.dispatchEvent(new CustomEvent("ap-math-lab-state", { bubbles: true, detail: detail }));
    }
  }

  function announce(root, msg) {
    var live = root.querySelector("[data-ap-live]");
    if (live) live.textContent = msg;
  }

  function SVGPlot(svg, opts) {
    this.svg = svg;
    this.padL = opts.padL || 42;
    this.padR = opts.padR || 16;
    this.padT = opts.padT || 18;
    this.padB = opts.padB || 30;
    this.W = opts.W || 480;
    this.H = opts.H || 280;
    this.xMin = opts.xMin;
    this.xMax = opts.xMax;
    this.yMin = opts.yMin;
    this.yMax = opts.yMax;
    this.plotLeft = this.padL;
    this.plotRight = this.W - this.padR;
    this.plotTop = this.padT;
    this.plotBottom = this.H - this.padB;
    this._ensureGrid();
    this._drawAxes();
  }

  SVGPlot.prototype.mapX = function (x) {
    return this.plotLeft + (x - this.xMin) / (this.xMax - this.xMin) * (this.plotRight - this.plotLeft);
  };

  SVGPlot.prototype.mapY = function (y) {
    return this.plotBottom - (y - this.yMin) / (this.yMax - this.yMin) * (this.plotBottom - this.plotTop);
  };

  SVGPlot.prototype._ensureGrid = function () {
    var existing = this.svg.querySelector("[data-ap-grid]");
    if (existing) existing.remove();
    var g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("data-ap-grid", "");
    var x0 = this.plotLeft, y0 = this.plotTop, x1 = this.plotRight, y1 = this.plotBottom;
    for (var i = 0; i <= 4; i++) {
      var x = x0 + (x1 - x0) * i / 4;
      var ln = document.createElementNS("http://www.w3.org/2000/svg", "line");
      ln.setAttribute("x1", x); ln.setAttribute("y1", y0);
      ln.setAttribute("x2", x); ln.setAttribute("y2", y1);
      ln.setAttribute("stroke", COLORS.grid); ln.setAttribute("stroke-width", "1");
      g.appendChild(ln);
    }
    for (var j = 0; j <= 3; j++) {
      var y = y0 + (j * (y1 - y0)) / 3;
      var ln2 = document.createElementNS("http://www.w3.org/2000/svg", "line");
      ln2.setAttribute("x1", x0); ln2.setAttribute("y1", y);
      ln2.setAttribute("x2", x1); ln2.setAttribute("y2", y);
      ln2.setAttribute("stroke", COLORS.grid); ln2.setAttribute("stroke-width", "1");
      g.appendChild(ln2);
    }
    var layer = this.svg.querySelector("[data-ap-plot-layer]");
    if (layer) layer.insertBefore(g, layer.firstChild);
    else this.svg.insertBefore(g, this.svg.firstChild.nextSibling);
  };

  SVGPlot.prototype._drawAxes = function () {
    var ax = this.svg.querySelector("[data-ap-axis-x]");
    var ay = this.svg.querySelector("[data-ap-axis-y]");
    if (ax) {
      ax.setAttribute("x1", this.plotLeft);
      ax.setAttribute("y1", this.plotBottom);
      ax.setAttribute("x2", this.plotRight);
      ax.setAttribute("y2", this.plotBottom);
    }
    if (ay) {
      ay.setAttribute("x1", this.plotLeft);
      ay.setAttribute("y1", this.plotTop);
      ay.setAttribute("x2", this.plotLeft);
      ay.setAttribute("y2", this.plotBottom);
    }
  };

  SVGPlot.prototype.drawTargetX = function (targetX) {
    var line = this.svg.querySelector("[data-ap-target-x]");
    if (!line || targetX == null) return;
    var x = this.mapX(targetX);
    line.setAttribute("x1", x);
    line.setAttribute("y1", this.plotTop);
    line.setAttribute("x2", x);
    line.setAttribute("y2", this.plotBottom);
    line.style.visibility = "visible";
  };

  SVGPlot.prototype.pathFromFn = function (fn, x0, x1, step) {
    var pts = [];
    step = step || 0.05;
    for (var x = x0; x <= x1; x += step) {
      var y = safeEval(fn, x);
      if (!isFinite(y)) continue;
      var py = this.mapY(y);
      if (py < this.plotTop - 2 || py > this.plotBottom + 2) continue;
      pts.push(this.mapX(x).toFixed(1) + "," + py.toFixed(1));
    }
    if (pts.length < 2) return "";
    return "M" + pts.join(" L");
  };

  function setPoint(svg, sel, x, y, plot, visible) {
    var pt = svg.querySelector(sel);
    if (!pt) return;
    if (!visible || !isFinite(x) || !isFinite(y)) {
      pt.setAttribute("visibility", "hidden");
      return;
    }
    pt.setAttribute("cx", plot.mapX(x));
    pt.setAttribute("cy", plot.mapY(y));
    pt.setAttribute("visibility", "visible");
  }

  function Tutor(root, tags) {
    this.root = root;
    this.tags = tags || [];
    this.level = 0;
    this.panel = root.querySelector("[data-ap-tutor]");
    this.text = root.querySelector("[data-ap-tutor-text]");
    this.btn = root.querySelector("[data-ap-tutor-next]");
    var self = this;
    if (this.btn) {
      this.btn.addEventListener("click", function () { self.nextHint(); });
    }
  }

  Tutor.prototype.nextHint = function (context) {
    this.level = Math.min(5, this.level + 1);
    var msg = this._message(context);
    if (this.text) this.text.textContent = msg;
    if (this.level >= 5) {
      if (this.btn) this.btn.textContent = "Full solution shown";
      var reflect = this.root.querySelector("[data-ap-reflection]");
      if (reflect) reflect.hidden = false;
    }
    return this.level;
  };

  Tutor.prototype.reset = function () {
    this.level = 0;
    if (this.text) this.text.textContent = "Need a nudge? Tap for a hint (Level 1).";
    if (this.btn) this.btn.textContent = "Get hint";
    var reflect = this.root.querySelector("[data-ap-reflection]");
    if (reflect) reflect.hidden = true;
  };

  Tutor.prototype.misconception = function (tag) {
    return MISCONCEPTION_HINTS[tag] || "Re-read the graph/table and compare left vs right.";
  };

  Tutor.prototype._message = function (ctx) {
    ctx = ctx || {};
    var L = this.level;
    if (L === 1) return "Focus on what changes as you approach the target — do not jump to h = 0 or the filled dot yet.";
    if (L === 2) return "Use the slope triangle: orange run h, blue rise Δs, gray secant, green tangent.";
    if (L === 3) return ctx.setup || "Setup: secant slope = (s(a+h)−s(a))/h. For s(t)=t²+1 at t=2, slope = 4+h.";
    if (L === 4) return ctx.step || "With h=0.1, Δs=0.41 and slope=4.1. Both sides approach 4.";
    if (L === 5) {
      return (ctx.solution || "Instantaneous rate ≈ 4 m/s. Left and right secant slopes agree → tangent slope 4.")
        + " Reflection: explain in your own words why the answer holds.";
    }
    return ctx.solution || "Instantaneous rate ≈ 4 m/s. Left and right secant slopes agree → tangent slope 4.";
  };

  function buildControls(root, buttons) {
    var bar = root.querySelector("[data-ap-controls]") || el("div", "ap-lab-controls", "");
    if (!root.querySelector("[data-ap-controls]")) {
      bar.setAttribute("data-ap-controls", "");
      var anchor = root.querySelector(".ap-lab-explore") || root;
      anchor.insertBefore(bar, anchor.firstChild);
    }
    bar.innerHTML = "";
    buttons.forEach(function (b) {
      var btn = el("button", "ap-lab-btn" + (b.primary ? " ap-lab-btn--primary" : ""), b.label);
      btn.type = "button";
      if (b.action) btn.setAttribute("data-ap-action", b.action);
      if (b.disabled) btn.disabled = true;
      bar.appendChild(btn);
    });
    return bar;
  }

  function SecantTangentLab(root, spec) {
    _lastRoot = root;
    this.root = root;
    this.spec = spec;
    this.a = spec.targetX;
    this.hValues = spec.allowedValues.slice().sort(function (a, b) { return a - b; });
    this.hIndex = this.hValues.indexOf(1) >= 0 ? this.hValues.indexOf(1) : this.hValues.length - 1;
    this.tangentRevealed = false;
    this.predictLocked = null;
    this.leftEst = null;
    this.rightEst = null;
    this.animTimer = null;
    this.tutor = new Tutor(root, spec.misconceptionTags);
    this._bind();
    this._render();
  }

  SecantTangentLab.prototype.s = function (t) {
    return safeEval(this.spec.functionDefinition, t);
  };

  SecantTangentLab.prototype.slope = function (h) {
    return (this.s(this.a + h) - this.s(this.a)) / h;
  };

  SecantTangentLab.prototype._bind = function () {
    var self = this;
    var slider = this.root.querySelector("[data-ap-h-slider]");
    if (slider) {
      slider.min = 0;
      slider.max = this.hValues.length - 1;
      slider.step = 1;
      slider.setAttribute("aria-valuemin", "0");
      slider.setAttribute("aria-valuemax", String(this.hValues.length - 1));
      slider.addEventListener("input", function () {
        self.hIndex = parseInt(slider.value, 10);
        self._render();
      });
      slider.addEventListener("keydown", function (e) {
        if (e.key === "ArrowLeft") { self.hIndex = Math.max(0, self.hIndex - 1); slider.value = self.hIndex; self._render(); }
        if (e.key === "ArrowRight") { self.hIndex = Math.min(self.hValues.length - 1, self.hIndex + 1); slider.value = self.hIndex; self._render(); }
      });
    }
    this.root.querySelectorAll("[data-ap-action]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        self._action(btn.getAttribute("data-ap-action"));
      });
    });
    this.root.querySelectorAll("[data-ap-predict]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        self._predict(btn.getAttribute("data-ap-predict"));
      });
    });
    this.root.querySelectorAll("[data-ap-explain]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        self._explain(btn.getAttribute("data-ap-explain"));
      });
    });
    var tutorBtn = this.root.querySelector("[data-ap-tutor-next]");
    if (tutorBtn) {
      tutorBtn.addEventListener("click", function () {
        var lvl = self.tutor.nextHint({
          setup: "Secant slope = (s(a+h)−s(a))/h. At t=2 with s(t)=t²+1, slope = 4+h.",
          step: "h=0.1 → Δs=0.41, slope=4.1. h=−0.1 → slope=3.9.",
          solution: "Instantaneous rate = 4 m/s (tangent slope 4).",
        });
        emitLearningState({ lessonId: self.spec.lessonId, labId: self.spec.id, hintsUsed: lvl });
      });
    }
  };

  SecantTangentLab.prototype._action = function (action) {
    var self = this;
    if (action === "reset") {
      this.hIndex = this.hValues.indexOf(1) >= 0 ? this.hValues.indexOf(1) : 0;
      this.tangentRevealed = false;
      this.tutor.reset();
      this._render();
      return;
    }
    if (action === "left") {
      var neg = this.hValues.filter(function (h) { return h < 0; });
      this.hIndex = this.hValues.indexOf(neg[neg.length - 1]);
      this._render();
      return;
    }
    if (action === "right") {
      var pos = this.hValues.filter(function (h) { return h > 0; });
      this.hIndex = this.hValues.indexOf(pos[0]);
      this._render();
      return;
    }
    if (action === "animate") {
      if (prefersReducedMotion()) return;
      clearInterval(this.animTimer);
      var seq = this.hValues.filter(function (h) { return h !== 0; });
      var i = 0;
      this.animTimer = setInterval(function () {
        self.hIndex = self.hValues.indexOf(seq[i]);
        self._render();
        i += 1;
        if (i >= seq.length) clearInterval(self.animTimer);
      }, 700);
      return;
    }
    if (action === "reveal-tangent") {
      this.tangentRevealed = true;
      this._render();
    }
  };

  SecantTangentLab.prototype._predict = function (val) {
    this.predictLocked = val;
    var correct = val === "stabilize-4";
    var panel = this.root.querySelector("[data-ap-predict-result]");
    if (panel) {
      panel.hidden = false;
      panel.textContent = correct
        ? "Prediction recorded. Explore with h → 0 to verify."
        : this.tutor.misconception("average-vs-instantaneous");
    }
    emitLearningState({
      lessonId: this.spec.lessonId,
      labId: this.spec.id,
      prediction: val,
      correct: correct,
      misconceptionTags: correct ? [] : ["average-vs-instantaneous"],
    });
  };

  SecantTangentLab.prototype._explain = function (val) {
    var correct = val === "h-not-zero";
    var panel = this.root.querySelector("[data-ap-explain-result]");
    if (panel) {
      panel.hidden = false;
      panel.innerHTML = correct
        ? "<strong>Correct.</strong> h = 0 gives no interval; we approach h → 0 with h ≠ 0."
        : "<strong>Not quite.</strong> " + this.tutor.misconception("substitute-h-zero-too-early");
    }
    var conclusion = this.root.querySelector("[data-ap-conclusion]");
    if (conclusion && correct) conclusion.hidden = false;
    emitLearningState({
      lessonId: this.spec.lessonId,
      labId: this.spec.id,
      studentAnswer: val,
      correct: correct,
      misconceptionTags: correct ? [] : ["substitute-h-zero-too-early"],
    });
  };

  SecantTangentLab.prototype._render = function () {
    var h = this.hValues[this.hIndex];
    var slider = this.root.querySelector("[data-ap-h-slider]");
    if (slider) {
      slider.value = this.hIndex;
      slider.setAttribute("aria-valuenow", String(this.hIndex));
      slider.setAttribute("aria-valuetext", "h equals " + h + " seconds");
    }
    var rate = this.slope(h);
    var deltaS = this.s(a + h) - this.s(a);
    var units = this.spec.annotations.units || {};

    this.root.querySelectorAll("[data-ap-h-val]").forEach(function (n) { n.textContent = h; });
    this.root.querySelectorAll("[data-ap-rate-val]").forEach(function (n) { n.textContent = rate.toFixed(2); });
    this.root.querySelectorAll("[data-ap-rise-val]").forEach(function (n) { n.textContent = deltaS.toFixed(2); });
    this.root.querySelectorAll("[data-ap-run-val]").forEach(function (n) { n.textContent = h; });

    if (h < 0) this.leftEst = rate;
    if (h > 0) this.rightEst = rate;
    var agree = this.leftEst != null && this.rightEst != null && Math.abs(this.leftEst - this.rightEst) < 0.25;
    var leftEl = this.root.querySelector("[data-ap-left-est]");
    var rightEl = this.root.querySelector("[data-ap-right-est]");
    var agreeEl = this.root.querySelector("[data-ap-agree]");
    if (leftEl) leftEl.textContent = this.leftEst != null ? this.leftEst.toFixed(2) : "—";
    if (rightEl) rightEl.textContent = this.rightEst != null ? this.rightEst.toFixed(2) : "—";
    if (agreeEl) agreeEl.textContent = agree ? "Yes → 4 m/s" : "Explore both sides";

    var formula = this.root.querySelector("[data-ap-formula-val]");
    if (formula) {
      formula.textContent = "Δs/h = " + deltaS.toFixed(2) + "/" + h + " = " + rate.toFixed(2) + " " + (units.rate || "");
    }
    var secEq = this.root.querySelector("[data-ap-secant-eq]");
    if (secEq) secEq.textContent = "Secant slope = " + rate.toFixed(2);
    var tanEq = this.root.querySelector("[data-ap-tangent-eq]");
    if (tanEq) tanEq.textContent = this.tangentRevealed ? "Tangent slope = 4" : "Tangent hidden — tap Reveal";

    this._draw(h, rate, deltaS);
    this._updateTable(h);

    announce(this.root,
      "h equals " + h + " " + (units.input || "") + ". Delta s equals " + deltaS.toFixed(2) + " " + (units.output || "") +
      ". Average rate equals " + rate.toFixed(2) + " " + (units.rate || "") + ". Secant slope approaching 4.");

    emitLearningState({
      lessonId: this.spec.lessonId,
      labId: this.spec.id,
      graphState: { h: h, rate: rate, deltaS: deltaS },
      sliderValue: h,
    });
  };

  SecantTangentLab.prototype._updateTable = function (activeH) {
    var tbody = this.root.querySelector("[data-ap-table-body]");
    if (!tbody) return;
    tbody.innerHTML = "";
    var self = this;
    this.hValues.forEach(function (h) {
      var tr = document.createElement("tr");
      if (h === activeH) tr.className = "is-active";
      var slope = self.slope(h);
      tr.innerHTML = "<td>" + h + "</td><td>" + (self.s(self.a + h) - self.s(self.a)).toFixed(2) +
        "</td><td>" + slope.toFixed(2) + "</td><td>[" + self.a + ", " + (self.a + h) + "]</td>";
      tbody.appendChild(tr);
    });
  };

  SecantTangentLab.prototype._draw = function (h, rate, deltaS) {
    var svg = this.root.querySelector(".ap-lab-svg");
    if (!svg) return;
    var plot = new SVGPlot(svg, { xMin: 0, xMax: 4.2, yMin: 0, yMax: 16 });
    var a = this.a;
    var s = this.s.bind(this);
    var curve = svg.querySelector("[data-ap-curve]");
    if (curve) curve.setAttribute("d", plot.pathFromFn(this.spec.functionDefinition, 0, 4.2));
    var cx0 = plot.mapX(a), cy0 = plot.mapY(s(a));
    var cx1 = plot.mapX(a + h), cy1 = plot.mapY(s(a + h));
    var secant = svg.querySelector("[data-ap-secant]");
    var halo = svg.querySelector("[data-ap-secant-halo]");
    if (halo) { halo.setAttribute("x1", cx0); halo.setAttribute("y1", cy0); halo.setAttribute("x2", cx1); halo.setAttribute("y2", cy1); }
    if (secant) { secant.setAttribute("x1", cx0); secant.setAttribute("y1", cy0); secant.setAttribute("x2", cx1); secant.setAttribute("y2", cy1); }
    var rise = svg.querySelector("[data-ap-rise]");
    var run = svg.querySelector("[data-ap-run]");
    if (rise) { rise.setAttribute("x1", cx1); rise.setAttribute("y1", cy0); rise.setAttribute("x2", cx1); rise.setAttribute("y2", cy1); }
    if (run) { run.setAttribute("x1", cx0); run.setAttribute("y1", cy0); run.setAttribute("x2", cx1); run.setAttribute("y2", cy0); }
    var tangent = svg.querySelector("[data-ap-tangent]");
    if (tangent) {
      tangent.style.display = this.tangentRevealed ? "" : "none";
      var m = 4, y0 = s(a);
      tangent.setAttribute("x1", plot.mapX(0.4)); tangent.setAttribute("y1", plot.mapY(y0 + m * (0.4 - a)));
      tangent.setAttribute("x2", plot.mapX(4)); tangent.setAttribute("y2", plot.mapY(y0 + m * (4 - a)));
    }
    var fixed = svg.querySelector("[data-ap-fixed]");
    var moving = svg.querySelector("[data-ap-moving]");
    if (fixed) { fixed.setAttribute("cx", cx0); fixed.setAttribute("cy", cy0); }
    if (moving) { moving.setAttribute("cx", cx1); moving.setAttribute("cy", cy1); }
  };

  function branchY(spec, branch, x) {
    return safeEval(branch.fn, x);
  }

  function GraphCaseSwitcher(root, spec) {
    _lastRoot = root;
    this.root = root;
    this.spec = spec;
    this.caseIndex = 0;
    this.leftDone = false;
    this.rightDone = false;
    this.leftObs = "";
    this.rightObs = "";
    this.tutor = new Tutor(root, spec.misconceptionTags);
    this._bind();
    this._renderCase();
  }

  GraphCaseSwitcher.prototype.current = function () {
    return this.spec.cases[this.caseIndex];
  };

  GraphCaseSwitcher.prototype._bind = function () {
    var self = this;
    this.root.querySelectorAll("[data-ap-case]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        self.caseIndex = parseInt(btn.getAttribute("data-ap-case"), 10) || 0;
        self.leftDone = false;
        self.rightDone = false;
        self._renderCase();
      });
    });
    var slider = this.root.querySelector("[data-ap-x-slider]");
    if (slider) {
      slider.addEventListener("input", function () { self._trace(parseFloat(slider.value)); });
    }
    this.root.querySelectorAll("[data-ap-action]").forEach(function (btn) {
      btn.addEventListener("click", function () { self._action(btn.getAttribute("data-ap-action")); });
    });
    this.root.querySelector("[data-ap-lock-left]")?.addEventListener("click", function () { self._lockSide("left"); });
    this.root.querySelector("[data-ap-lock-right]")?.addEventListener("click", function () { self._lockSide("right"); });
  };

  GraphCaseSwitcher.prototype._action = function (action) {
    var c = this.current();
    var slider = this.root.querySelector("[data-ap-x-slider]");
    if (!slider) return;
    if (action === "left") { slider.value = (c.targetX - 0.35).toFixed(2); this._trace(parseFloat(slider.value)); }
    if (action === "right") { slider.value = (c.targetX + 0.35).toFixed(2); this._trace(parseFloat(slider.value)); }
    if (action === "reset") { slider.value = (c.targetX - 0.5).toFixed(2); this.leftDone = false; this.rightDone = false; this._renderCase(); }
  };

  GraphCaseSwitcher.prototype._trace = function (x) {
    var c = this.current();
    var y = branchY(c, c.branches[0], x);
    this.root.querySelectorAll("[data-ap-x-read]").forEach(function (n) { n.textContent = x.toFixed(2); });
    this.root.querySelectorAll("[data-ap-y-read]").forEach(function (n) { n.textContent = isFinite(y) ? y.toFixed(2) : "—"; });
    if (x < c.targetX - 0.02) {
      this.root.querySelector("[data-ap-side-msg]").textContent = "Tracing from the left toward x = " + c.targetX;
    } else if (x > c.targetX + 0.02) {
      this.root.querySelector("[data-ap-side-msg]").textContent = "Tracing from the right toward x = " + c.targetX;
    } else {
      this.root.querySelector("[data-ap-side-msg]").textContent = "At x = " + c.targetX + " — compare approach vs filled point.";
    }
    this._drawCase(x, y);
  };

  GraphCaseSwitcher.prototype._lockSide = function (side) {
    var c = this.current();
    if (side === "left") {
      this.leftDone = true;
      this.leftObs = String(c.leftLimit);
      this.root.querySelector("[data-ap-left-obs]").textContent = this.leftObs;
    } else {
      this.rightDone = true;
      this.rightObs = String(c.rightLimit);
      this.root.querySelector("[data-ap-right-obs]").textContent = this.rightObs;
    }
    if (this.leftDone && this.rightDone) {
      var panel = this.root.querySelector("[data-ap-limit-panel]");
      if (panel) panel.hidden = false;
      var same = c.leftLimit === c.rightLimit;
      this.root.querySelector("[data-ap-compare]").textContent = same ? "same" : "different";
      this.root.querySelector("[data-ap-limit-val]").textContent = c.twoSidedLimit != null ? c.twoSidedLimit : "DNE";
      this.root.querySelector("[data-ap-fc-val]").textContent = c.functionValue != null ? c.functionValue : "undefined";
    }
  };

  GraphCaseSwitcher.prototype._renderCase = function () {
    var self = this;
    var c = this.current();
    this.root.querySelectorAll("[data-ap-case]").forEach(function (btn) {
      var idx = parseInt(btn.getAttribute("data-ap-case"), 10) || 0;
      btn.classList.toggle("is-active", idx === self.caseIndex);
    });
    var title = this.root.querySelector("[data-ap-case-title]");
    if (title) title.textContent = "Case " + c.label + ": " + c.title;
    var slider = this.root.querySelector("[data-ap-x-slider]");
    if (slider) {
      slider.min = c.targetX - 0.5;
      slider.max = c.targetX + 0.5;
      slider.step = 0.05;
      slider.value = c.targetX - 0.4;
    }
    var panel = this.root.querySelector("[data-ap-limit-panel]");
    if (panel) panel.hidden = true;
    this.root.querySelector("[data-ap-left-obs]").textContent = "______";
    this.root.querySelector("[data-ap-right-obs]").textContent = "______";
    this.leftDone = false;
    this.rightDone = false;
    this._trace(parseFloat(slider.value));
  };

  GraphCaseSwitcher.prototype._drawCase = function (x, y) {
    var c = this.current();
    var svg = this.root.querySelector(".ap-lab-svg");
    if (!svg) return;
    var plot = new SVGPlot(svg, { xMin: 0, xMax: 6, yMin: -1, yMax: 11 });
    plot.drawTargetX(c.targetX);
    c.branches.forEach(function (br, i) {
      var path = svg.querySelector("[data-ap-branch='" + i + "']") || svg.querySelector("[data-ap-curve]");
      if (!path) return;
      var d = plot.pathFromFn(br.fn, br.x0, br.x1);
      path.setAttribute("d", d);
      path.setAttribute("stroke", br.color || COLORS.curve);
      path.style.display = d ? "" : "none";
    });
    var branch1 = svg.querySelector("[data-ap-branch='1']");
    if (branch1 && c.branches.length < 2) branch1.style.display = "none";
    var open0 = (c.openPoints || [])[0];
    var closed0 = (c.closedPoints || [])[0];
    setPoint(svg, "[data-ap-open-0]", open0 ? open0.x : NaN, open0 ? open0.y : NaN, plot, !!open0);
    setPoint(svg, "[data-ap-filled-0]", closed0 ? closed0.x : NaN, closed0 ? closed0.y : NaN, plot, !!closed0);
    setPoint(svg, "[data-ap-tracer]", x, y, plot, isFinite(y));
  };

  function OneSidedLimitTracer(root, spec) {
    _lastRoot = root;
    this.root = root;
    this.spec = spec;
    this.scenarioIndex = 0;
    this.step = 1;
    this.leftLocked = null;
    this.rightLocked = null;
    this.tutor = new Tutor(root, spec.misconceptionTags);
    this._bind();
    this._renderScenario();
  }

  OneSidedLimitTracer.prototype.scenario = function () {
    return this.spec.scenarios[this.scenarioIndex];
  };

  OneSidedLimitTracer.prototype._bind = function () {
    var self = this;
    this.root.querySelectorAll("[data-ap-scenario]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        self.scenarioIndex = parseInt(btn.getAttribute("data-ap-scenario"), 10) || 0;
        self.step = 1;
        self.leftLocked = null;
        self.rightLocked = null;
        self._renderScenario();
      });
    });
    var slider = this.root.querySelector("[data-ap-trace-slider]");
    if (slider) slider.addEventListener("input", function () { self._trace(parseFloat(slider.value)); });
    this.root.querySelectorAll("[data-ap-action]").forEach(function (btn) {
      btn.addEventListener("click", function () { self._action(btn.getAttribute("data-ap-action")); });
    });
    this.root.querySelector("[data-ap-lock-left]")?.addEventListener("click", function () { self._lock("left"); });
    this.root.querySelector("[data-ap-lock-right]")?.addEventListener("click", function () { self._lock("right"); });
    this.root.querySelector("[data-ap-lock-compare]")?.addEventListener("click", function () { self._compare(); });
  };

  OneSidedLimitTracer.prototype._action = function (action) {
    var sc = this.scenario();
    var slider = this.root.querySelector("[data-ap-trace-slider]");
    if (!slider) return;
    if (action === "left") { slider.value = (sc.targetX - 0.4).toFixed(2); this._trace(parseFloat(slider.value)); }
    if (action === "right") { slider.value = (sc.targetX + 0.4).toFixed(2); this._trace(parseFloat(slider.value)); }
    if (action === "reset") { this.step = 1; this.leftLocked = null; this.rightLocked = null; this._renderScenario(); }
  };

  OneSidedLimitTracer.prototype._trace = function (x) {
    var sc = this.scenario();
    var y = this._yAt(x);
    this.root.querySelector("[data-ap-trace-x]").textContent = x.toFixed(2);
    this.root.querySelector("[data-ap-trace-y]").textContent = isFinite(y) ? y.toFixed(2) : "∞";
    this._draw(x, y);
    this._updateDashboard();
  };

  OneSidedLimitTracer.prototype._yAt = function (x) {
    var sc = this.scenario();
    for (var i = 0; i < sc.branches.length; i++) {
      var br = sc.branches[i];
      if (x >= br.x0 && x <= br.x1) return safeEval(br.fn, x);
    }
    if (Math.abs(x - sc.targetX) < 0.03 && sc.functionValue != null) return sc.functionValue;
    return NaN;
  };

  OneSidedLimitTracer.prototype._lock = function (side) {
    var sc = this.scenario();
    if (side === "left") {
      this.leftLocked = sc.leftLimit;
      this.step = Math.max(this.step, 2);
    } else {
      this.rightLocked = sc.rightLimit;
      this.step = Math.max(this.step, 4);
    }
    this._updateDashboard();
  };

  OneSidedLimitTracer.prototype._compare = function () {
    this.step = 5;
    this._updateDashboard();
    var conclusion = this.root.querySelector("[data-ap-conclusion]");
    if (conclusion) conclusion.hidden = false;
  };

  OneSidedLimitTracer.prototype._updateDashboard = function () {
    var sc = this.scenario();
    var dash = this.root.querySelector("[data-ap-dashboard]");
    if (!dash) return;
    dash.querySelector("[data-d-left]").textContent = this.leftLocked != null ? this.leftLocked : "—";
    dash.querySelector("[data-d-right]").textContent = this.rightLocked != null ? this.rightLocked : "—";
    var same = sc.leftLimit != null && sc.rightLimit != null && sc.leftLimit === sc.rightLimit;
    dash.querySelector("[data-d-same]").textContent = sc.leftLimit == null || sc.rightLimit == null ? "n/a" : (same ? "same" : "different");
    dash.querySelector("[data-d-two]").textContent = sc.twoSidedLimit != null ? sc.twoSidedLimit : "DNE";
    dash.querySelector("[data-d-fc]").textContent = sc.functionValue != null ? sc.functionValue : "undefined";
    dash.querySelectorAll("[data-ap-step]").forEach(function (node) {
      var n = parseInt(node.getAttribute("data-ap-step"), 10);
      node.classList.toggle("is-done", n < this.step);
      node.classList.toggle("is-active", n === this.step);
    }.bind(this));
  };

  OneSidedLimitTracer.prototype._renderScenario = function () {
    var self = this;
    var sc = this.scenario();
    this.root.querySelectorAll("[data-ap-scenario]").forEach(function (btn) {
      var idx = parseInt(btn.getAttribute("data-ap-scenario"), 10) || 0;
      btn.classList.toggle("is-active", idx === self.scenarioIndex);
    });
    var note = this.root.querySelector("[data-ap-scenario-note]");
    if (note) note.textContent = sc.previewNote || "";
    var slider = this.root.querySelector("[data-ap-trace-slider]");
    if (slider) {
      var x0 = sc.domainMin != null ? sc.domainMin : (sc.targetX - 1);
      slider.min = x0;
      slider.max = sc.targetX + 1.5;
      slider.value = x0 + 0.3;
    }
    this._trace(parseFloat(slider.value));
  };

  OneSidedLimitTracer.prototype._draw = function (x, y) {
    var sc = this.scenario();
    var svg = this.root.querySelector(".ap-lab-svg");
    if (!svg) return;
    var xMin = sc.domainMin != null ? sc.domainMin - 0.3 : -0.5;
    var plot = new SVGPlot(svg, { xMin: xMin, xMax: 4.5, yMin: -1.5, yMax: 6 });
    plot.drawTargetX(sc.targetX);
    sc.branches.forEach(function (br, i) {
      var path = svg.querySelector("[data-ap-branch='" + i + "']");
      if (!path) return;
      var d = plot.pathFromFn(br.fn, br.x0, br.x1);
      path.setAttribute("d", d);
      path.setAttribute("stroke", br.color || COLORS.curve);
      path.style.display = d ? "" : "none";
    });
    var branch1 = svg.querySelector("[data-ap-branch='1']");
    if (branch1 && sc.branches.length < 2) branch1.style.display = "none";
    var open0 = (sc.openPoints || [])[0];
    var closed0 = (sc.closedPoints || [])[0];
    setPoint(svg, "[data-ap-open-0]", open0 ? open0.x : NaN, open0 ? open0.y : NaN, plot, !!open0);
    setPoint(svg, "[data-ap-filled-0]", closed0 ? closed0.x : NaN, closed0 ? closed0.y : NaN, plot, !!closed0);
    setPoint(svg, "[data-ap-tracer]", x, y, plot, isFinite(y));
  };

  function initMathLab(root) {
    var spec = parseSpec(root);
    if (!spec) return;
    var type = spec.labType;
    if (type === "SecantTangentLab") new SecantTangentLab(root, spec);
    else if (type === "GraphCaseSwitcher") new GraphCaseSwitcher(root, spec);
    else if (type === "OneSidedLimitTracer") new OneSidedLimitTracer(root, spec);
  }

  function initAll(scope) {
    (scope || document).querySelectorAll("[data-ap-math-lab]").forEach(initMathLab);
  }

  global.ApCalcMathLab = {
    init: initAll,
    initLab: initMathLab,
    MISCONCEPTION_HINTS: MISCONCEPTION_HINTS,
    safeEval: safeEval,
    onStateChange: null,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { initAll(); });
  }
})(window);
