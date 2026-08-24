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

  var LAYOUT_KEY = config.layoutKey || "np-board-panel-layout-v6";
  var PREFS_KEY = config.prefsKey || "np-board-teach-prefs-v6";
  var CONTENT_KEY = config.contentKey || "np-board-scratch-v6";
  var emptyHint = panel.querySelector("[data-np-board-empty-hint]");
  var themeBtn = panel.querySelector("[data-np-board-theme]");
  var gridBtn = panel.querySelector("[data-np-board-grid]");
  var restoreBtn = document.getElementById("np-board-restore");
  var paperEl = panel.querySelector(".np-board-paper");
  var newlineBtn = panel.querySelector("[data-np-board-newline]");
  var copyBtn = panel.querySelector("[data-np-board-copy]");
  var redoBtn = panel.querySelector("[data-np-board-redo]");
  var peekBtn = panel.querySelector("[data-np-board-peek]");
  var minimizeBtn = panel.querySelector("[data-np-board-minimize]");
  var ctx = canvas ? canvas.getContext("2d") : null;
  var strokes = [];
  var redoStack = [];
  var drawing = null;
  var mode = "type";
  var tool = "pen";
  var color = "#f8fafc";
  var size = 4;
  var MathfieldElementCtor = null;
  var mathLiveReady = null;
  var lines = [];
  var activeField = null;
  var activeText = null;
  var dpr = Math.max(1, window.devicePixelRatio || 1);
  var lineSeq = 0;
  var prefs = { theme: "slate", dock: "right", fontStep: 0, input: "math", mode: "type", grid: false };
  var minimized = false;
  var peeking = false;
  var clearArmed = false;
  var clearArmTimer = null;
  var saveTimer = null;
  var restoring = false;
  var contentReady = false;

  function loadPrefs() {
    try {
      var raw = JSON.parse(localStorage.getItem(PREFS_KEY) || "null");
      if (raw && typeof raw === "object") {
        prefs.theme = raw.theme === "paper" ? "paper" : "slate";
        prefs.dock = ["left", "right", "wide", "present"].indexOf(raw.dock) >= 0 ? raw.dock : "right";
        prefs.fontStep = Math.max(-2, Math.min(4, Number(raw.fontStep) || 0));
        prefs.input = raw.input === "text" ? "text" : "math";
        prefs.mode = raw.mode === "draw" ? "draw" : "type";
        prefs.grid = !!raw.grid;
      }
    } catch (e) {}
  }

  function savePrefs() {
    try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch (e) {}
  }

  function chalkColor() {
    return prefs.theme === "paper" ? "#1c1917" : "#f8fafc";
  }

  function syncChalkSwatch() {
    var chalk = panel.querySelector('[data-np-board-color="#f8fafc"], [data-np-board-color="#1c1917"], [data-np-board-color="#111827"]');
    if (!chalk) return;
    var next = chalkColor();
    chalk.setAttribute("data-np-board-color", next);
    chalk.style.setProperty("--swatch", next);
  }

  function applyTheme() {
    panel.classList.toggle("theme-paper", prefs.theme === "paper");
    panel.classList.toggle("theme-slate", prefs.theme !== "paper");
    syncChalkSwatch();
    applyGrid();
    // Keep the default marker on chalk when switching boards.
    if (color === "#f8fafc" || color === "#ffffff" || color === "#1c1917" || color === "#111827") {
      setColor(chalkColor());
    }
  }

  function applyDock(dock, skipSave) {
    prefs.dock = dock || prefs.dock || "right";
    panel.classList.remove("dock-left", "dock-right", "dock-wide", "dock-present");
    panel.classList.add("dock-" + prefs.dock);
    panel.querySelectorAll("[data-np-board-dock]").forEach(function (btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-np-board-dock") === prefs.dock);
    });
    if (prefs.dock === "present") {
      panel.style.left = "";
      panel.style.top = "";
      panel.style.width = "";
      panel.style.height = "";
    } else if (prefs.dock === "wide") {
      panel.style.left = "";
      panel.style.top = Math.max(40, Math.round(window.innerHeight * 0.08)) + "px";
      panel.style.width = "";
      panel.style.height = "";
    } else if (prefs.dock === "left" || prefs.dock === "right") {
      var w = Math.min(520, Math.max(380, Math.round(window.innerWidth * 0.34)));
      var h = Math.min(Math.round(window.innerHeight * 0.78), window.innerHeight - 64);
      panel.style.top = "48px";
      panel.style.width = w + "px";
      panel.style.height = h + "px";
      panel.style.left = "";
      panel.style.right = "";
    }
    if (!skipSave) {
      savePrefs();
      saveLayout();
    }
    window.setTimeout(resizeCanvas, 40);
  }

  function applyInputKind(kind, skipSave, skipEnter) {
    if (kind) prefs.input = kind === "text" ? "text" : "math";
    panel.classList.toggle("is-fx-input", prefs.input !== "text");
    panel.classList.toggle("is-abc-input", prefs.input === "text");
    panel.querySelectorAll("[data-np-board-input]").forEach(function (btn) {
      var on = btn.getAttribute("data-np-board-input") === prefs.input;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (!skipSave) savePrefs();
    if (skipEnter || !isOpen() || mode !== "type") return;
    if (prefs.input === "math") enterMathInput();
    else enterTextInput();
  }

  function enterMathInput() {
    if (activeField) {
      try { activeField.focus(); } catch (e) {}
      return;
    }
    var textEl = activeText;
    if (!textEl && lines.length) {
      var segs = lineSegs(lines[lines.length - 1]);
      textEl = segs.filter(function (el) { return el.classList.contains("np-board-text"); }).pop() || segs[0];
    }
    if (textEl && textEl.classList.contains("np-board-text")) insertMathInText(textEl, "");
    else if (!lines.length) addLine(true);
  }

  function enterTextInput() {
    if (activeText) {
      focusText(activeText, "end");
      return;
    }
    if (activeField) {
      var after = neighborSeg(activeField, 1);
      if (after && after.classList.contains("np-board-text")) {
        focusText(after, "start");
        return;
      }
      var text = createTextSeg("");
      activeField.after(text);
      focusText(text, "start");
      return;
    }
    if (lines.length) focusLine(lines[lines.length - 1], "end");
  }

  function applyFontStep() {
    var base = 1.7;
    var sizeRem = Math.max(1.25, Math.min(2.45, base + prefs.fontStep * 0.18));
    panel.style.setProperty("--math-size", sizeRem + "rem");
    lines.forEach(function (line) {
      lineSegs(line).forEach(function (el) {
        if (el.tagName === "MATH-FIELD") {
          try { el.style.fontSize = sizeRem + "rem"; } catch (e) {}
        }
      });
    });
  }

  function syncContentState() {
    var hasWrite = lines.some(function (line) { return !lineIsEmpty(line); });
    var hasInk = strokes.length > 0;
    panel.classList.toggle("has-content", hasWrite || hasInk || lines.length > 1);
    if (emptyHint) emptyHint.hidden = hasWrite || hasInk || lines.length > 1;
    scheduleSave();
  }

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

  // In Abc/text, only convert tokens that are rarely English words.
  var TEXT_SHORTCUTS = {
    sqrt: "\\sqrt{#?}",
    cbrt: "\\sqrt[3]{#?}",
    frac: "\\frac{#?}{#?}",
    binom: "\\binom{#?}{#?}",
    pi: "\\pi",
    theta: "\\theta",
    alpha: "\\alpha",
    beta: "\\beta",
    gamma: "\\gamma",
    delta: "\\delta",
    sigma: "\\sigma",
    omega: "\\omega",
    lambda: "\\lambda",
    inf: "\\infty",
    infinity: "\\infty",
    leq: "\\leq",
    geq: "\\geq",
    neq: "\\neq",
    approx: "\\approx",
    times: "\\times",
    cdot: "\\cdot",
    pm: "\\pm",
    abs: "\\left|#?\\right|",
    lim: "\\lim",
    prod: "\\prod",
    iint: "\\iint"
  };

  var TEXT_SHORTCUT_WORDS = Object.keys(TEXT_SHORTCUTS).sort(function (a, b) {
    return b.length - a.length;
  });

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
    times: "\\times",
    neq: "\\neq",
    to: "\\to",
    infty: "\\infty"
  };

  function isOpen() {
    return panel.classList.contains("is-open");
  }

  function eventInsideBoard(el) {
    return !!(el && el.closest && el.closest("#np-board-panel"));
  }

  function isTypingTarget(el) {
    if (!el) return false;
    var tag = (el.tagName || "").toUpperCase();
    if (tag === "TEXTAREA" || tag === "SELECT" || tag === "MATH-FIELD" || tag === "OPTION") return true;
    if (tag === "INPUT") {
      var type = String(el.type || "text").toLowerCase();
      if (type === "button" || type === "submit" || type === "checkbox" || type === "radio" || type === "file" || type === "reset" || type === "image") {
        return false;
      }
      return true;
    }
    if (el.isContentEditable) return true;
    if (el.closest && el.closest("math-field, [contenteditable='true'], .np-board-text, .dcg-mq-textarea, .dcg-mq-math-mode, .dcg-container textarea")) {
      return true;
    }
    return false;
  }

  function isShiftLetter(event, code) {
    return !!(
      event &&
      event.shiftKey &&
      !event.metaKey &&
      !event.ctrlKey &&
      !event.altKey &&
      event.code === code
    );
  }

  function decorateToggles() {
    toggles.forEach(function (btn) {
      btn.setAttribute("title", "Teaching Board (Shift+B). Shift+P for pen.");
      btn.setAttribute("aria-keyshortcuts", "Shift+B");
      if (btn.classList.contains("np-cm-board-quick")) return;
      if (btn.querySelector(".np-tool-kbd")) return;
      var kbd = document.createElement("span");
      kbd.className = "np-tool-kbd";
      kbd.textContent = "⇧B";
      btn.appendChild(kbd);
    });
  }

  function applyGrid() {
    if (paperEl) paperEl.classList.toggle("is-grid", !!prefs.grid);
    if (gridBtn) gridBtn.classList.toggle("is-active", !!prefs.grid);
  }

  function setPeeking(on) {
    peeking = !!on;
    document.documentElement.classList.toggle("np-board-is-peeking", peeking && isOpen() && !minimized);
    if (peekBtn) peekBtn.classList.toggle("is-active", peeking);
  }

  function setMinimized(on) {
    minimized = !!on;
    panel.classList.toggle("is-minimized", minimized);
    if (restoreBtn) restoreBtn.hidden = !minimized;
    document.documentElement.classList.toggle("np-board-is-minimized", minimized);
    document.documentElement.classList.toggle("np-board-is-open", isOpen() && !minimized);
    if (minimized) setPeeking(false);
    if (!minimized && isOpen()) {
      window.setTimeout(resizeCanvas, 40);
    }
  }

  function nudgeAwayFromDesmos() {
    try {
      if (!(window.NpDesmos && typeof window.NpDesmos.isOpen === "function" && window.NpDesmos.isOpen())) return;
      if (prefs.dock === "right") applyDock("left");
    } catch (e) {}
  }

  function serializeContent() {
    return {
      lines: lines.map(function (line) {
        return lineSegs(line).map(function (el) {
          if (el.classList.contains("np-board-text")) return { k: "t", v: el.textContent || "" };
          try { return { k: "m", v: String(el.getValue("latex") || "") }; } catch (err) { return { k: "m", v: "" }; }
        });
      }),
      strokes: strokes
    };
  }

  function saveContent() {
    if (restoring) return;
    try {
      sessionStorage.setItem(CONTENT_KEY, JSON.stringify(serializeContent()));
    } catch (e) {}
  }

  function scheduleSave() {
    if (restoring) return;
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(saveContent, 180);
  }

  function wipeLines() {
    lines.forEach(function (line) {
      if (line.row && line.row.parentNode) line.row.parentNode.removeChild(line.row);
    });
    lines = [];
    activeField = null;
    activeText = null;
  }

  function hydrateLines(payload) {
    wipeLines();
    var rows = (payload && payload.lines) || [];
    if (!rows.length) return;
    rows.forEach(function (segs) {
      var line = addLine(false);
      if (!line) return;
      line.body.innerHTML = "";
      (segs || []).forEach(function (seg) {
        if (seg && seg.k === "m") line.body.appendChild(createMathField(seg.v || ""));
        else line.body.appendChild(createTextSeg((seg && seg.v) || ""));
      });
      if (!line.body.lastChild) line.body.appendChild(createTextSeg(""));
    });
  }

  var restorePromise = null;

  function restoreContent() {
    if (restorePromise) return restorePromise;
    var data = null;
    try { data = JSON.parse(sessionStorage.getItem(CONTENT_KEY) || "null"); } catch (e) { data = null; }
    if (!data || typeof data !== "object") {
      contentReady = true;
      restorePromise = Promise.resolve(false);
      return restorePromise;
    }
    restoring = true;
    var hasMath = Array.isArray(data.lines) && data.lines.some(function (row) {
      return (row || []).some(function (seg) { return seg && seg.k === "m"; });
    });
    function apply() {
      if (Array.isArray(data.lines) && data.lines.length) hydrateLines(data);
      strokes = Array.isArray(data.strokes) ? data.strokes : [];
      redoStack = [];
      restoring = false;
      contentReady = true;
      redraw();
      syncContentState();
      return true;
    }
    if (hasMath) {
      restorePromise = ensureMathLive().then(function (ok) {
        if (!ok) {
          restoring = false;
          contentReady = true;
          return false;
        }
        return apply();
      });
      return restorePromise;
    }
    apply();
    restorePromise = Promise.resolve(true);
    return restorePromise;
  }

  function copyBoard() {
    var parts = lines.map(function (line) {
      return lineSegs(line).map(function (el) {
        if (el.classList.contains("np-board-text")) return el.textContent || "";
        try { return String(el.getValue("latex") || ""); } catch (err) { return ""; }
      }).join("");
    }).filter(function (row) { return row.replace(/\s+/g, ""); });
    var text = parts.join("\n");
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        if (!copyBtn) return;
        var prev = copyBtn.textContent;
        copyBtn.textContent = "Copied";
        window.setTimeout(function () { copyBtn.textContent = prev; }, 1200);
      }).catch(function () {});
    }
  }

  function disarmClear() {
    clearArmed = false;
    window.clearTimeout(clearArmTimer);
    if (clearBtn) {
      clearBtn.textContent = "Clear";
      clearBtn.classList.remove("is-armed");
    }
  }

  function requestClear() {
    var hasWrite = lines.some(function (line) { return !lineIsEmpty(line); });
    if (!clearArmed && (hasWrite || strokes.length || lines.length > 1)) {
      clearArmed = true;
      if (clearBtn) {
        clearBtn.textContent = "Sure?";
        clearBtn.classList.add("is-armed");
      }
      clearArmTimer = window.setTimeout(disarmClear, 2600);
      return;
    }
    disarmClear();
    clearBoard();
  }

  function openInPenMode() {
    prefs.mode = "draw";
    if (!isOpen()) setOpen(true);
    else if (minimized) setMinimized(false);
    setTool("pen");
    setMode("draw");
  }

  function togglePenOrInk() {
    if (window.NpInk && typeof window.NpInk.available === "function" && window.NpInk.available()) {
      window.NpInk.toggle();
      return;
    }
    if (isOpen() && !minimized && mode === "draw") {
      setMode("type");
      return;
    }
    openInPenMode();
  }

  function setOpen(open) {
    if (open) setMinimized(false);
    panel.classList.toggle("is-open", !!open);
    panel.setAttribute("aria-hidden", open && !minimized ? "false" : "true");
    document.documentElement.classList.toggle("np-board-is-open", !!open && !minimized);
    toggles.forEach(function (btn) {
      btn.classList.toggle("is-active", !!open && !minimized);
      btn.setAttribute("aria-pressed", open && !minimized ? "true" : "false");
    });
    if (open) {
      initPanelControls();
      applyTheme();
      applyGrid();
      applyDock(prefs.dock, true);
      applyFontStep();
      applyInputKind(null, true, true);
      nudgeAwayFromDesmos();
      restoreContent().then(function () {
        resizeCanvas();
        setMode(prefs.mode || "type");
        if (mode === "type" && prefs.input === "math" && lines.length && !activeField) enterMathInput();
        syncContentState();
      });
      ensureMathLive();
    } else {
      drawing = null;
      activeField = null;
      activeText = null;
      setPeeking(false);
      setMinimized(false);
      if (restoreBtn) restoreBtn.hidden = true;
      saveContent();
    }
  }

  function defaultLayout() {
    var width = Math.min(520, Math.max(380, Math.round(window.innerWidth * 0.34)));
    var height = Math.min(Math.round(window.innerHeight * 0.78), window.innerHeight - 64);
    return {
      left: Math.max(16, window.innerWidth - width - 16),
      top: 48,
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
    if (prefs.dock === "present" || prefs.dock === "wide") {
      applyDock(prefs.dock, true);
      return;
    }
    var layout = null;
    try {
      layout = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "null");
    } catch (e) {
      layout = null;
    }
    applyLayout(layout || defaultLayout());
    applyDock(prefs.dock, true);
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
      ctx.globalAlpha = 1;
    } else if (stroke.tool === "highlighter") {
      ctx.globalCompositeOperation = "source-over";
      ctx.strokeStyle = stroke.color;
      ctx.lineWidth = Math.max(14, stroke.size * 3.4);
      ctx.globalAlpha = 0.38;
    } else {
      ctx.globalCompositeOperation = "source-over";
      ctx.strokeStyle = stroke.color;
      ctx.lineWidth = stroke.size;
      ctx.globalAlpha = 1;
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
    prefs.mode = mode;
    savePrefs();
    panel.classList.toggle("is-type-mode", mode === "type");
    panel.classList.toggle("is-draw-mode", mode === "draw");
    panel.querySelectorAll("[data-np-board-mode]").forEach(function (btn) {
      var on = btn.getAttribute("data-np-board-mode") === mode;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (mode === "type") {
      if (lines.length) focusLine(lines[lines.length - 1], "end");
      else addLine(true);
    } else {
      drawing = null;
    }
  }

  function setTool(next) {
    tool = next === "eraser" ? "eraser" : next === "highlighter" ? "highlighter" : "pen";
    panel.classList.toggle("is-eraser", tool === "eraser");
    panel.classList.toggle("is-highlighter", tool === "highlighter");
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
          loadingEl.textContent = "Math engine failed to load. Check network, reopen with Shift+B.";
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
    try { mf.mathModeSpace = "\\:"; } catch (e) {}
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
    try {
      var rem = 1.7 + prefs.fontStep * 0.18;
      mf.style.fontSize = Math.max(1.25, Math.min(2.45, rem)) + "rem";
    } catch (e) {}
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

  function lineSegs(line) {
    if (!line || !line.body) return [];
    return Array.prototype.slice.call(line.body.children);
  }

  function lineFromEl(el) {
    var row = el && el.closest ? el.closest(".np-board-line") : null;
    if (!row) return null;
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].row === row) return lines[i];
    }
    return null;
  }

  function fieldIsEmpty(field) {
    try {
      return !String(field.getValue("latex") || "").replace(/\s+/g, "");
    } catch (e) {
      return false;
    }
  }

  function lineIsEmpty(line) {
    return lineSegs(line).every(function (el) {
      if (el.classList.contains("np-board-text")) {
        return el.textContent === "";
      }
      if (el.tagName === "MATH-FIELD") return fieldIsEmpty(el);
      return true;
    });
  }

  function getCaretOffset(el) {
    var sel = window.getSelection();
    if (!sel || !sel.rangeCount) return (el.textContent || "").length;
    var range = sel.getRangeAt(0);
    if (!el.contains(range.startContainer) && el !== range.startContainer) {
      return (el.textContent || "").length;
    }
    var pre = range.cloneRange();
    pre.selectNodeContents(el);
    pre.setEnd(range.startContainer, range.startOffset);
    return pre.toString().length;
  }

  function setCaretOffset(el, offset) {
    el.focus();
    var text = el.firstChild;
    if (!text || text.nodeType !== 3) {
      if (!(el.textContent || "") && offset === 0) return;
      el.textContent = el.textContent || "";
      text = el.firstChild;
    }
    var len = (el.textContent || "").length;
    var pos = Math.max(0, Math.min(offset, len));
    var range = document.createRange();
    var sel = window.getSelection();
    if (text && text.nodeType === 3) {
      range.setStart(text, pos);
      range.collapse(true);
    } else {
      range.selectNodeContents(el);
      range.collapse(pos > 0 ? false : true);
    }
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function focusText(el, where) {
    if (!el) return;
    activeText = el;
    activeField = null;
    window.requestAnimationFrame(function () {
      try {
        el.focus();
        if (where === "start") setCaretOffset(el, 0);
        else if (where === "end") setCaretOffset(el, (el.textContent || "").length);
      } catch (e) {}
    });
  }

  function focusMath(field, where) {
    if (!field) return;
    activeField = field;
    activeText = null;
    window.requestAnimationFrame(function () {
      try {
        field.focus();
        if (where === "start" && field.executeCommand) field.executeCommand("moveToMathfieldStart");
        if (where === "end" && field.executeCommand) field.executeCommand("moveToMathfieldEnd");
      } catch (e) {}
    });
  }

  function focusLine(line, where) {
    if (!line) return;
    var segs = lineSegs(line);
    if (!segs.length) return;
    var el = where === "start" ? segs[0] : segs[segs.length - 1];
    if (el.classList.contains("np-board-text")) focusText(el, where || "end");
    else focusMath(el, where || "end");
  }

  function neighborSeg(el, dir) {
    var line = lineFromEl(el);
    if (!line) return null;
    var segs = lineSegs(line);
    var idx = segs.indexOf(el);
    if (idx < 0) return null;
    return segs[idx + dir] || null;
  }

  function moveToNeighbor(el, dir, edge) {
    var next = neighborSeg(el, dir);
    if (next) {
      if (next.classList.contains("np-board-text")) focusText(next, edge);
      else focusMath(next, edge);
      return true;
    }
    var line = lineFromEl(el);
    var lineIdx = lines.indexOf(line);
    if (dir < 0 && lineIdx > 0) {
      focusLine(lines[lineIdx - 1], "end");
      return true;
    }
    if (dir > 0 && lineIdx >= 0 && lineIdx < lines.length - 1) {
      focusLine(lines[lineIdx + 1], "start");
      return true;
    }
    return false;
  }

  function bindTypedShortcuts(field) {
    var buf = "";
    field.addEventListener("keydown", function (event) {
      if (event.isComposing || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "Backspace") {
        buf = buf.slice(0, -1);
        return;
      }
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        buf = "";
        var created = addLine(true);
        if (created) focusLine(created, "start");
        return;
      }
      if (event.key === "$") {
        event.preventDefault();
        buf = "";
        applyInputKind("text", false, true);
        var after = neighborSeg(field, 1);
        if (after && after.classList.contains("np-board-text")) focusText(after, "start");
        else {
          var text = createTextSeg("");
          field.after(text);
          focusText(text, "start");
        }
        return;
      }
      if (event.key === "Tab") {
        event.preventDefault();
        buf = "";
        applyInputKind("text", false, true);
        var nextText = neighborSeg(field, 1);
        if (nextText && nextText.classList.contains("np-board-text")) focusText(nextText, "start");
        else {
          var follow = createTextSeg("");
          field.after(follow);
          focusText(follow, "start");
        }
        return;
      }
      if (event.key.length === 1 && /[a-zA-Z]/.test(event.key)) {
        var trial = buf + event.key.toLowerCase();
        var hit = null;
        for (var i = 0; i < SHORTCUT_WORDS.length; i++) {
          if (trial === SHORTCUT_WORDS[i]) {
            hit = SHORTCUT_WORDS[i];
            break;
          }
        }
        if (hit) {
          event.preventDefault();
          deleteBackward(field, buf.length);
          insertLatex(field, TYPED_SHORTCUTS[hit]);
          buf = "";
          return;
        }
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
      buf = "";
    });
  }

  function bindMathNav(field) {
    field.addEventListener("move-out", function (event) {
      var dir = (event.detail && event.detail.direction) || "";
      if (dir === "backward" || dir === "left") moveToNeighbor(field, -1, "end");
      else if (dir === "forward" || dir === "right") moveToNeighbor(field, 1, "start");
      else if (dir === "upward" || dir === "up") {
        var line = lineFromEl(field);
        var idx = lines.indexOf(line);
        if (idx > 0) focusLine(lines[idx - 1], "end");
      } else if (dir === "downward" || dir === "down") {
        var lineDown = lineFromEl(field);
        var idxDown = lines.indexOf(lineDown);
        if (idxDown >= 0 && idxDown < lines.length - 1) focusLine(lines[idxDown + 1], "start");
      }
    });
    field.addEventListener("keydown", function (event) {
      if (event.key === "ArrowLeft" && !event.shiftKey && fieldIsEmpty(field)) {
        if (moveToNeighbor(field, -1, "end")) event.preventDefault();
      }
      if (event.key === "ArrowRight" && !event.shiftKey && fieldIsEmpty(field)) {
        if (moveToNeighbor(field, 1, "start")) event.preventDefault();
      }
      if (event.key === "Backspace" && !event.isComposing && fieldIsEmpty(field)) {
        event.preventDefault();
        var line = lineFromEl(field);
        var prev = neighborSeg(field, -1);
        if (field.parentNode) field.parentNode.removeChild(field);
        if (prev && prev.classList.contains("np-board-text")) focusText(prev, "end");
        else if (line && lineIsEmpty(line)) removeLine(line);
        syncContentState();
      }
    });
  }

  function createMathField(latex) {
    var field = new MathfieldElementCtor();
    field.className = "np-board-line-field";
    field.setAttribute("aria-label", "Board math");
    configureField(field);
    try { field.placeholder = ""; } catch (e) {}
    if (latex) {
      try { field.setValue(latex); } catch (e) {}
    }
    field.addEventListener("focus", function () {
      var line = lineFromEl(field);
      if (line) line.row.classList.add("is-active");
      activeField = field;
      activeText = null;
    });
    field.addEventListener("blur", function () {
      var line = lineFromEl(field);
      if (line) line.row.classList.remove("is-active");
    });
    field.addEventListener("input", syncContentState);
    bindTypedShortcuts(field);
    bindMathNav(field);
    return field;
  }

  function createTextSeg(text) {
    var el = document.createElement("span");
    el.className = "np-board-text";
    el.contentEditable = "true";
    el.spellcheck = false;
    el.setAttribute("role", "textbox");
    el.setAttribute("aria-label", "Board text");
    el.tabIndex = 0;
    el.textContent = text || "";

    el.addEventListener("focus", function () {
      var line = lineFromEl(el);
      if (line) line.row.classList.add("is-active");
      activeText = el;
      activeField = null;
    });
    el.addEventListener("blur", function () {
      var line = lineFromEl(el);
      if (line) line.row.classList.remove("is-active");
    });
    el.addEventListener("input", syncContentState);
    el.addEventListener("paste", function (event) {
      event.preventDefault();
      var pasted = (event.clipboardData || window.clipboardData).getData("text/plain") || "";
      document.execCommand("insertText", false, pasted.replace(/\r\n/g, "\n"));
    });
    var textBuf = "";
    el.addEventListener("keydown", function (event) {
      if (event.isComposing) return;
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        textBuf = "";
        splitLineFromText(el);
        return;
      }
      if (event.key === "Tab") {
        event.preventDefault();
        textBuf = "";
        insertMathInText(el, "");
        applyInputKind("math", false, true);
        return;
      }
      if (event.key === "$" && !event.metaKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault();
        textBuf = "";
        insertMathInText(el, "");
        applyInputKind("math", false, true);
        return;
      }
      if ((event.key === "^" || event.key === "_") && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        var offset = getCaretOffset(el);
        var before = (el.textContent || "").slice(0, offset);
        var atom = (before.match(/([A-Za-z0-9]+)$/) || [null, ""])[1];
        var latex = (atom || "") + (event.key === "^" ? "^{#?}" : "_{#?}");
        insertMathInText(el, latex, atom.length);
        applyInputKind("math", false, true);
        textBuf = "";
        return;
      }
      if (event.key.length === 1 && /[a-zA-Z]/.test(event.key) && !event.metaKey && !event.ctrlKey && !event.altKey) {
        var trial = textBuf + event.key.toLowerCase();
        var hit = null;
        for (var s = 0; s < TEXT_SHORTCUT_WORDS.length; s++) {
          if (trial === TEXT_SHORTCUT_WORDS[s]) {
            hit = TEXT_SHORTCUT_WORDS[s];
            break;
          }
        }
        if (hit) {
          event.preventDefault();
          insertMathInText(el, TEXT_SHORTCUTS[hit], textBuf.length);
          applyInputKind("math", false, true);
          textBuf = "";
          return;
        }
        var maybe = false;
        for (var t = 0; t < TEXT_SHORTCUT_WORDS.length; t++) {
          if (TEXT_SHORTCUT_WORDS[t].indexOf(trial) === 0) {
            maybe = true;
            break;
          }
        }
        textBuf = maybe ? trial : "";
      } else if (event.key === "Backspace") {
        textBuf = textBuf.slice(0, -1);
      } else if (event.key.length === 1) {
        textBuf = "";
      }
      if (event.key === "ArrowLeft" && !event.shiftKey && getCaretOffset(el) === 0) {
        if (moveToNeighbor(el, -1, "end")) event.preventDefault();
        return;
      }
      if (event.key === "ArrowRight" && !event.shiftKey && getCaretOffset(el) >= (el.textContent || "").length) {
        if (moveToNeighbor(el, 1, "start")) event.preventDefault();
        return;
      }
      if (event.key === "ArrowUp" && !event.shiftKey && getCaretOffset(el) === 0 && !neighborSeg(el, -1)) {
        var line = lineFromEl(el);
        var idx = lines.indexOf(line);
        if (idx > 0) {
          event.preventDefault();
          focusLine(lines[idx - 1], "end");
        }
        return;
      }
      if (event.key === "ArrowDown" && !event.shiftKey && getCaretOffset(el) >= (el.textContent || "").length && !neighborSeg(el, 1)) {
        var lineDown = lineFromEl(el);
        var idxDown = lines.indexOf(lineDown);
        if (idxDown >= 0 && idxDown < lines.length - 1) {
          event.preventDefault();
          focusLine(lines[idxDown + 1], "start");
        }
        return;
      }
      if (event.key === "Backspace" && getCaretOffset(el) === 0) {
        var prev = neighborSeg(el, -1);
        if (prev && prev.tagName === "MATH-FIELD") {
          event.preventDefault();
          if (fieldIsEmpty(prev)) {
            prev.parentNode.removeChild(prev);
            syncContentState();
          } else {
            focusMath(prev, "end");
          }
          return;
        }
        var line = lineFromEl(el);
        if (line && lineIsEmpty(line)) {
          event.preventDefault();
          removeLine(line);
        }
      }
    });
    return el;
  }

  function insertMathInText(textEl, latex, eatPrefix) {
    var offset = getCaretOffset(textEl);
    var full = textEl.textContent || "";
    eatPrefix = Math.max(0, eatPrefix || 0);
    var cut = Math.max(0, offset - eatPrefix);
    var before = full.slice(0, cut);
    var after = full.slice(offset);
    ensureMathLive().then(function (ok) {
      if (!ok || !textEl || !textEl.parentNode) return;
      textEl.textContent = before;
      var field = createMathField(latex || "");
      var afterEl = createTextSeg(after);
      textEl.after(field, afterEl);
      focusMath(field, "end");
      syncContentState();
    });
  }

  function insertMathAtActive(latex) {
    setMode("type");
    applyInputKind("math", false, true);
    if (activeField) {
      if (latex) insertLatex(activeField, latex);
      try { activeField.focus(); } catch (e) {}
      return;
    }
    var textEl = activeText;
    if (!textEl) {
      if (!lines.length) addLine(false);
      var line = lines[lines.length - 1];
      var segs = lineSegs(line);
      textEl = segs.filter(function (el) { return el.classList.contains("np-board-text"); }).pop() || segs[0];
    }
    if (textEl && textEl.classList.contains("np-board-text")) {
      insertMathInText(textEl, latex || "");
    }
  }

  function splitLineFromText(textEl) {
    var line = lineFromEl(textEl);
    if (!line) return;
    var offset = getCaretOffset(textEl);
    var full = textEl.textContent || "";
    var afterText = full.slice(offset);
    textEl.textContent = full.slice(0, offset);
    var segs = lineSegs(line);
    var idx = segs.indexOf(textEl);
    var moved = segs.slice(idx + 1);
    var created = addLine(false);
    if (!created) return;
    created.body.innerHTML = "";
    created.body.appendChild(createTextSeg(afterText));
    moved.forEach(function (el) { created.body.appendChild(el); });
    if (!created.body.lastChild || created.body.lastChild.tagName === "MATH-FIELD") {
      created.body.appendChild(createTextSeg(""));
    }
    if (prefs.input === "math") {
      var first = lineSegs(created)[0];
      if (first && first.classList.contains("np-board-text") && !(first.textContent || "")) {
        insertMathInText(first, "");
      } else {
        focusLine(created, "start");
      }
    } else {
      focusLine(created, "start");
    }
    syncContentState();
  }

  function resetLineBody(line) {
    line.body.innerHTML = "";
    var text = createTextSeg("");
    line.body.appendChild(text);
    return text;
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

  function removeLine(line) {
    if (lines.length <= 1) {
      resetLineBody(line);
      focusLine(line, "start");
      syncContentState();
      return;
    }
    var idx = lines.indexOf(line);
    if (idx < 0) return;
    lines.splice(idx, 1);
    if (line.row && line.row.parentNode) line.row.parentNode.removeChild(line.row);
    renumberLines();
    focusLine(lines[Math.min(idx, lines.length - 1)] || lines[0], "end");
    syncContentState();
  }

  function addLine(focus) {
    if (!linesEl) return null;
    var row = document.createElement("div");
    row.className = "np-board-line";
    row.dataset.lineId = String(++lineSeq);

    var num = document.createElement("span");
    num.className = "np-board-line-num";

    var body = document.createElement("div");
    body.className = "np-board-line-body";
    var text = createTextSeg("");

    var del = document.createElement("button");
    del.type = "button";
    del.className = "np-board-line-del";
    del.setAttribute("aria-label", "Delete line");
    del.textContent = "×";

    body.appendChild(text);
    row.appendChild(num);
    row.appendChild(body);
    row.appendChild(del);
    linesEl.appendChild(row);

    var line = { row: row, num: num, body: body };
    lines.push(line);
    renumberLines();

    del.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      removeLine(line);
    });

    if (focus) {
      if (prefs.input === "math") insertMathInText(text, "");
      else focusText(text, "end");
    }
    syncContentState();
    return line;
  }

  function clearBoard() {
    strokes = [];
    redoStack = [];
    drawing = null;
    redraw();
    wipeLines();
    if (mode === "type") addLine(true);
    syncContentState();
    saveContent();
  }

  function undoStroke() {
    if (!strokes.length) return;
    redoStack.push(strokes.pop());
    redraw();
    syncContentState();
  }

  function redoStroke() {
    if (!redoStack.length) return;
    strokes.push(redoStack.pop());
    redraw();
    syncContentState();
  }

  function stepSize(delta) {
    size = Math.max(2, Math.min(22, size + delta));
    if (sizeInput) sizeInput.value = String(size);
  }

  function applyDrawHotkey(event) {
    if (event.key === "u" || event.key === "U") {
      event.preventDefault();
      undoStroke();
      return true;
    }
    if (event.key === "e" || event.key === "E") {
      event.preventDefault();
      setTool(tool === "eraser" ? "pen" : "eraser");
      return true;
    }
    if (event.key === "h" || event.key === "H") {
      event.preventDefault();
      setTool(tool === "highlighter" ? "pen" : "highlighter");
      return true;
    }
    if (event.key === "v" || event.key === "V") {
      event.preventDefault();
      setTool("pen");
      return true;
    }
    if (event.key === "[" || event.key === "{") {
      event.preventDefault();
      stepSize(-1);
      return true;
    }
    if (event.key === "]" || event.key === "}") {
      event.preventDefault();
      stepSize(1);
      return true;
    }
    if (event.key >= "1" && event.key <= "5") {
      var swatches = panel.querySelectorAll("[data-np-board-color]");
      var swatch = swatches[Number(event.key) - 1];
      if (swatch) {
        event.preventDefault();
        setColor(swatch.getAttribute("data-np-board-color"));
      }
      return true;
    }
    return false;
  }

  function initDrawing() {
    if (!canvas || canvas.dataset.ready === "1") return;
    canvas.dataset.ready = "1";

    canvas.addEventListener("pointerdown", function (event) {
      if (mode !== "draw") return;
      event.preventDefault();
      redoStack = [];
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
      syncContentState();
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
    loadPrefs();
    applyTheme();
    restoreLayout();
    applyFontStep();
    initDrawing();

    var dragging = null;
    if (handle) {
      handle.addEventListener("pointerdown", function (event) {
        if (event.target.closest("button")) return;
        if (prefs.dock === "present" || prefs.dock === "wide") return;
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

    panel.querySelectorAll("[data-np-board-dock]").forEach(function (btn) {
      btn.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        applyDock(btn.getAttribute("data-np-board-dock"));
      });
    });

    panel.querySelectorAll("[data-np-board-font]").forEach(function (btn) {
      btn.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        prefs.fontStep = Math.max(-2, Math.min(4, prefs.fontStep + (Number(btn.getAttribute("data-np-board-font")) || 0)));
        savePrefs();
        applyFontStep();
      });
    });

    if (themeBtn) {
      themeBtn.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        prefs.theme = prefs.theme === "paper" ? "slate" : "paper";
        savePrefs();
        applyTheme();
      });
    }

    if (gridBtn) {
      gridBtn.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        prefs.grid = !prefs.grid;
        savePrefs();
        applyGrid();
      });
    }

    if (peekBtn) {
      peekBtn.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        setPeeking(!peeking);
      });
    }

    if (minimizeBtn) {
      minimizeBtn.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        setMinimized(true);
      });
    }

    if (newlineBtn) {
      newlineBtn.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        setMode("type");
        addLine(true);
      });
    }

    if (copyBtn) {
      copyBtn.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        copyBoard();
      });
    }

    panel.querySelectorAll("[data-np-board-input]").forEach(function (btn) {
      btn.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        setMode("type");
        applyInputKind(btn.getAttribute("data-np-board-input"));
      });
    });

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
      if (event.pointerType === "pen" && mode === "type") {
        setMode("draw");
        return;
      }
      if (mode !== "type") return;
      if (event.target.closest("math-field, .np-board-text, button")) return;
      if (!lines.length) {
        addLine(true);
      } else {
        focusLine(lines[lines.length - 1], "end");
      }
    });

    if (symbolsEl) {
      symbolsEl.addEventListener("click", function (event) {
        var btn = event.target.closest("[data-np-board-insert]");
        if (!btn) return;
        event.preventDefault();
        var token = btn.getAttribute("data-np-board-insert") || "";
        var latex = token === "math" ? "" : (INSERT_LATEX[token] || TYPED_SHORTCUTS[token] || "");
        insertMathAtActive(latex);
      });
    }
  }

  function toggle() {
    if (isOpen() && minimized) {
      setMinimized(false);
      return;
    }
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
  if (redoBtn) redoBtn.addEventListener("click", redoStroke);
  if (clearBtn) clearBtn.addEventListener("click", requestClear);
  if (restoreBtn) {
    restoreBtn.addEventListener("click", function (event) {
      event.preventDefault();
      if (!isOpen()) setOpen(true);
      else setMinimized(false);
    });
  }

  toggles.forEach(function (btn) {
    btn.addEventListener("click", function (event) {
      event.preventDefault();
      toggle();
    });
  });
  decorateToggles();

  document.addEventListener(
    "keydown",
    function (e) {
      var typing = isTypingTarget(e.target);
      if (config.enableShortcut !== false && !typing && isShiftLetter(e, "KeyB")) {
        e.preventDefault();
        e.stopPropagation();
        toggle();
        return;
      }
      if (config.enableShortcut !== false && !typing && isShiftLetter(e, "KeyP")) {
        e.preventDefault();
        e.stopPropagation();
        togglePenOrInk();
        return;
      }
      if (!isOpen() || minimized) return;
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        setMinimized(true);
        return;
      }
      if (e.key === "Alt") {
        setPeeking(true);
        return;
      }
      if ((e.metaKey || e.ctrlKey) && (e.key === "z" || e.key === "Z") && !typing && (mode === "draw" || eventInsideBoard(e.target))) {
        e.preventDefault();
        if (e.shiftKey) redoStroke();
        else undoStroke();
        return;
      }
      if (mode === "draw" && !typing && !e.metaKey && !e.ctrlKey && !e.altKey && !e.shiftKey) {
        applyDrawHotkey(e);
      }
    },
    true
  );

  document.addEventListener("keyup", function (e) {
    if (e.key === "Alt") setPeeking(false);
  });
  window.addEventListener("blur", function () { setPeeking(false); });

  loadPrefs();
  applyTheme();
  applyFontStep();
  applyInputKind(null, true, true);
  applyGrid();

  window.NpBoard = {
    toggle: toggle,
    open: function () { if (!isOpen()) setOpen(true); else if (minimized) setMinimized(false); },
    close: function () { setOpen(false); },
    minimize: function () { if (isOpen()) setMinimized(true); },
    openPen: openInPenMode,
    clear: clearBoard,
    setMode: setMode,
    isOpen: function () { return isOpen() && !minimized; },
    dock: applyDock,
    setTheme: function (theme) {
      prefs.theme = theme === "paper" ? "paper" : "slate";
      savePrefs();
      applyTheme();
    }
  };
})();
