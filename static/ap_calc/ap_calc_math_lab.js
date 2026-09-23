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
    "checks-left-only": "Complete a right trace before comparing.",
    "checks-right-only": "Complete a left trace before comparing.",
    "averages-unequal-one-sided-limits": "Do not average L⁻ and L⁺ — they must match exactly.",
    "endpoint-needs-two-sides": "At a domain endpoint, only the valid one-sided limit exists.",
    "infinite-treated-as-finite": "If |y| grows without bound, the finite limit does not exist.",
    "open-closed-point-confusion": "Open circle = approach height; filled dot = function value.",
    "tracer-at-target": "The tracer cannot sit at x = c — limits describe approach, not the point itself.",
    "DNE-without-reason": "State why the limit DNE: unequal sides, unbounded, or oscillatory.",
    "filled-point-determines-limit": "Branches determine the limit; the filled dot shows f(c) only.",
    "rise-run-reversed": "Secant slope = rise Δs divided by run h.",
  };

  var TRACER_EPS = 0.0005;

  function formatSecantNum(x) {
    if (x === 0) return "0";
    var abs = Math.abs(x);
    var decimals = abs >= 10 ? 2 : abs >= 1 ? 3 : 4;
    var text = x.toFixed(decimals);
    while (abs < 1 && abs > 0 && parseFloat(text) === 0 && decimals < 6) {
      decimals += 1;
      text = x.toFixed(decimals);
    }
    return text.replace(/(\.\d*?[1-9])0+$/, "$1").replace(/\.0+$/, "");
  }

  function formatSecantInterval(a, h) {
    return a + " → " + formatSecantNum(a + h);
  }

  var SCENARIO_ID_ALIASES = { "hole-filled": "hole-with-value" };

  function resolveScenarioIndex(spec) {
    if (spec.initialScenarioId && spec.scenarios) {
      var want = SCENARIO_ID_ALIASES[spec.initialScenarioId] || spec.initialScenarioId;
      for (var i = 0; i < spec.scenarios.length; i++) {
        var sid = spec.scenarios[i].id;
        if (sid === want || sid === spec.initialScenarioId) return i;
      }
    }
    return 0;
  }

  function formatApproachX(x, c, side) {
    if (side === "left" && x >= c - TRACER_EPS) {
      return "x → " + c + "⁻";
    }
    if (side === "right" && x <= c + TRACER_EPS) {
      return "x → " + c + "⁺";
    }
    var decimals = Math.abs(x - c) < 0.15 ? 3 : 2;
    var rounded = parseFloat(x.toFixed(decimals));
    while (side === "left" && rounded >= c) {
      decimals += 1;
      rounded = parseFloat(x.toFixed(decimals));
    }
    while (side === "right" && rounded <= c) {
      decimals += 1;
      rounded = parseFloat(x.toFixed(decimals));
    }
    if (Math.abs(x - c) < 0.05) {
      return side === "left" ? "x → " + c + "⁻" : "x → " + c + "⁺";
    }
    return "x = " + rounded;
  }

  function approachEndpoint(c, side, domainMin) {
    return clampTracerX(side === "left" ? c - TRACER_EPS : c + TRACER_EPS, c, side, domainMin);
  }

  function branchForApproach(sc, x) {
    var c = sc.targetX;
    var i, br;
    for (i = 0; i < sc.branches.length; i++) {
      br = sc.branches[i];
      if (x >= br.x0 && x <= br.x1) return br;
    }
    if (x < c) {
      var bestLeft = null;
      for (i = 0; i < sc.branches.length; i++) {
        br = sc.branches[i];
        if (br.x1 <= c && (!bestLeft || br.x1 > bestLeft.x1)) bestLeft = br;
      }
      return bestLeft || sc.branches[0];
    }
    if (x > c) {
      var bestRight = null;
      for (i = 0; i < sc.branches.length; i++) {
        br = sc.branches[i];
        if (br.x0 >= c && (!bestRight || br.x0 < bestRight.x0)) bestRight = br;
      }
      return bestRight || sc.branches[sc.branches.length - 1];
    }
    return null;
  }

  function evaluateScenarioY(sc, x, allowFc) {
    var c = sc.targetX;
    if (allowFc && Math.abs(x - c) < 0.03 && sc.functionValue != null) {
      return sc.functionValue;
    }
    if (!allowFc && Math.abs(x - c) < TRACER_EPS / 2) return NaN;
    var br = branchForApproach(sc, x);
    if (!br) return NaN;
    var y = safeEval(br.fn, x);
    if (!isFinite(y)) return sc.infinite ? y : NaN;
    return y;
  }

  function formatTracerY(y, sc) {
    if (y == null || isNaN(y)) return "—";
    if (!isFinite(y)) return sc && sc.infinite ? "∞" : "—";
    return y.toFixed(2);
  }

  function formatPresetLabel(x) {
    var s = String(x);
    var decimals = 0;
    if (s.indexOf(".") >= 0) {
      decimals = s.split(".")[1].length;
    }
    if (decimals < 2) decimals = 2;
    return "x = " + parseFloat(x.toFixed(decimals));
  }

  function nearTracerPresets(presets, c, side) {
    var valid = presets.filter(function (x) {
      return side === "left" ? x < c - TRACER_EPS : x > c + TRACER_EPS;
    });
    valid.sort(function (a, b) { return Math.abs(a - c) - Math.abs(b - c); });
    var picked = valid.slice(0, 2);
    picked.sort(function (a, b) { return a - b; });
    return picked;
  }

  function evaluateHoleWithValue(x) {
    return evaluateScenarioY({
      id: "hole-with-value",
      targetX: 2,
      infinite: false,
      functionValue: 1.5,
      branches: [
        { fn: "x + 1", x0: -0.5, x1: 1.98 },
        { fn: "-x + 5", x0: 2.02, x1: 4.5 },
      ],
    }, x, false);
  }

  function parseLimitValue(raw) {
    if (raw == null || raw === "") return null;
    var t = String(raw).trim().toLowerCase();
    if (t === "dne" || t === "undefined" || t === "none" || t === "n/a") return null;
    if (t === "inf" || t === "infinity" || t === "∞") return Infinity;
    if (t === "-inf" || t === "-infinity" || t === "-∞") return -Infinity;
    var n = parseFloat(t);
    return isNaN(n) ? null : n;
  }

  function limitsMatch(a, b, tol) {
    tol = tol == null ? 0.2 : tol;
    if (a == null && b == null) return true;
    if (a == null || b == null) return false;
    if (!isFinite(a) || !isFinite(b)) return a === b;
    return Math.abs(a - b) < tol;
  }

  function clampTracerX(x, c, side, domainMin) {
    if (side === "left") {
      var maxL = c - TRACER_EPS;
      var minL = domainMin != null ? domainMin : c - 2;
      return Math.min(maxL, Math.max(minL, x));
    }
    var minR = c + TRACER_EPS;
    return Math.max(minR, x);
  }

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

  function phaseFromLabStep(step) {
    if (step <= 0) return "understand";
    if (step <= 4) return "investigate";
    if (step <= 6) return "learn";
    return "explain";
  }

  function buildStructuredLessonState(lab) {
    if (!lab) return {};
    var sc = lab.scenario ? lab.scenario() : (lab.current ? lab.current() : {});
    return {
      lessonId: (lab.spec && lab.spec.lessonId) || "",
      slideId: (lab.spec && lab.spec.slideId) || "",
      learningObjective: (lab.spec && lab.spec.learningObjective) || "",
      currentPhase: phaseFromLabStep(lab.step != null ? lab.step : 0),
      selectedCase: sc.id || sc.caseId || "",
      prediction: lab.predictLocked || lab.prediction || null,
      leftObservation: lab.leftObs || lab.leftLocked || null,
      rightObservation: lab.rightObs || lab.rightLocked || null,
      comparison: lab.comparisonChoice || null,
      functionValue: sc.functionValue != null ? sc.functionValue : null,
      studentAnswer: lab.studentExplain || null,
      attemptCount: lab.attemptCount || 0,
      hintCount: (lab.tutor && lab.tutor.hintsUsed) || 0,
      misconceptionTags: lab.tutor && lab.tutor.lastMisconception ? [lab.tutor.lastMisconception] : [],
      labStep: lab.step != null ? lab.step : 0,
    };
  }

  function emitLearningState(root, payload) {
    var detail = Object.assign({
      timestamp: Date.now(),
      courseId: "ap-calc",
    }, payload);
    if (payload && payload.labInstance) {
      detail = Object.assign(detail, buildStructuredLessonState(payload.labInstance));
      delete detail.labInstance;
    }
    if (root) {
      _lastRoot = root;
      rootDispatch(root, detail);
    }
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

  function niceStep(span, target) {
    target = target || 5;
    if (span <= 0) return 1;
    var raw = span / target;
    var mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var norm = raw / mag;
    var nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
    return nice * mag;
  }

  function tickValues(vmin, vmax, target) {
    target = target || 5;
    if (vmax <= vmin) return [vmin];
    var step = niceStep(vmax - vmin, target);
    var start = Math.ceil(vmin / step - 1e-9) * step;
    var ticks = [];
    for (var v = start; v <= vmax + step * 0.001; v += step) ticks.push(v);
    return ticks;
  }

  function formatTick(v) {
    if (Math.abs(v) < 1e-9) return "0";
    if (Math.abs(v - Math.round(v)) < 1e-6) return String(Math.round(v));
    return String(parseFloat(v.toPrecision(2)));
  }

  function SVGPlot(svg, opts) {
    this.svg = svg;
    this.padL = opts.padL || 48;
    this.padR = opts.padR || 16;
    this.padT = opts.padT || 18;
    this.padB = opts.padB || 38;
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
      ax.setAttribute("stroke-width", "1.25");
    }
    if (ay) {
      ay.setAttribute("x1", this.plotLeft);
      ay.setAttribute("y1", this.plotTop);
      ay.setAttribute("x2", this.plotLeft);
      ay.setAttribute("y2", this.plotBottom);
      ay.setAttribute("stroke-width", "1.25");
    }
    this._drawTickLabels();
  };

  SVGPlot.prototype._drawTickLabels = function () {
    var old = this.svg.querySelector("[data-ap-ticks]");
    if (old) old.remove();
    var g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("data-ap-ticks", "");
    var self = this;
    var tickLen = 5;
    var fs = 10;
    tickValues(this.xMin, this.xMax, 5).forEach(function (xv) {
      var px = self.mapX(xv);
      var t1 = document.createElementNS("http://www.w3.org/2000/svg", "line");
      t1.setAttribute("x1", px); t1.setAttribute("y1", self.plotBottom);
      t1.setAttribute("x2", px); t1.setAttribute("y2", self.plotBottom + tickLen);
      t1.setAttribute("stroke", COLORS.axis); t1.setAttribute("stroke-width", "1");
      g.appendChild(t1);
      var txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
      txt.setAttribute("x", px);
      txt.setAttribute("y", self.plotBottom + tickLen + 13);
      txt.setAttribute("text-anchor", "middle");
      txt.setAttribute("font-size", fs);
      txt.setAttribute("fill", COLORS.axis);
      txt.textContent = formatTick(xv);
      g.appendChild(txt);
    });
    tickValues(this.yMin, this.yMax, 5).forEach(function (yv) {
      var py = self.mapY(yv);
      var t2 = document.createElementNS("http://www.w3.org/2000/svg", "line");
      t2.setAttribute("x1", self.plotLeft - tickLen); t2.setAttribute("y1", py);
      t2.setAttribute("x2", self.plotLeft); t2.setAttribute("y2", py);
      t2.setAttribute("stroke", COLORS.axis); t2.setAttribute("stroke-width", "1");
      g.appendChild(t2);
      var txt2 = document.createElementNS("http://www.w3.org/2000/svg", "text");
      txt2.setAttribute("x", self.plotLeft - 7);
      txt2.setAttribute("y", py + 3);
      txt2.setAttribute("text-anchor", "end");
      txt2.setAttribute("font-size", fs);
      txt2.setAttribute("fill", COLORS.axis);
      txt2.textContent = formatTick(yv);
      g.appendChild(txt2);
    });
    var layer = this.svg.querySelector("[data-ap-plot-layer]");
    if (layer) layer.insertBefore(g, layer.firstChild);
    else this.svg.appendChild(g);
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
      pts.push(this.mapX(x).toFixed(1) + "," + this.mapY(y).toFixed(1));
    }
    if (pts.length < 2) return "";
    return "M" + pts.join(" L");
  };

  function computePlotBounds(branches, openPoints, closedPoints, targetX) {
    var xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
    (branches || []).forEach(function (br) {
      xMin = Math.min(xMin, br.x0, targetX);
      xMax = Math.max(xMax, br.x1, targetX);
      var step = Math.max((br.x1 - br.x0) / 40, 0.05);
      for (var x = br.x0; x <= br.x1; x += step) {
        var y = safeEval(br.fn, x);
        if (isFinite(y)) {
          yMin = Math.min(yMin, y);
          yMax = Math.max(yMax, y);
        }
      }
    });
    function scanPts(pts) {
      (pts || []).forEach(function (p) {
        xMin = Math.min(xMin, p.x);
        xMax = Math.max(xMax, p.x);
        yMin = Math.min(yMin, p.y);
        yMax = Math.max(yMax, p.y);
      });
    }
    scanPts(openPoints);
    scanPts(closedPoints);
    if (!isFinite(xMin)) { xMin = targetX - 1; xMax = targetX + 1; yMin = -1; yMax = 5; }
    var xPad = Math.max((xMax - xMin) * 0.14, 0.4);
    var yPad = Math.max((yMax - yMin) * 0.2, 0.6);
    return { xMin: xMin - xPad, xMax: xMax + xPad, yMin: yMin - yPad, yMax: yMax + yPad };
  }

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

  function ContextualTutor(root, spec) {
    this.root = root;
    this.spec = spec || {};
    this.lessonId = spec.lessonId || "1.3";
    this.slideId = spec.slideId || "";
    this.level = 0;
    this.hintsUsed = 0;
    this.lastMisconception = null;
    this._ctx = {};
    this.text = root.querySelector("[data-ap-tutor-text]");
    this.tagEl = root.querySelector("[data-ap-tutor-tag]") || this.text;
    this.status = root.querySelector("[data-ap-tutor-status]");
    this.hintLevels = spec.hintLevels || [];
    this.misconceptions = spec.misconceptions || {};
    var self = this;
    this.root.querySelectorAll("[data-ap-tutor-action]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        self.handleAction(btn.getAttribute("data-ap-tutor-action"));
      });
    });
    var legacyBtn = root.querySelector("[data-ap-tutor-next]");
    if (legacyBtn) {
      legacyBtn.addEventListener("click", function () { self.handleAction("hint"); });
    }
  }

  ContextualTutor.prototype.misconception = function (tag) {
    var m = this.misconceptions[tag];
    if (m && m.studentFacingMessage) return m.studentFacingMessage;
    return MISCONCEPTION_HINTS[tag] || "Re-read the graph and compare left vs right.";
  };

  ContextualTutor.prototype.level1For = function (tag) {
    var m = this.misconceptions[tag];
    if (m && m.level1Hint) return m.level1Hint;
    return this.misconception(tag);
  };

  ContextualTutor.prototype.reset = function () {
    this.level = 0;
    this.hintsUsed = 0;
    this.lastMisconception = null;
    if (this.status) this.status.textContent = "Try first — then ask for help.";
    if (this.text) this.text.textContent = "";
    var reflect = this.root.querySelector("[data-ap-reflection]");
    if (reflect) reflect.hidden = true;
  };

  ContextualTutor.prototype.show = function (typeLabel, message) {
    if (this.tagEl && this.tagEl !== this.text) {
      this.tagEl.textContent = typeLabel ? "[" + typeLabel + "] " : "";
    }
    if (this.text) {
      this.text.textContent = (typeLabel ? typeLabel + ": " : "") + message;
    }
  };

  ContextualTutor.prototype.setContext = function (ctx) {
    this._ctx = ctx || {};
  };

  ContextualTutor.prototype._contextualEntry = function () {
    var ch = this.spec.contextualHints;
    if (!ch || !ch.sequence || !ch.sequence.length) return null;
    var ctx = this._ctx || {};
    var entry = ch.sequence[Math.min(this.level, ch.sequence.length) - 1];
    if (ch.caseOverrides && ctx.caseId && this.level >= 2) {
      var ov = ch.caseOverrides[ctx.caseId];
      if (ov && (this.level === 2 || this.level === 4)) entry = ov;
    }
    if (this.slideId === "1.2-4" && ctx.leftDone && !ctx.rightDone && this.level === 2) {
      entry = ch.sequence[1];
    }
    return entry;
  };

  ContextualTutor.prototype.nextHint = function (ctx) {
    if (ctx) this.setContext(ctx);
    this.level = Math.min(5, this.level + 1);
    this.hintsUsed += 1;
    var contextual = this._contextualEntry();
    if (contextual) {
      this.show(contextual.type, contextual.text);
    } else {
      var entry = this.hintLevels[this.level - 1];
      if (entry) {
        this.show(entry.type, entry.text);
      } else if (this.lessonId === "1.1") {
        this._secantFallback(this.level, ctx);
      } else {
        this.show("Observation hint", this.level1For("filled-point-first"));
      }
    }
    if (this.level >= 5) {
      var reflect = this.root.querySelector("[data-ap-reflection]");
      if (reflect) reflect.hidden = false;
    }
    return this.level;
  };

  ContextualTutor.prototype._secantFallback = function (L, ctx) {
    ctx = ctx || {};
    if (L === 1) this.show("Observation hint", "Watch how Δs and h change as you move the slider.");
    else if (L === 2) this.show("Strategy hint", "Use the slope triangle: orange run h, blue rise Δs.");
    else if (L === 3) this.show("Representation hint", ctx.setup || "Secant slope = Δs/h = 4+h at t=2.");
    else if (L === 4) this.show("Partial step", ctx.step || "h=0.1 → slope 4.1; h=−0.1 → slope 3.9.");
    else this.show("Full solution", ctx.solution || "Instantaneous rate ≈ 4 m/s.");
  };

  ContextualTutor.prototype.handleAction = function (action) {
    if (action === "hint") {
      return this.nextHint();
    }
    if (action === "mistake" && this.lastMisconception) {
      this.show("Error diagnosis", this.misconception(this.lastMisconception));
      return;
    }
    if (action === "why") {
      this.show("Strategy hint", this.lessonId === "1.1"
        ? "We approach h → 0 with h ≠ 0 because h = 0 gives no interval."
        : "Branches determine the limit; f(c) is read separately from the filled dot.");
      return;
    }
    if (action === "similar") {
      this.show("Strategy hint", "Similar problem: same structure with a different target x — trace both sides first.");
      return;
    }
    if (action === "check-explain") {
      this.show("Reflection", "Include left behavior, right behavior, whether they agree, and that f(c) is separate.");
    }
  };

  ContextualTutor.prototype.recordMisconception = function (tag) {
    this.lastMisconception = tag;
    this.show("Error diagnosis", this.misconception(tag));
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
    this.tutor = new ContextualTutor(root, spec);
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
    emitLearningState(this.root, {
      eventType: "prediction_submitted",
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
    emitLearningState(this.root, {
      eventType: "explanation_submitted",
      lessonId: this.spec.lessonId,
      labId: this.spec.id,
      answer: val,
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
    var deltaS = this.s(this.a + h) - this.s(this.a);
    var units = this.spec.annotations.units || {};

    this.root.querySelectorAll("[data-ap-h-val]").forEach(function (n) { n.textContent = h; });
    this.root.querySelectorAll("[data-ap-rate-val]").forEach(function (n) { n.textContent = formatSecantNum(rate); });
    this.root.querySelectorAll("[data-ap-rise-val]").forEach(function (n) { n.textContent = formatSecantNum(deltaS); });
    this.root.querySelectorAll("[data-ap-run-val]").forEach(function (n) { n.textContent = h; });

    if (h < 0) this.leftEst = rate;
    if (h > 0) this.rightEst = rate;
    var agree = this.leftEst != null && this.rightEst != null && Math.abs(this.leftEst - this.rightEst) < 0.25;
    var leftEl = this.root.querySelector("[data-ap-left-est]");
    var rightEl = this.root.querySelector("[data-ap-right-est]");
    var agreeEl = this.root.querySelector("[data-ap-agree]");
    if (leftEl) leftEl.textContent = this.leftEst != null ? formatSecantNum(this.leftEst) : "—";
    if (rightEl) rightEl.textContent = this.rightEst != null ? formatSecantNum(this.rightEst) : "—";
    if (agreeEl) agreeEl.textContent = agree ? "Yes → 4 m/s" : "Explore both sides";

    var formula = this.root.querySelector("[data-ap-formula-val]");
    if (formula) {
      formula.textContent = "Δs/h = " + formatSecantNum(deltaS) + "/" + h + " = " + formatSecantNum(rate) + " " + (units.rate || "");
    }
    var secEq = this.root.querySelector("[data-ap-secant-eq]");
    if (secEq) secEq.textContent = "Secant slope = " + formatSecantNum(rate);
    var tanEq = this.root.querySelector("[data-ap-tangent-eq]");
    if (tanEq) tanEq.textContent = this.tangentRevealed ? "Tangent slope = " + formatSecantNum(this.spec.tangent.slope) : "Tangent hidden — tap Reveal";

    this._draw(h, rate, deltaS);
    this._updateTable(h);

    announce(this.root,
      "h equals " + h + " " + (units.input || "") + ". Delta s equals " + formatSecantNum(deltaS) + " " + (units.output || "") +
      ". Average rate equals " + formatSecantNum(rate) + " " + (units.rate || "") + ".");

    emitLearningState(this.root, {
      eventType: "tracer_moved",
      lessonId: this.spec.lessonId,
      labId: this.spec.id,
      graphState: { h: h, rate: rate, deltaS: deltaS },
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
      tr.innerHTML = "<td>" + h + "</td><td>" + formatSecantNum(self.s(self.a + h) - self.s(self.a)) +
        "</td><td>" + formatSecantNum(slope) + "</td><td>" + formatSecantInterval(self.a, h) + "</td>";
      tbody.appendChild(tr);
    });
  };

  SecantTangentLab.prototype._draw = function (h, rate, deltaS) {
    var svg = this.root.querySelector(".ap-lab-svg");
    if (!svg) return;
    var plot = new SVGPlot(svg, { xMin: 0, xMax: 4.2, yMin: 0, yMax: 20 });
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
    this.tutor = new ContextualTutor(root, spec);
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
    var self = this;
    if (action === "trace-left" || action === "left") {
      this._animateTrace("left", approachEndpoint(c.targetX, "left", c.domainMin), function (x) {
        slider.value = x;
        self._trace(x);
      });
    }
    if (action === "trace-right" || action === "right") {
      this._animateTrace("right", approachEndpoint(c.targetX, "right", c.domainMin), function (x) {
        slider.value = x;
        self._trace(x);
      });
    }
    if (action === "reset") {
      this.leftDone = false;
      this.rightDone = false;
      this.tutor.reset();
      this._renderCase();
    }
  };

  GraphCaseSwitcher.prototype._animateTrace = function (side, endX, onFrame) {
    var c = this.current();
    var startX = side === "left" ? c.targetX - 0.4 : c.targetX + 0.4;
    startX = clampTracerX(startX, c.targetX, side, c.domainMin);
    if (prefersReducedMotion()) {
      onFrame(endX);
      return;
    }
    var frames = 12;
    var step = 0;
    var timer = setInterval(function () {
      step += 1;
      var t = step / frames;
      var x = startX + (endX - startX) * t;
      x = clampTracerX(x, c.targetX, side, c.domainMin);
      onFrame(x);
      if (step >= frames) clearInterval(timer);
    }, 40);
  };

  GraphCaseSwitcher.prototype._yAt = function (x) {
    return evaluateScenarioY(this.current(), x, false);
  };

  GraphCaseSwitcher.prototype._syncCaseModel = function () {
    var self = this;
    this.root.querySelectorAll("[data-ap-case-model]").forEach(function (panel) {
      var idx = parseInt(panel.getAttribute("data-ap-case-model"), 10) || 0;
      panel.hidden = idx !== self.caseIndex;
    });
    if (window.MathJax && window.MathJax.typesetPromise) {
      window.MathJax.typesetPromise([this.root]).catch(function () {});
    }
  };

  GraphCaseSwitcher.prototype._trace = function (x) {
    var c = this.current();
    var side = x < c.targetX ? "left" : "right";
    if (Math.abs(x - c.targetX) < TRACER_EPS) {
      x = approachEndpoint(c.targetX, side, c.domainMin);
    } else {
      x = clampTracerX(x, c.targetX, side, c.domainMin);
    }
    var y = this._yAt(x);
    this.tutor.setContext({ caseId: c.id, caseIndex: this.caseIndex, leftDone: this.leftDone, rightDone: this.rightDone });
    this.root.querySelectorAll("[data-ap-x-read]").forEach(function (n) {
      n.textContent = formatApproachX(x, c.targetX, side).replace("x = ", "").replace("x → ", "");
    });
    this.root.querySelectorAll("[data-ap-y-read]").forEach(function (n) { n.textContent = formatTracerY(y, c); });
    if (side === "left") {
      this.root.querySelector("[data-ap-side-msg]").textContent = "Tracing from the left toward x = " + c.targetX;
    } else {
      this.root.querySelector("[data-ap-side-msg]").textContent = "Tracing from the right toward x = " + c.targetX;
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
      slider.step = 0.001;
      slider.value = clampTracerX(c.targetX - 0.4, c.targetX, "left", c.domainMin);
    }
    var panel = this.root.querySelector("[data-ap-limit-panel]");
    if (panel) panel.hidden = true;
    this.root.querySelector("[data-ap-left-obs]").textContent = "______";
    this.root.querySelector("[data-ap-right-obs]").textContent = "______";
    this.leftDone = false;
    this.rightDone = false;
    this._syncCaseModel();
    this._trace(parseFloat(slider.value));
  };

  GraphCaseSwitcher.prototype._drawCase = function (x, y) {
    var c = this.current();
    var svg = this.root.querySelector(".ap-lab-svg");
    if (!svg) return;
    var bounds = computePlotBounds(c.branches, c.openPoints, c.closedPoints, c.targetX);
    var plot = new SVGPlot(svg, bounds);
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
    var i;
    for (i = 0; i < 2; i++) {
      var op = (c.openPoints || [])[i];
      var sel = "[data-ap-open-" + i + "]";
      setPoint(svg, sel, op ? op.x : NaN, op ? op.y : NaN, plot, !!op);
      var ptEl = svg.querySelector(sel);
      if (ptEl && op && c.branches[i]) ptEl.setAttribute("stroke", c.branches[i].color || COLORS.curve);
    }
    var closed0 = (c.closedPoints || [])[0];
    setPoint(svg, "[data-ap-filled-0]", closed0 ? closed0.x : NaN, closed0 ? closed0.y : NaN, plot, !!closed0);
    setPoint(svg, "[data-ap-tracer]", x, y, plot, isFinite(y));
  };

  function OneSidedLimitTracer(root, spec) {
    _lastRoot = root;
    this.root = root;
    this.spec = spec;
    this.scenarioIndex = resolveScenarioIndex(spec);
    this.step = 0;
    this.leftX = null;
    this.rightX = null;
    this.leftLocked = null;
    this.rightLocked = null;
    this.predictDone = false;
    this.fcConfirmed = false;
    this._yCache = {};
    this.tutor = new ContextualTutor(root, spec);
    this._bind();
    this._applyScenarioTabsVisibility();
    this._renderScenario();
    this._syncPanels();
  }

  OneSidedLimitTracer.prototype.scenario = function () {
    return this.spec.scenarios[this.scenarioIndex];
  };

  OneSidedLimitTracer.prototype._applyScenarioTabsVisibility = function () {
    var tabs = this.root.querySelector("[data-ap-scenario-tabs]");
    if (tabs && this.spec.showScenarioTabs === false) tabs.hidden = true;
  };

  OneSidedLimitTracer.prototype._bind = function () {
    var self = this;
    this.root.querySelectorAll("[data-ap-scenario]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        self.scenarioIndex = parseInt(btn.getAttribute("data-ap-scenario"), 10) || 0;
        self._resetFlow();
        self._renderScenario();
      });
    });
    var leftSlider = this.root.querySelector("[data-ap-trace-left-slider]");
    var rightSlider = this.root.querySelector("[data-ap-trace-right-slider]");
    if (leftSlider) {
      leftSlider.addEventListener("input", function () { self._traceLeft(parseFloat(leftSlider.value)); });
    }
    if (rightSlider) {
      rightSlider.addEventListener("input", function () { self._traceRight(parseFloat(rightSlider.value)); });
    }
    this.root.querySelectorAll("[data-ap-action]").forEach(function (btn) {
      btn.addEventListener("click", function () { self._action(btn.getAttribute("data-ap-action")); });
    });
    this.root.querySelector("[data-ap-predict-submit]")?.addEventListener("click", function () { self._submitPredict(); });
    this.root.querySelector("[data-ap-lock-left-submit]")?.addEventListener("click", function () { self._submitLock("left"); });
    this.root.querySelector("[data-ap-lock-right-submit]")?.addEventListener("click", function () { self._submitLock("right"); });
    this.root.querySelector("[data-ap-compare-submit]")?.addEventListener("click", function () { self._submitCompare(); });
    this.root.querySelector("[data-ap-fc-confirm]")?.addEventListener("click", function () { self._confirmFc(); });
    this.root.querySelector("[data-ap-explain-submit]")?.addEventListener("click", function () { self._submitExplain(); });
  };

  OneSidedLimitTracer.prototype._resetFlow = function () {
    this.step = 0;
    this.leftLocked = null;
    this.rightLocked = null;
    this.predictDone = false;
    this.fcConfirmed = false;
    this.tutor.reset();
    this._syncPanels();
  };

  OneSidedLimitTracer.prototype._animateTrace = function (side, endX) {
    var sc = this.scenario();
    var c = sc.targetX;
    var startX = side === "left" ? c - 0.4 : c + 0.4;
    startX = clampTracerX(startX, c, side, sc.domainMin);
    var self = this;
    if (prefersReducedMotion()) {
      if (side === "left") self._traceLeft(endX);
      else self._traceRight(endX);
      return;
    }
    var frames = 12;
    var step = 0;
    var timer = setInterval(function () {
      step += 1;
      var t = step / frames;
      var x = startX + (endX - startX) * t;
      x = clampTracerX(x, c, side, sc.domainMin);
      if (side === "left") self._traceLeft(x);
      else self._traceRight(x);
      if (step >= frames) clearInterval(timer);
    }, 40);
  };

  OneSidedLimitTracer.prototype._action = function (action) {
    var sc = this.scenario();
    if (action === "trace-left") {
      this._animateTrace("left", approachEndpoint(sc.targetX, "left", sc.domainMin));
    }
    if (action === "trace-right") {
      this._animateTrace("right", approachEndpoint(sc.targetX, "right", sc.domainMin));
    }
    if (action === "reset") {
      this._resetFlow();
      this._renderScenario();
    }
  };

  OneSidedLimitTracer.prototype._yAt = function (x, allowFc) {
    var key = this.scenarioIndex + "|" + x + "|" + (allowFc ? 1 : 0);
    if (this._yCache[key] !== undefined) return this._yCache[key];
    var y = evaluateScenarioY(this.scenario(), x, allowFc);
    this._yCache[key] = y;
    return y;
  };

  OneSidedLimitTracer.prototype._submitPredict = function () {
    var sc = this.scenario();
    var leftVal = this.root.querySelector("[data-ap-predict-left]")?.value;
    var rightVal = this.root.querySelector("[data-ap-predict-right]")?.value;
    var twoVal = this.root.querySelector("[data-ap-predict-two]")?.value;
    var fcVal = this.root.querySelector("[data-ap-predict-fc]")?.value;
    if (!leftVal || !rightVal || !twoVal || !fcVal) {
      var panel = this.root.querySelector("[data-ap-predict-result]");
      if (panel) { panel.hidden = false; panel.textContent = "Complete all four predictions first."; }
      return;
    }
    this.predictDone = true;
    this.step = 1;
    var panel = this.root.querySelector("[data-ap-predict-result]");
    if (panel) {
      panel.hidden = false;
      panel.textContent = "Prediction recorded. Explore the left branch (x < " + sc.targetX + ").";
    }
    this._syncPanels();
    emitLearningState(this.root, {
      eventType: "prediction_submitted",
      lessonId: this.spec.lessonId,
      labId: this.spec.id,
      caseId: sc.id,
      prediction: { left: leftVal, right: rightVal, two: twoVal, fcAffects: fcVal },
      labInstance: this,
    });
  };

  OneSidedLimitTracer.prototype._submitLock = function (side) {
    var sc = this.scenario();
    var input = this.root.querySelector(side === "left" ? "[data-ap-lock-left-input]" : "[data-ap-lock-right-input]");
    var feedback = this.root.querySelector(side === "left" ? "[data-ap-lock-left-feedback]" : "[data-ap-lock-right-feedback]");
    var expected = side === "left" ? sc.leftLimit : sc.rightLimit;
    var parsed = parseLimitValue(input ? input.value : "");
    var correct = limitsMatch(parsed, expected);
    if (feedback) feedback.hidden = false;
    if (correct) {
      if (side === "left") {
        this.leftLocked = expected;
        this.step = 3;
        if (feedback) feedback.textContent = "L⁻ locked.";
      } else {
        this.rightLocked = expected;
        this.step = 5;
        if (feedback) feedback.textContent = "L⁺ locked.";
      }
      this._syncPanels();
      emitLearningState(this.root, {
        eventType: side === "left" ? "left_observation_locked" : "right_observation_locked",
        lessonId: this.spec.lessonId,
        labId: this.spec.id,
        caseId: sc.id,
        answer: input ? input.value : "",
        correct: true,
        labInstance: this,
      });
      return;
    }
    var tag = side === "left" ? "checks-left-only" : "checks-right-only";
    if (parsed != null && expected != null && sc.functionValue != null && Math.abs(parsed - sc.functionValue) < 0.2) {
      tag = "filled-point-first";
    }
    if (feedback) feedback.textContent = this.tutor.misconception(tag);
    this.tutor.recordMisconception(tag);
    emitLearningState(this.root, {
      eventType: "answer_checked",
      lessonId: this.spec.lessonId,
      labId: this.spec.id,
      caseId: sc.id,
      answer: input ? input.value : "",
      correct: false,
      misconceptionTags: [tag],
    });
  };

  OneSidedLimitTracer.prototype._expectedComparison = function () {
    var sc = this.scenario();
    if (sc.infinite) return "unbounded";
    if (sc.leftLimit == null && sc.rightLimit == null) return "unbounded";
    if (sc.leftLimit == null || sc.rightLimit == null) return "one-side";
    if (sc.leftLimit === sc.rightLimit) return "same";
    return "different";
  };

  OneSidedLimitTracer.prototype._submitCompare = function () {
    var sc = this.scenario();
    var sel = this.root.querySelector("[data-ap-compare-select]");
    var val = sel ? sel.value : "";
    var feedback = this.root.querySelector("[data-ap-compare-feedback]");
    var expected = this._expectedComparison();
    var correct = val === expected;
    if (feedback) feedback.hidden = false;
    if (correct) {
      this.step = Math.max(this.step, 6);
      if (feedback) feedback.textContent = "Comparison locked. Two-sided: " + (sc.twoSidedLimit != null ? sc.twoSidedLimit : "DNE");
      var conclusion = this.root.querySelector("[data-ap-conclusion]");
      if (conclusion) conclusion.hidden = false;
      var body = this.root.querySelector("[data-ap-conclusion-body]");
      if (body) {
        body.textContent = "L⁻ = " + (sc.leftLimit != null ? sc.leftLimit : "n/a") +
          ", L⁺ = " + (sc.rightLimit != null ? sc.rightLimit : "n/a") +
          ". Two-sided limit: " + (sc.twoSidedLimit != null ? sc.twoSidedLimit : "DNE") + ".";
      }
      this._syncPanels();
      emitLearningState(this.root, {
        eventType: "comparison_submitted",
        lessonId: this.spec.lessonId,
        labId: this.spec.id,
        caseId: sc.id,
        answer: val,
        correct: true,
        labInstance: this,
      });
      return;
    }
    var tag = val === "same" && expected === "different" ? "averages-unequal-one-sided-limits" : "DNE-without-reason";
    if (feedback) feedback.textContent = this.tutor.misconception(tag);
    this.tutor.recordMisconception(tag);
  };

  OneSidedLimitTracer.prototype._confirmFc = function () {
    var sc = this.scenario();
    this.fcConfirmed = true;
    this.step = Math.max(this.step, 7);
    var read = this.root.querySelector("[data-ap-fc-read]");
    if (read) read.textContent = sc.functionValue != null ? sc.functionValue : "undefined";
    this._syncPanels();
    emitLearningState(this.root, {
      eventType: "function_value_submitted",
      lessonId: this.spec.lessonId,
      labId: this.spec.id,
      caseId: sc.id,
      answer: sc.functionValue,
      correct: true,
    });
  };

  OneSidedLimitTracer.prototype._submitExplain = function () {
    var sc = this.scenario();
    var text = (this.root.querySelector("[data-ap-explain-input]")?.value || "").toLowerCase();
    var feedback = this.root.querySelector("[data-ap-explain-feedback]");
    var hasLeft = text.indexOf("left") >= 0 || text.indexOf("l⁻") >= 0 || text.indexOf("l-") >= 0;
    var hasRight = text.indexOf("right") >= 0 || text.indexOf("l⁺") >= 0 || text.indexOf("l+") >= 0;
    var hasAgree = text.indexOf("same") >= 0 || text.indexOf("equal") >= 0 || text.indexOf("agree") >= 0 || text.indexOf("dne") >= 0 || text.indexOf("not exist") >= 0;
    var hasFc = text.indexOf("f(c)") >= 0 || text.indexOf("filled") >= 0 || text.indexOf("dot") >= 0 || text.indexOf("separate") >= 0;
    var correct = hasLeft && hasRight && hasAgree && hasFc;
    if (feedback) {
      feedback.hidden = false;
      feedback.innerHTML = correct
        ? "<strong>Strong explanation.</strong> You separated branch behavior from f(c)."
        : "<strong>Add more detail:</strong> mention left behavior, right behavior, whether they agree, and that f(c) is separate.";
    }
    if (!correct) this.tutor.recordMisconception("filled-point-determines-limit");
    this.studentExplain = text.slice(0, 500);
    emitLearningState(this.root, {
      eventType: "explanation_submitted",
      lessonId: this.spec.lessonId,
      labId: this.spec.id,
      caseId: sc.id,
      answer: this.studentExplain,
      correct: correct,
      labInstance: this,
    });
  };

  OneSidedLimitTracer.prototype._traceLeft = function (x) {
    var sc = this.scenario();
    x = clampTracerX(x, sc.targetX, "left", sc.domainMin);
    this.tutor.setContext({ caseId: sc.id, step: this.step, leftDone: this.leftLocked != null, rightDone: this.rightLocked != null });
    this.leftX = x;
    var y = this._yAt(x, false);
    var read = this.root.querySelector("[data-ap-trace-left-read]");
    var yEl = this.root.querySelector("[data-ap-trace-left-y]");
    var distEl = this.root.querySelector("[data-ap-trace-left-dist]");
    if (read) read.textContent = formatApproachX(x, sc.targetX, "left");
    if (yEl) yEl.textContent = formatTracerY(y, sc);
    if (distEl) distEl.textContent = Math.abs(x - sc.targetX).toFixed(3);
    if (this.predictDone && Math.abs(x - sc.targetX) <= 0.11) {
      this.step = Math.max(this.step, 2);
      this._syncPanels();
    }
    this._draw();
    emitLearningState(this.root, {
      eventType: "tracer_moved",
      lessonId: this.spec.lessonId,
      labId: this.spec.id,
      caseId: sc.id,
      graphState: { side: "left", x: x, y: y },
    });
  };

  OneSidedLimitTracer.prototype._traceRight = function (x) {
    var sc = this.scenario();
    x = clampTracerX(x, sc.targetX, "right", sc.domainMin);
    this.tutor.setContext({ caseId: sc.id, step: this.step, leftDone: this.leftLocked != null, rightDone: this.rightLocked != null });
    this.rightX = x;
    var y = this._yAt(x, false);
    var read = this.root.querySelector("[data-ap-trace-right-read]");
    var yEl = this.root.querySelector("[data-ap-trace-right-y]");
    var distEl = this.root.querySelector("[data-ap-trace-right-dist]");
    if (read) read.textContent = formatApproachX(x, sc.targetX, "right");
    if (yEl) yEl.textContent = formatTracerY(y, sc);
    if (distEl) distEl.textContent = Math.abs(x - sc.targetX).toFixed(3);
    if (this.leftLocked != null && Math.abs(x - sc.targetX) <= 0.11) {
      this.step = Math.max(this.step, 4);
      this._syncPanels();
    }
    this._draw();
    emitLearningState(this.root, {
      eventType: "tracer_moved",
      lessonId: this.spec.lessonId,
      labId: this.spec.id,
      caseId: sc.id,
      graphState: { side: "right", x: x, y: y },
    });
  };

  var TRACER_STEP_LABELS = [
    "Predict",
    "Explore left",
    "Lock L⁻",
    "Explore right",
    "Lock L⁺",
    "Compare",
    "Inspect f(c)",
    "Explain",
  ];

  OneSidedLimitTracer.prototype._syncPanels = function () {
    var predictPanel = this.root.querySelector("[data-ap-predict-panel]");
    var exploreStack = this.root.querySelector("[data-ap-explore-stack]");
    var leftPanel = this.root.querySelector("[data-ap-trace-left-panel]");
    var rightPanel = this.root.querySelector("[data-ap-trace-right-panel]");
    var lockLeft = this.root.querySelector("[data-ap-lock-left-panel]");
    var lockRight = this.root.querySelector("[data-ap-lock-right-panel]");
    var compare = this.root.querySelector("[data-ap-compare-panel]");
    var fc = this.root.querySelector("[data-ap-fc-panel]");
    var explain = this.root.querySelector("[data-ap-explain-panel]");
    var gatedExplore = !this.predictDone && this.step === 0;
    if (predictPanel) predictPanel.hidden = !gatedExplore;
    if (exploreStack) exploreStack.hidden = gatedExplore;
    if (leftPanel) leftPanel.hidden = this.step < 1 || this.step > 2;
    if (lockLeft) lockLeft.hidden = this.step !== 2;
    if (rightPanel) rightPanel.hidden = this.step < 3 || this.step > 4;
    if (lockRight) lockRight.hidden = this.step !== 4;
    if (compare) compare.hidden = this.step !== 5;
    if (fc) fc.hidden = this.step !== 6;
    if (explain) explain.hidden = this.step < 7;
    var sideTitle = this.root.querySelector("[data-ap-side-title]");
    if (sideTitle) {
      sideTitle.textContent = gatedExplore
        ? "Controls · Predict"
        : "Controls · " + (TRACER_STEP_LABELS[this.step] || "Explore");
    }
    var tutor = this.root.querySelector("[data-ap-tutor]");
    if (tutor) tutor.hidden = gatedExplore;
    this._updateDashboard();
    this._draw();
  };

  OneSidedLimitTracer.prototype._updateDashboard = function () {
    var sc = this.scenario();
    var dash = this.root.querySelector("[data-ap-dashboard]");
    if (!dash) return;
    dash.querySelector("[data-d-left]").textContent = this.leftLocked != null ? this.leftLocked : "—";
    dash.querySelector("[data-d-right]").textContent = this.rightLocked != null ? this.rightLocked : "—";
    var same = sc.leftLimit != null && sc.rightLimit != null && sc.leftLimit === sc.rightLimit;
    dash.querySelector("[data-d-same]").textContent = this.step >= 5
      ? (sc.leftLimit == null || sc.rightLimit == null ? "n/a" : (same ? "same" : "different"))
      : "—";
    dash.querySelector("[data-d-two]").textContent = this.step >= 5
      ? (sc.twoSidedLimit != null ? sc.twoSidedLimit : "DNE")
      : "—";
    dash.querySelector("[data-d-fc]").textContent = this.fcConfirmed
      ? (sc.functionValue != null ? sc.functionValue : "undefined")
      : "—";
    dash.querySelectorAll("[data-ap-step]").forEach(function (node) {
      var n = parseInt(node.getAttribute("data-ap-step"), 10);
      node.classList.toggle("is-done", n < this.step);
      node.classList.toggle("is-active", n === this.step);
    }.bind(this));
    var stepNow = dash.querySelector("[data-ap-step-now-text]");
    if (stepNow) stepNow.textContent = TRACER_STEP_LABELS[this.step] || "Explore";
    var benchStatus = this.root.querySelector("[data-ap-bench-status]");
    if (benchStatus) {
      benchStatus.textContent = "Step " + this.step + " · " + (TRACER_STEP_LABELS[this.step] || "Explore");
    }
  };

  OneSidedLimitTracer.prototype._buildPresets = function (side) {
    var sc = this.scenario();
    var presets = (sc.allowedTracerValues && sc.allowedTracerValues[side]) || [];
    presets = nearTracerPresets(presets, sc.targetX, side);
    var container = this.root.querySelector(side === "left" ? "[data-ap-left-presets]" : "[data-ap-right-presets]");
    if (!container) return;
    container.innerHTML = "";
    var self = this;
    presets.forEach(function (x) {
      var btn = el("button", "ap-lab-btn ap-lab-btn--preset", formatPresetLabel(x));
      btn.type = "button";
      btn.addEventListener("click", function () {
        if (side === "left") {
          var slider = self.root.querySelector("[data-ap-trace-left-slider]");
          if (slider) { slider.value = x; self._traceLeft(x); }
        } else {
          var sliderR = self.root.querySelector("[data-ap-trace-right-slider]");
          if (sliderR) { sliderR.value = x; self._traceRight(x); }
        }
      });
      container.appendChild(btn);
    });
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
    var c = sc.targetX;
    var domainMin = sc.domainMin != null ? sc.domainMin : c - 2;
    var leftSlider = this.root.querySelector("[data-ap-trace-left-slider]");
    var rightSlider = this.root.querySelector("[data-ap-trace-right-slider]");
    if (leftSlider) {
      leftSlider.min = domainMin;
      leftSlider.max = c - TRACER_EPS;
      leftSlider.step = 0.001;
      leftSlider.value = clampTracerX(c - 0.3, c, "left", sc.domainMin);
    }
    if (rightSlider) {
      rightSlider.min = c + TRACER_EPS;
      rightSlider.max = c + 2;
      rightSlider.step = 0.001;
      rightSlider.value = c + 0.3;
    }
    this._buildPresets("left");
    this._buildPresets("right");
    if (this.predictDone || this.step > 0) {
      if (leftSlider) this._traceLeft(parseFloat(leftSlider.value));
      if (rightSlider) this._traceRight(parseFloat(rightSlider.value));
    } else {
      this.leftX = null;
      this.rightX = null;
      this._draw();
    }
    var fcRead = this.root.querySelector("[data-ap-fc-read]");
    if (fcRead) {
      fcRead.textContent = this.step >= 6 && sc.functionValue != null ? sc.functionValue : "—";
    }
    if (this.step === 2 || this.leftLocked != null) this.step = Math.max(this.step, 2);
    this._syncPanels();
  };

  OneSidedLimitTracer.prototype._draw = function () {
    var sc = this.scenario();
    var svg = this.root.querySelector(".ap-lab-svg");
    if (!svg) return;
    var bounds = computePlotBounds(sc.branches, sc.openPoints, sc.closedPoints, sc.targetX);
    if (sc.domainMin != null) bounds.xMin = sc.domainMin - 0.2;
    var plot = new SVGPlot(svg, bounds);
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
    var showMarkers = this.predictDone || this.step > 0;
    var showFc = this.step >= 6;
    var closed0 = (sc.closedPoints || [])[0];
    var j;
    for (j = 0; j < 2; j++) {
      var op2 = (sc.openPoints || [])[j];
      var sel2 = "[data-ap-open-" + j + "]";
      setPoint(svg, sel2, op2 ? op2.x : NaN, op2 ? op2.y : NaN, plot, showMarkers && !!op2);
      var ptEl2 = svg.querySelector(sel2);
      if (ptEl2 && op2) {
        var brCol = sc.branches[j] ? sc.branches[j].color : COLORS.curve;
        ptEl2.setAttribute("stroke", brCol || COLORS.curve);
      }
    }
    setPoint(svg, "[data-ap-filled-0]", closed0 ? closed0.x : NaN, closed0 ? closed0.y : NaN, plot, showFc && !!closed0);
    var yL = this.leftX != null ? this._yAt(this.leftX, false) : NaN;
    var yR = this.rightX != null ? this._yAt(this.rightX, false) : NaN;
    setPoint(svg, "[data-ap-tracer-left]", this.leftX, yL, plot, isFinite(yL));
    setPoint(svg, "[data-ap-tracer-right]", this.rightX, yR, plot, isFinite(yR));
  };

  function initMathLab(root) {
    if (root._apMathLabInit) return;
    var spec = parseSpec(root);
    if (!spec) return;
    root._apMathLabInit = true;
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
    buildStructuredLessonState: buildStructuredLessonState,
    phaseFromLabStep: phaseFromLabStep,
    MISCONCEPTION_HINTS: MISCONCEPTION_HINTS,
    safeEval: safeEval,
    formatApproachX: formatApproachX,
    clampTracerX: clampTracerX,
    parseLimitValue: parseLimitValue,
    limitsMatch: limitsMatch,
    resolveScenarioIndex: resolveScenarioIndex,
    approachEndpoint: approachEndpoint,
    branchForApproach: branchForApproach,
    evaluateScenarioY: evaluateScenarioY,
    evaluateHoleWithValue: evaluateHoleWithValue,
    formatPresetLabel: formatPresetLabel,
    formatTracerY: formatTracerY,
    nearTracerPresets: nearTracerPresets,
    tickValues: tickValues,
    formatTick: formatTick,
    TRACER_EPS: TRACER_EPS,
    onStateChange: null,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { initAll(); });
  }
})(window);
