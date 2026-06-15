(function () {
  "use strict";

  var config = window.__NP_DESMOS__ || {};
  var panel = document.getElementById("np-desmos-panel");
  if (!panel) return;

  var calcEl = document.getElementById("np-desmos-calculator");
  var statusEl = panel.querySelector("[data-np-desmos-status]");
  var toggles = Array.prototype.slice.call(
    document.querySelectorAll("[data-np-desmos-toggle], [data-cm-desmos-toggle]")
  );
  var closeBtn = panel.querySelector("[data-np-desmos-close]");
  var resetBtn = panel.querySelector("[data-np-desmos-reset]");
  var handle = document.getElementById("np-desmos-drag-handle");
  var desmosApiKey = config.apiKey || "";
  var desmosApiVersion = config.apiVersion || "v1.13";
  var calculator = null;
  var desmosLoadPromise = null;
  var LAYOUT_KEY = config.layoutKey || "np-desmos-panel-layout";

  function setStatus(message) {
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.textContent = message;
    }
  }

  function setOpen(open) {
    panel.classList.toggle("is-open", open);
    panel.setAttribute("aria-hidden", open ? "false" : "true");
    toggles.forEach(function (btn) {
      btn.classList.toggle("is-active", open);
      btn.setAttribute("aria-pressed", open ? "true" : "false");
    });
    if (open) {
      initPanelControls();
      window.setTimeout(resizeCalculator, 80);
    }
  }

  function isOpen() {
    return panel.classList.contains("is-open");
  }

  function isProjectorMode() {
    return !!document.querySelector(".np-cm-viewer.is-focus-mode");
  }

  function defaultLayout() {
    var projector = isProjectorMode();
    var width = projector
      ? Math.min(780, Math.max(520, Math.round(window.innerWidth * 0.42)))
      : Math.min(680, Math.max(420, window.innerWidth - 48));
    var height = projector
      ? Math.min(820, Math.max(520, window.innerHeight - 88))
      : Math.min(760, Math.max(420, window.innerHeight - 96));
    return {
      left: Math.max(16, window.innerWidth - width - 24),
      top: projector ? 58 : Math.max(16, Math.min(72, window.innerHeight - height - 16)),
      width: width,
      height: height
    };
  }

  function clampLayout(layout) {
    var minW = 360;
    var minH = 360;
    var width = Math.min(Math.max(layout.width || minW, minW), Math.max(minW, window.innerWidth - 24));
    var height = Math.min(Math.max(layout.height || minH, minH), Math.max(minH, window.innerHeight - 24));
    var left = Math.min(Math.max(layout.left || 12, 12), Math.max(12, window.innerWidth - width - 12));
    var top = Math.min(Math.max(layout.top || 12, 12), Math.max(12, window.innerHeight - height - 12));
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
    if (isProjectorMode()) {
      applyLayout(defaultLayout());
      return;
    }
    try {
      layout = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "null");
    } catch (e) {
      layout = null;
    }
    applyLayout(layout || defaultLayout());
  }

  function resizeCalculator() {
    if (calculator && calculator.resize) calculator.resize();
  }

  function initPanelControls() {
    if (!handle || panel.dataset.controlsReady === "1") return;
    panel.dataset.controlsReady = "1";
    restoreLayout();

    var dragging = null;
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
      handle.setPointerCapture(event.pointerId);
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
      resizeCalculator();
    }

    handle.addEventListener("pointerup", stopDrag);
    handle.addEventListener("pointercancel", stopDrag);

    if (window.ResizeObserver) {
      var ro = new ResizeObserver(function () {
        if (!isOpen()) return;
        saveLayout();
        resizeCalculator();
      });
      ro.observe(panel);
    }

    window.addEventListener("resize", function () {
      if (!isOpen()) return;
      applyLayout({
        left: panel.offsetLeft,
        top: panel.offsetTop,
        width: panel.offsetWidth,
        height: panel.offsetHeight
      });
      resizeCalculator();
    });
  }

  function ensureDesmosLoaded() {
    if (!desmosApiKey) return Promise.resolve(false);
    if (window.Desmos) return Promise.resolve(true);
    if (desmosLoadPromise) return desmosLoadPromise;

    desmosLoadPromise = new Promise(function (resolve) {
      var script = document.createElement("script");
      script.src =
        "https://www.desmos.com/api/" +
        desmosApiVersion +
        "/calculator.js?apiKey=" +
        encodeURIComponent(desmosApiKey);
      script.async = true;
      script.onload = function () { resolve(true); };
      script.onerror = function () { resolve(false); };
      document.head.appendChild(script);
      window.setTimeout(function () { resolve(!!window.Desmos); }, 5000);
    });

    return desmosLoadPromise;
  }

  async function initCalculator() {
    if (calculator) return true;
    setStatus("Loading Desmos...");
    if (!desmosApiKey) {
      setStatus("Desmos API key is not configured on the server.");
      return false;
    }
    var ok = await ensureDesmosLoaded();
    if (!ok || !window.Desmos) {
      setStatus("Desmos failed to load. Check your network connection.");
      return false;
    }
    if (statusEl) statusEl.hidden = true;
    calculator = Desmos.GraphingCalculator(calcEl, {
      keypad: true,
      expressions: true,
      settingsMenu: true,
      zoomButtons: true,
      expressionsCollapsed: false,
      border: false,
      lockViewport: false,
      // Table regression UI requires API v1.10+ (customRegressions) and v1.11+ (regressionTemplates menu).
      customRegressions: true,
      regressionTemplates: true,
      links: true
    });
    resizeCalculator();
    return true;
  }

  async function toggle() {
    if (isOpen()) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (!calculator) await initCalculator();
    else resizeCalculator();
  }

  function resetPanel() {
    try {
      localStorage.removeItem(LAYOUT_KEY);
    } catch (e) {}
    applyLayout(defaultLayout());
    window.setTimeout(resizeCalculator, 80);
  }

  toggles.forEach(function (btn) {
    btn.addEventListener("click", toggle);
  });
  if (closeBtn) closeBtn.addEventListener("click", function () { setOpen(false); });
  if (resetBtn) resetBtn.addEventListener("click", resetPanel);

  document.addEventListener("keydown", function (e) {
    var tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (config.enableShortcut === false) return;
    if (e.key === "d" || e.key === "D") {
      e.preventDefault();
      toggle();
    }
    if (e.key === "Escape" && isOpen()) {
      setOpen(false);
    }
  });

  ["fullscreenchange", "webkitfullscreenchange", "MSFullscreenChange"].forEach(function (eventName) {
    document.addEventListener(eventName, function () {
      if (!isOpen()) return;
      applyLayout(defaultLayout());
      window.setTimeout(resizeCalculator, 80);
    });
  });

  window.NpDesmos = { toggle: toggle, open: function () { if (!isOpen()) toggle(); }, close: function () { setOpen(false); }, reset: resetPanel };
  window.toggleCalc = toggle;
})();
