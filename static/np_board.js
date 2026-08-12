(function () {
  "use strict";

  var config = window.__NP_BOARD__ || {};
  var panel = document.getElementById("np-board-panel");
  if (!panel) return;

  var handle = document.getElementById("np-board-drag-handle");
  var surface = panel.querySelector("[data-np-board-surface]");
  var canvas = panel.querySelector("[data-np-board-canvas]");
  var linesEl = panel.querySelector("[data-np-board-lines]");
  var loadingEl = panel.querySelector("[data-np-board-loading]");
  var symbolsEl = panel.querySelector("[data-np-board-symbols]");
  var closeBtn = panel.querySelector("[data-np-board-close]");
  var undoBtn = panel.querySelector("[data-np-board-undo]");
  var clearBtn = panel.querySelector("[data-np-board-clear]");
  var sizeInput = panel.querySelector("[data-np-board-size]");
  var toggles = Array.prototype.slice.call(
    document.querySelectorAll("[data-np-board-toggle], [data-cm-board-toggle]")
  );

  var LAYOUT_KEY = config.layoutKey || "np-board-panel-layout-v3";
  var ctx = canvas ? canvas.getContext("2d") : null;
  var strokes = [];
  var drawing = null;
  var mode = "type";
  var tool = "pen";
  var color = "#111827";
  var size = 3;
  var MathfieldElementCtor = null;
  var mathLiveReady = null;
  var lines = [];
  var activeField = null;
  var dpr = Math.max(1, window.devicePixelRatio || 1);
  var lineSeq = 0;

  // Exact typed words → LaTeX inserted via MathLive command (Desmos-like).
  var TYPED_SHORTCUTS = {
    sqrt: "\\sqrt{#?}",
    cbrt: "\\sqrt[3]{#?}",
    int: "\\int",
    iint: "\\iint",
    sum: "\\sum",
    prod: "\\prod",
    lim: "\\lim",
    inf: "\\infty",
    infinity: "\\infty",
    pi: "\\pi",
    theta: "\\theta",
    alpha: "\\alpha",
    beta: "\\beta",
    gamma: "\\gamma",
    delta: "\\delta",
    sigma: "\\sigma",
    omega: "\\omega",
    lambda: "\\lambda",
    abs: "\\left|#?\\right|",
    pm: "\\pm",
    times: "\\times",
    cdot: "\\cdot",
    leq: "\\leq",
    geq: "\\geq",
    neq: "\\neq",
    approx: "\\approx",
    to: "\\to",
    sin: "\\sin",
    cos: "\\cos",
    tan: "\\tan",
    log: "\\log",
    ln: "\\ln",
    exp: "\\exp",
    frac: "\\frac{#?}{#?}",
    binom: "\\binom{#?}{#?}"
  };

  var SHORTCUT_WORDS = Object.keys(TYPED_SHORTCUTS).sort(function (a, b) {
    return b.length - a.length;
  });

  // Token → LaTeX for bottom symbol bar (tokens avoid Jinja `{#` comment traps).
  var INSERT_LATEX = {
    sqrt: "\\sqrt{#?}",
    int: "\\int",
    sum: "\\sum",
    pi: "\\pi",
    theta: "\\theta",
    frac: "\\frac{#?}{#?}",
    pow: "^{#?}",
    sub: "_{#?}",
    le: "\\le",
    ge: "\\ge",
    pm: "\\pm",
    infty: "\\infty"
  };

  function isOpen() {
    return panel.classList.contains("is-open");
  }

  function eventInsideBoard(el) {
    return !!(el && el.closest && el.closest("#np-board-panel"));
  }

  function setOpen(open) {
    panel.classList.toggle("is-open", !!open);
    panel.setAttribute("aria-hidden", open ? "false" : "true");
    document.documentElement.classList.toggle("np-board-is-open", !!open);
    toggles.forEach(function (btn) {
      btn.classList.toggle("is-active", !!open);
      btn.setAttribute("aria-pressed", open ? "true" : "false");
    });
    if (open) {
      initPanelControls();
      resizeCanvas();
      setMode("type");
      ensureMathLive().then(function (ok) {
        if (!ok) return;
        if (!lines.length) addLine(true);
        else focusLine(lines[lines.length - 1]);
      });
    } else {
      drawing = null;
      activeField = null;
    }
  }

  function defaultLayout() {
    var width = Math.min(700, Math.max(420, window.innerWidth - 48));
    var height = Math.min(620, Math.max(400, window.innerHeight - 100));
    return {
      left: 24,
      top: Math.max(48, Math.min(68, window.innerHeight - height - 20)),
      width: width,
      height: height
    };
  }

  function clampLayout(layout) {
    var minW = 360;
    var minH = 340;
    var width = Math.min(Math.max(layout.width || minW, minW), Math.max(minW, window.innerWidth - 16));
    var height = Math.min(Math.max(layout.height || minH, minH), Math.max(minH, window.innerHeight - 16));
    var left = Math.min(Math.max(layout.left || 12, 8), Math.max(8, window.innerWidth - width - 8));
    var top = Math.min(Math.max(layout.top || 12, 8), Math.max(8, window.innerHeight - height - 8));
    return { left: left, top: top, width: width, height: height };
  }

  function applyLayout(layout) {
    var next = clampLayout(layout || defaultLayout());
    panel.style.left = next.left + "px";
    panel.style.top = next.top + "px";
    panel.style.width = next.width + "px";
    panel.style.height = next.height + "px";
  }

  function saveLayout() {
    try {
      localStorage.setItem(
        LAYOUT_KEY,
        JSON.stringify({
          left: panel.offsetLeft,
          top: panel.offsetTop,
          width: panel.offsetWidth,
          height: panel.offsetHeight
        })
      );
    } catch (e) {}
  }

  function restoreLayout() {
    var layout = null;
    try {
      layout = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "null");
    } catch (e) {
      layout = null;
    }
    applyLayout(layout || defaultLayout());
  }

  function resizeCanvas() {
    if (!canvas || !ctx || !surface) return;
    var rect = surface.getBoundingClientRect();
    var w = Math.max(1, Math.round(rect.width));
    var h = Math.max(1, Math.round(rect.height));
    dpr = Math.max(1, window.devicePixelRatio || 1);
    var needW = Math.round(w * dpr);
    var needH = Math.round(h * dpr);
    if (canvas.width === needW && canvas.height === needH) return;
    canvas.width = needW;
    canvas.height = needH;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    redraw();
  }

  function pointerPos(event) {
    var rect = canvas.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function drawStroke(stroke) {
    if (!ctx || !stroke || !stroke.points || !stroke.points.length) return;
    ctx.save();
    if (stroke.tool === "eraser") {
      ctx.globalCompositeOperation = "destination-out";
      ctx.strokeStyle = "rgba(0,0,0,1)";
      ctx.lineWidth = Math.max(12, stroke.size * 4);
    } else {
      ctx.globalCompositeOperation = "source-over";
      ctx.strokeStyle = stroke.color;
      ctx.lineWidth = stroke.size;
    }
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(stroke.points[0].x, stroke.points[0].y);
    for (var i = 1; i < stroke.points.length; i++) {
      ctx.lineTo(stroke.points[i].x, stroke.points[i].y);
    }
    ctx.stroke();
    ctx.restore();
  }

  function redraw() {
    if (!ctx || !canvas) return;
    ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    strokes.forEach(drawStroke);
  }

  function setMode(next) {
    mode = next === "draw" ? "draw" : "type";
    panel.classList.toggle("is-type-mode", mode === "type");
    panel.classList.toggle("is-draw-mode", mode === "draw");
    panel.querySelectorAll("[data-np-board-mode]").forEach(function (btn) {
      var on = btn.getAttribute("data-np-board-mode") === mode;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (mode === "type") {
      if (lines.length) focusLine(lines[lines.length - 1]);
      else ensureMathLive().then(function (ok) { if (ok) addLine(true); });
    } else {
      drawing = null;
    }
  }

  function setTool(next) {
    tool = next === "eraser" ? "eraser" : "pen";
    panel.classList.toggle("is-eraser", tool === "eraser");
    panel.querySelectorAll("[data-np-board-tool]").forEach(function (btn) {
      var on = btn.getAttribute("data-np-board-tool") === tool;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function setColor(next) {
    color = next || color;
    panel.querySelectorAll("[data-np-board-color]").forEach(function (btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-np-board-color") === color);
    });
    if (tool === "eraser") setTool("pen");
  }

  function ensureMathLiveCss() {
    if (document.getElementById("np-board-mathlive-css")) return;
    var link = document.createElement("link");
    link.id = "np-board-mathlive-css";
    link.rel = "stylesheet";
    link.href = config.mathliveCss || "https://cdn.jsdelivr.net/npm/mathlive@0.105.3/mathlive-static.css";
    document.head.appendChild(link);
  }

  function ensureMathLive() {
    if (MathfieldElementCtor) return Promise.resolve(true);
    if (mathLiveReady) return mathLiveReady;
    ensureMathLiveCss();
    var moduleUrl = config.mathliveModule || "https://cdn.jsdelivr.net/npm/mathlive@0.105.3/+esm";
    if (loadingEl) {
      loadingEl.hidden = false;
      loadingEl.textContent = "Loading math…";
    }
    mathLiveReady = import(moduleUrl)
      .then(function (mod) {
        MathfieldElementCtor = mod.MathfieldElement || window.MathfieldElement;
        if (!MathfieldElementCtor) throw new Error("MathfieldElement missing");
        if (!customElements.get("math-field")) {
          customElements.define("math-field", MathfieldElementCtor);
        }
        try {
          var defaults = MathfieldElementCtor.defaultInlineShortcuts || {};
          var merged = {};
          Object.keys(defaults).forEach(function (k) { merged[k] = defaults[k]; });
          Object.keys(TYPED_SHORTCUTS).forEach(function (k) { merged[k] = TYPED_SHORTCUTS[k]; });
          MathfieldElementCtor.inlineShortcuts = merged;
        } catch (e) {}
        if (loadingEl) loadingEl.hidden = true;
        return true;
      })
      .catch(function (err) {
        console.error("[NpBoard] MathLive failed", err);
        mathLiveReady = null;
        if (loadingEl) {
          loadingEl.hidden = false;
          loadingEl.textContent = "Math engine failed to load. Check network, reopen with B.";
        }
        return false;
      });
    return mathLiveReady;
  }

  function configureField(mf) {
    try { mf.mathVirtualKeyboardPolicy = "manual"; } catch (e) {}
    try { mf.smartMode = false; } catch (e) {}
    try { mf.smartFence = true; } catch (e) {}
    try { mf.smartSuperscript = true; } catch (e) {}
    try { mf.inlineShortcutTimeout = 0; } catch (e) {}
    try {
      var defaults = (MathfieldElementCtor && MathfieldElementCtor.defaultInlineShortcuts) || {};
      var merged = {};
      Object.keys(defaults).forEach(function (k) { merged[k] = defaults[k]; });
      Object.keys(TYPED_SHORTCUTS).forEach(function (k) { merged[k] = TYPED_SHORTCUTS[k]; });
      mf.inlineShortcuts = merged;
    } catch (e) {
      try { mf.inlineShortcuts = TYPED_SHORTCUTS; } catch (e2) {}
    }
    try { mf.menuItems = []; } catch (e) {}
    try { mf.style.fontSize = "1.45rem"; } catch (e) {}
  }

  function insertLatex(field, latex) {
    if (!field || !latex) return;
    try {
      if (field.executeCommand) {
        field.executeCommand(["insert", latex]);
        return;
      }
    } catch (e) {}
    try {
      var cur = String(field.getValue("latex") || "");
      field.setValue(cur + latex);
    } catch (e2) {}
  }

  function deleteBackward(field, n) {
    for (var i = 0; i < n; i++) {
      try {
        if (field.executeCommand) field.executeCommand("deleteBackward");
      } catch (e) {}
    }
  }

  /** Convert typed word buffer into a math symbol as soon as it matches. */
  function bindTypedShortcuts(field) {
    var buf = "";

    field.addEventListener("keydown", function (event) {
      event.stopPropagation();
      if (event.isComposing || event.metaKey || event.ctrlKey || event.altKey) return;

      if (event.key === "Backspace") {
        buf = buf.slice(0, -1);
        return;
      }

      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        buf = "";
        var created = addLine(true);
        if (created) focusLine(created);
        return;
      }

      if (event.key.length === 1 && /[a-zA-Z]/.test(event.key)) {
        var trial = buf + event.key.toLowerCase();
        var hit = null;
        for (var i = 0; i < SHORTCUT_WORDS.length; i++) {
          var word = SHORTCUT_WORDS[i];
          if (trial === word) {
            hit = word;
            break;
          }
        }
        if (hit) {
          event.preventDefault();
          // Remove already-typed prefix letters (all but the current key, which we blocked).
          deleteBackward(field, buf.length);
          insertLatex(field, TYPED_SHORTCUTS[hit]);
          buf = "";
          return;
        }
        // Keep buffer only for possible prefixes of a shortcut.
        var maybe = false;
        for (var j = 0; j < SHORTCUT_WORDS.length; j++) {
          if (SHORTCUT_WORDS[j].indexOf(trial) === 0) {
            maybe = true;
            break;
          }
        }
        buf = maybe ? trial : "";
        return;
      }

      // Non-letter ends the word buffer.
      buf = "";
    });
  }

  function renumberLines() {
    lines.forEach(function (line, idx) {
      if (line.num) {
        line.num.textContent = "";
        line.num.setAttribute("aria-hidden", "true");
        line.num.title = "Line " + (idx + 1);
      }
      line.row.dataset.index = String(idx);
    });
  }

  function focusLine(line) {
    if (!line || !line.field) return;
    activeField = line.field;
    window.requestAnimationFrame(function () {
      try { line.field.focus(); } catch (e) {}
    });
  }

  function fieldIsEmpty(field) {
    try {
      return !String(field.getValue("latex") || "").replace(/\s+/g, "");
    } catch (e) {
      return false;
    }
  }

  function removeLine(line) {
    if (lines.length <= 1) {
      try { line.field.setValue(""); } catch (e) {}
      focusLine(line);
      return;
    }
    var idx = lines.indexOf(line);
    if (idx < 0) return;
    lines.splice(idx, 1);
    if (line.row && line.row.parentNode) line.row.parentNode.removeChild(line.row);
    renumberLines();
    focusLine(lines[Math.min(idx, lines.length - 1)] || lines[0]);
  }

  function addLine(focus) {
    if (!MathfieldElementCtor || !linesEl) return null;
    var row = document.createElement("div");
    row.className = "np-board-line";
    row.dataset.lineId = String(++lineSeq);

    var num = document.createElement("span");
    num.className = "np-board-line-num";

    var field = new MathfieldElementCtor();
    field.className = "np-board-line-field";
    field.setAttribute("aria-label", "Board math line");
    configureField(field);
    try { field.placeholder = ""; } catch (e) {}

    var del = document.createElement("button");
    del.type = "button";
    del.className = "np-board-line-del";
    del.setAttribute("aria-label", "Delete line");
    del.textContent = "×";

    row.appendChild(num);
    row.appendChild(field);
    row.appendChild(del);
    linesEl.appendChild(row);

    var line = { row: row, num: num, field: field };
    lines.push(line);
    renumberLines();

    del.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      removeLine(line);
    });

    field.addEventListener("focus", function () {
      row.classList.add("is-active");
      activeField = field;
    });
    field.addEventListener("blur", function () {
      row.classList.remove("is-active");
    });

    bindTypedShortcuts(field);

    field.addEventListener("keydown", function (event) {
      if (event.key === "Backspace" && !event.isComposing && fieldIsEmpty(field)) {
        event.preventDefault();
        removeLine(line);
        return;
      }
      if (event.key === "ArrowUp" && !event.shiftKey) {
        var idxUp = lines.indexOf(line);
        if (idxUp > 0) {
          event.preventDefault();
          focusLine(lines[idxUp - 1]);
        }
      }
      if (event.key === "ArrowDown" && !event.shiftKey) {
        var idxDown = lines.indexOf(line);
        if (idxDown >= 0 && idxDown < lines.length - 1) {
          event.preventDefault();
          focusLine(lines[idxDown + 1]);
        }
      }
    });

    if (focus) focusLine(line);
    return line;
  }

  function clearBoard() {
    strokes = [];
    drawing = null;
    redraw();
    lines.forEach(function (line) {
      if (line.row && line.row.parentNode) line.row.parentNode.removeChild(line.row);
    });
    lines = [];
    activeField = null;
    if (mode === "type" && MathfieldElementCtor) addLine(true);
  }

  function undoStroke() {
    if (!strokes.length) return;
    strokes.pop();
    redraw();
  }

  function initDrawing() {
    if (!canvas || canvas.dataset.ready === "1") return;
    canvas.dataset.ready = "1";

    canvas.addEventListener("pointerdown", function (event) {
      if (mode !== "draw") return;
      event.preventDefault();
      var p = pointerPos(event);
      drawing = {
        pointerId: event.pointerId,
        tool: tool,
        color: color,
        size: size,
        points: [p]
      };
      try { canvas.setPointerCapture(event.pointerId); } catch (e) {}
      drawStroke(drawing);
    });

    canvas.addEventListener("pointermove", function (event) {
      if (!drawing || drawing.pointerId !== event.pointerId) return;
      drawing.points.push(pointerPos(event));
      redraw();
      drawStroke(drawing);
    });

    function endStroke(event) {
      if (!drawing || drawing.pointerId !== event.pointerId) return;
      if (drawing.points.length > 1) strokes.push(drawing);
      drawing = null;
      redraw();
    }

    canvas.addEventListener("pointerup", endStroke);
    canvas.addEventListener("pointercancel", endStroke);
  }

  function initPanelControls() {
    if (panel.dataset.controlsReady === "1") {
      resizeCanvas();
      return;
    }
    panel.dataset.controlsReady = "1";
    restoreLayout();
    initDrawing();

    var dragging = null;
    if (handle) {
      handle.addEventListener("pointerdown", function (event) {
        if (event.target.closest("button")) return;
        event.preventDefault();
        var rect = panel.getBoundingClientRect();
        dragging = {
          pointerId: event.pointerId,
          dx: event.clientX - rect.left,
          dy: event.clientY - rect.top
        };
        panel.classList.add("is-dragging");
        try { handle.setPointerCapture(event.pointerId); } catch (e) {}
      });
      handle.addEventListener("pointermove", function (event) {
        if (!dragging || dragging.pointerId !== event.pointerId) return;
        var layout = clampLayout({
          left: event.clientX - dragging.dx,
          top: event.clientY - dragging.dy,
          width: panel.offsetWidth,
          height: panel.offsetHeight
        });
        panel.style.left = layout.left + "px";
        panel.style.top = layout.top + "px";
      });
      function stopDrag(event) {
        if (!dragging || dragging.pointerId !== event.pointerId) return;
        dragging = null;
        panel.classList.remove("is-dragging");
        saveLayout();
        resizeCanvas();
      }
      handle.addEventListener("pointerup", stopDrag);
      handle.addEventListener("pointercancel", stopDrag);
    }

    if (window.ResizeObserver) {
      var ro = new ResizeObserver(function () {
        if (!isOpen()) return;
        saveLayout();
        resizeCanvas();
      });
      ro.observe(panel);
      if (surface) ro.observe(surface);
    }

    window.addEventListener("resize", function () {
      if (!isOpen()) return;
      applyLayout({
        left: panel.offsetLeft,
        top: panel.offsetTop,
        width: panel.offsetWidth,
        height: panel.offsetHeight
      });
      resizeCanvas();
    });

    surface.addEventListener("pointerdown", function (event) {
      if (mode !== "type") return;
      if (event.target.closest("math-field") || event.target.closest("button")) return;
      if (!lines.length) {
        ensureMathLive().then(function (ok) { if (ok) addLine(true); });
      } else {
        focusLine(lines[lines.length - 1]);
      }
    });

    if (symbolsEl) {
      symbolsEl.addEventListener("click", function (event) {
        var btn = event.target.closest("[data-np-board-insert]");
        if (!btn) return;
        event.preventDefault();
        setMode("type");
        var token = btn.getAttribute("data-np-board-insert") || "";
        var latex = INSERT_LATEX[token] || TYPED_SHORTCUTS[token] || "";
        if (!latex) return;
        ensureMathLive().then(function (ok) {
          if (!ok) return;
          if (!activeField || !lines.length) addLine(true);
          var field = activeField || (lines[lines.length - 1] && lines[lines.length - 1].field);
          if (!field) return;
          focusLine(lines.find(function (l) { return l.field === field; }) || lines[lines.length - 1]);
          window.setTimeout(function () {
            insertLatex(field, latex);
            try { field.focus(); } catch (e) {}
          }, 30);
        });
      });
    }
  }

  function toggle() {
    setOpen(!isOpen());
  }

  panel.querySelectorAll("[data-np-board-mode]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setMode(btn.getAttribute("data-np-board-mode"));
    });
  });
  panel.querySelectorAll("[data-np-board-tool]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setTool(btn.getAttribute("data-np-board-tool"));
      setMode("draw");
    });
  });
  panel.querySelectorAll("[data-np-board-color]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setColor(btn.getAttribute("data-np-board-color"));
      setMode("draw");
    });
  });
  if (sizeInput) {
    sizeInput.addEventListener("input", function () {
      size = Number(sizeInput.value) || 3;
    });
  }
  if (closeBtn) closeBtn.addEventListener("click", function () { setOpen(false); });
  if (undoBtn) undoBtn.addEventListener("click", undoStroke);
  if (clearBtn) clearBtn.addEventListener("click", clearBoard);

  toggles.forEach(function (btn) {
    btn.addEventListener("click", function (event) {
      event.preventDefault();
      toggle();
    });
  });

  document.addEventListener(
    "keydown",
    function (e) {
      if (eventInsideBoard(e.target) || (e.target && (e.target.tagName || "").toUpperCase() === "MATH-FIELD")) {
        if (isOpen() && (e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === "ArrowUp" || e.key === "ArrowDown")) {
          e.stopPropagation();
        }
        if (isOpen() && (e.key === "d" || e.key === "D" || e.key === "b" || e.key === "B" || e.key === "p" || e.key === "P")) {
          e.stopPropagation();
        }
        return;
      }
      if (config.enableShortcut === false) return;
      if ((e.key === "b" || e.key === "B") && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        e.stopPropagation();
        toggle();
        return;
      }
      if (!isOpen()) return;
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        setOpen(false);
        return;
      }
      if ((e.key === "u" || e.key === "U") && mode === "draw") {
        e.preventDefault();
        undoStroke();
      }
    },
    true
  );

  window.NpBoard = {
    toggle: toggle,
    open: function () { if (!isOpen()) setOpen(true); },
    close: function () { setOpen(false); },
    clear: clearBoard,
    setMode: setMode,
    isOpen: isOpen
  };
})();
