(function () {
  "use strict";

  var root = document.querySelector("[data-cm-viewer]");
  if (!root) return;

  var slides = [];
  var slidesEl = document.getElementById("cm-slides-json");
  if (slidesEl) {
    try {
      slides = JSON.parse(slidesEl.textContent || "[]");
    } catch (e) {
      slides = [];
    }
  }
  if (!slides.length) return;

  var lessonSlug = root.getAttribute("data-lesson-slug") || "lesson";
  var storageKey = "np-cm-progress-" + lessonSlug;
  var studyKey = "np-cm-study-" + lessonSlug;
  var syncEnabled = root.getAttribute("data-cm-sync") === "1";
  var progressApi = root.getAttribute("data-cm-progress-api") || "";
  var classroomActiveApi = root.getAttribute("data-cm-classroom-active-api") || "";
  var classroomResponseApi = root.getAttribute("data-cm-classroom-response-api") || "";
  var classroomSummaryApi = root.getAttribute("data-cm-classroom-summary-api") || "";
  var classroomStartApi = root.getAttribute("data-cm-classroom-start-api") || "";
  var classroomSlideApi = root.getAttribute("data-cm-classroom-slide-api") || "";
  var classroomInkApi = root.getAttribute("data-cm-classroom-ink-api") || "";
  var syncTimer = null;
  var globalVisitKey = "np-cm-last-visit";
  var resumeDismissKey = "np-cm-resume-dismiss-" + lessonSlug;

  var idx = 0;
  var activeFilter = "all";
  var bodyEl = root.querySelector("[data-cm-body]");
  var slideEl = root.querySelector("[data-cm-slide]");
  var titleEl = root.querySelector("[data-cm-title]");
  var sectionEl = root.querySelector("[data-cm-slide-section]");
  var badgeEl = root.querySelector("[data-cm-badge]");
  var counterEl = root.querySelector("[data-cm-counter]");
  var railCounterEl = root.querySelector("[data-cm-rail-counter]");
  var kindPill = root.querySelector("[data-cm-kind-pill]");
  var progressEl = root.querySelector("[data-cm-progress]");
  var stageEl = root.querySelector(".np-cm-slide-stage");
  var inkRailHost = root.querySelector("[data-cm-ink-rail]");
  var inkCompactSlot = root.querySelector("[data-cm-ink-compact-slot]");
  var inkChromeHost = root.querySelector(".np-cm-deck-chrome");
  var studyToggle = root.querySelector("[data-cm-study-toggle]");
  var studyStatEl = root.querySelector("[data-cm-study-stat]");
  var masteryPctEl = root.querySelector("[data-cm-mastery-pct]");
  var masteryRingEl = root.querySelector("[data-cm-mastery-ring]");
  var pathCurrentEl = root.querySelector("[data-cm-path-current]");
  var sectionLabelEl = root.querySelector("[data-cm-section-label]");
  var coachTipEl = root.querySelector("[data-cm-coach-tip]");
  var hintBtn = root.querySelector("[data-cm-show-hint]");
  var hintPanel = root.querySelector("[data-cm-hint-panel]");
  var nextChallengeBtn = root.querySelector("[data-cm-next-challenge]");
  var resumeEl = root.querySelector("[data-cm-resume]");
  var resumeTextEl = root.querySelector("[data-cm-resume-text]");
  var resumeGoBtn = root.querySelector("[data-cm-resume-go]");
  var resumeDismissBtn = root.querySelector("[data-cm-resume-dismiss]");
  var focusToggle = root.querySelector("[data-cm-focus-toggle]");
  var focusInlineExit = root.querySelector(".np-cm-focus-inline-exit");
  var focusExitBtns = Array.prototype.slice.call(root.querySelectorAll("[data-cm-focus-exit]"));
  var focusKey = "np-cm-focus-" + lessonSlug;
  var pathOpenBeforeFocus = false;
  var coachEl = root.querySelector("[data-cm-coach]");
  var liveResultsEl = root.querySelector("[data-cm-live-results]");
  var slideHeadEl = root.querySelector(".np-cm-slide-head");
  var deckEl = root.querySelector(".np-cm-deck");
  var reflectEl = root.querySelector("[data-cm-reflect]");
  var outlineItems = Array.prototype.slice.call(root.querySelectorAll(".np-cm-outline-item"));
  var outlineBtns = Array.prototype.slice.call(root.querySelectorAll("[data-cm-index]"));
  var outlineToggles = Array.prototype.slice.call(root.querySelectorAll("[data-cm-toggle-outline]"));
  var filterBtns = Array.prototype.slice.call(root.querySelectorAll("[data-cm-filter]"));

  function loadJsonScript(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    try {
      return JSON.parse(el.textContent || "null");
    } catch (e) {
      return null;
    }
  }

  var checkpointItems = loadJsonScript("cm-checkpoint-json") || [];
  var knowledgeMap = loadJsonScript("cm-knowledge-json") || [];
  var lessonMeta = loadJsonScript("cm-lesson-meta-json") || {};
  var checkpointKey = "np-cm-checkpoint-" + lessonSlug;
  var checkpointEl = document.querySelector("[data-cm-checkpoint]");
  var knowledgeListEl = root.querySelector("[data-cm-knowledge-list]");
  var checkpointState = {
    active: false,
    order: [],
    cursor: 0,
    results: []
  };

  var kindLabels = {
    lesson: "Knowledge Point",
    concept: "Knowledge Point",
    practice: "Question Practice",
    question: "Question Practice",
    example: "Guided Example",
    solution: "Solution Review",
    answer: "Answer Review",
    section: "Lesson Section",
    intro: "Lesson Preview",
    content: "Lesson Path",
    closing: "Wrap Up"
  };

  var progress = loadProgress();
  var studyMode = loadStudyMode();
  var classroomSession = null;
  var lastKnownSlideUpdatedAt = null;
  var classroomSummary = null;
  var classroomSummaryTimer = null;
  var classroomSlidePublishTimer = null;
  var lastPublishedClassroomSlide = null;
  var lastFollowedClassroomSlide = null;

  function loadProgress() {
    try {
      var raw = localStorage.getItem(storageKey);
      return raw ? JSON.parse(raw) : { done: [], viewed: [], reflections: {} };
    } catch (e) {
      return { done: [], viewed: [], reflections: {} };
    }
  }

  function progressPayload() {
    var slide = slides[idx];
    return {
      viewed: progress.viewed || [],
      done: progress.done || [],
      reflections: progress.reflections || {},
      checkpoint: loadCheckpointRecord(),
      study_mode: studyMode ? "on" : "off",
      last_slide_index: slide ? slide.index : (progress.last_slide_index || 1),
      last_active_at: Date.now(),
    };
  }

  function applyRemoteProgress(remote) {
    if (!remote || typeof remote !== "object") return;
    var local = {
      viewed: progress.viewed || [],
      done: progress.done || [],
      reflections: progress.reflections || {},
      checkpoint: loadCheckpointRecord(),
      study_mode: studyMode ? "on" : "off",
    };
    var merged = mergeProgressObjects(local, remote);
    progress.viewed = merged.viewed || [];
    progress.done = merged.done || [];
    progress.reflections = merged.reflections || {};
    progress.last_slide_index = merged.last_slide_index || progress.last_slide_index || 1;
    progress.last_active_at = merged.last_active_at || progress.last_active_at || 0;
    if (merged.checkpoint) {
      try {
        localStorage.setItem(checkpointKey, JSON.stringify(merged.checkpoint));
      } catch (e) {}
    }
    if (merged.study_mode === "off") {
      studyMode = false;
      saveStudyMode();
    } else if (merged.study_mode === "on") {
      studyMode = true;
      saveStudyMode();
    }
    try {
      localStorage.setItem(storageKey, JSON.stringify(progress));
    } catch (e) {}
  }

  function mergeProgressObjects(local, remote) {
    var out = { viewed: [], done: [], reflections: {}, checkpoint: {} };
    ["viewed", "done"].forEach(function (key) {
      var set = {};
      (local[key] || []).concat(remote[key] || []).forEach(function (n) {
        set[n] = true;
      });
      out[key] = Object.keys(set).map(Number).sort(function (a, b) { return a - b; });
    });
    out.reflections = Object.assign({}, remote.reflections || {}, local.reflections || {});
    var cpL = local.checkpoint || {};
    var cpR = remote.checkpoint || {};
    out.checkpoint = {
      best_score: Math.max(cpL.best_score || 0, cpR.best_score || 0),
      best_total: Math.max(cpL.best_total || 0, cpR.best_total || 0),
      last_run: cpL.last_run || cpR.last_run || null,
      missed: (cpL.missed && cpL.missed.length) ? cpL.missed : (cpR.missed || []),
    };
    out.study_mode = local.study_mode || remote.study_mode;
    var localAt = parseInt(local.last_active_at, 10) || 0;
    var remoteAt = parseInt(remote.last_active_at, 10) || 0;
    if (remoteAt > localAt) {
      out.last_active_at = remoteAt;
      out.last_slide_index = parseInt(remote.last_slide_index, 10) || 1;
    } else if (localAt > 0) {
      out.last_active_at = localAt;
      out.last_slide_index = parseInt(local.last_slide_index, 10) || 1;
    } else {
      out.last_slide_index = parseInt(local.last_slide_index || remote.last_slide_index, 10) || 1;
      out.last_active_at = 0;
    }
    return out;
  }

  function saveGlobalLastVisit() {
    var slide = slides[idx];
    if (!slide) return;
    try {
      localStorage.setItem(globalVisitKey, JSON.stringify({
        slug: lessonSlug,
        slide_index: slide.index,
        at: Date.now(),
      }));
    } catch (e) {}
  }

  function parseInitialSlide() {
    try {
      var params = new URLSearchParams(window.location.search);
      var fromQuery = parseInt(params.get("slide"), 10);
      if (fromQuery > 0) return fromQuery;
    } catch (e) {}
    return 0;
  }

  function slideTitleByIndex(n) {
    var s = slideByIndex(n);
    return s ? (s.title || ("Slide " + n)) : ("Slide " + n);
  }

  function showResumeBanner() {
    if (!resumeEl) return;
    try {
      if (sessionStorage.getItem(resumeDismissKey) === "1") return;
    } catch (e) {}
    var target = parseInt(progress.last_slide_index, 10) || 0;
    var initialSlide = parseInitialSlide();
    if (initialSlide > 0) return;
    if (target <= 1) return;
    if (!slideByIndex(target)) return;
    if (idx > 0) return;
    if (resumeTextEl) {
      resumeTextEl.textContent =
        "You were on slide " + target + " (" + slideTitleByIndex(target) + "). Pick up there or start from the beginning.";
    }
    resumeEl.hidden = false;
  }

  function hideResumeBanner() {
    if (resumeEl) resumeEl.hidden = true;
  }

  function scheduleProgressSync() {
    if (!syncEnabled || !progressApi) return;
    if (syncTimer) window.clearTimeout(syncTimer);
    syncTimer = window.setTimeout(function () {
      fetch(progressApi, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ progress: progressPayload() }),
      }).catch(function () {});
    }, 800);
  }

  function loadRemoteProgress() {
    if (!syncEnabled || !progressApi) return Promise.resolve();
    return fetch(progressApi, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.ok && data.progress) {
          applyRemoteProgress(data.progress);
          syncOutlineDone();
          updateStudyStat();
          updateMastery();
          updateKnowledgeMap();
        }
      })
      .catch(function () {});
  }

  function isClassroomFollower() {
    return !!(classroomSession && !classroomSlideApi);
  }

  function setClassroomSession(session) {
    var previousId = classroomSession ? classroomSession.id : null;
    classroomSession = session || null;
    var currentId = classroomSession ? classroomSession.id : null;
    if (currentId !== previousId) {
      // New live class (or class ended): forget cached sync state so the
      // teacher republishes and students re-follow from scratch.
      lastPublishedClassroomSlide = null;
      lastFollowedClassroomSlide = null;
      lastKnownSlideUpdatedAt = null;
      inkUpdatedAt = null;
      inkStrokes = [];
      clearLaserTrail(true);
      hideLaserPreview();
      publishLaserState(false);
    }
    root.classList.toggle("is-classroom-live", !!classroomSession);
    root.classList.toggle("is-classroom-controller", !!(classroomSession && classroomSlideApi));
    updateClassroomPaceBadge();
    updateClassroomLiveBanner();
    syncInkFromSession(false);
    updateInkDock();
    if (!classroomSession) return;
    var remoteSlide = parseInt(classroomSession.current_slide_index, 10) || 0;
    var currentSlide = slides[idx] ? parseInt(slides[idx].index, 10) : 0;
    if (classroomSlideApi) {
      // Teacher: if the server state drifted (failed publish, server
      // restart, another tab), force a republish of the current slide.
      if (remoteSlide !== currentSlide) {
        lastPublishedClassroomSlide = null;
      }
      publishCurrentClassroomSlide();
      return;
    }
    if (remoteSlide > 0) {
      var remoteUpdated = classroomSession.slide_updated_at || "";
      var slideChanged = currentSlide !== remoteSlide;
      var stampChanged = remoteUpdated && remoteUpdated !== lastKnownSlideUpdatedAt;
      if (slideChanged || stampChanged) {
        goToSlideNumber(remoteSlide, { fromClassroomSync: true });
      }
      if (remoteUpdated) lastKnownSlideUpdatedAt = remoteUpdated;
      if (remoteSlide > 0) lastFollowedClassroomSlide = remoteSlide;
    }
  }

  function updateClassroomPaceBadge() {
    var badge = root.querySelector("[data-cm-classroom-pace]");
    if (!classroomSession) {
      if (badge) badge.remove();
      return;
    }
    if (!badge) {
      badge = document.createElement("div");
      badge.setAttribute("data-cm-classroom-pace", "true");
      badge.className = "cm-classroom-pace";
      root.appendChild(badge);
    }
    var slide = parseInt((slides[idx] && slides[idx].index) || classroomSession.current_slide_index || 1, 10) || 1;
    badge.classList.toggle("is-controller", !!classroomSlideApi);
    badge.innerHTML = classroomSlideApi
      ? "<strong>Live Sync</strong><span>Slide " + slide + "</span>"
      : "<strong>Following</strong><span>Slide " + slide + "</span>";
  }

  function updateClassroomLiveBanner() {
    var banner = root.querySelector("[data-cm-classroom-live-banner]");
    if (!classroomSession) {
      if (banner) banner.remove();
      return;
    }
    if (!banner) {
      banner = document.createElement("div");
      banner.setAttribute("data-cm-classroom-live-banner", "true");
      banner.className = "cm-classroom-live-banner";
      var hero = root.querySelector(".np-cm-hero");
      if (hero && hero.parentNode) {
        hero.parentNode.insertBefore(banner, hero.nextSibling);
      } else {
        root.insertBefore(banner, root.firstChild);
      }
    }
    var isFollower = !classroomSlideApi;
    var title = classroomSession.title || "Live class";
    var slide = parseInt(classroomSession.current_slide_index, 10) || 1;
    banner.classList.toggle("is-controller", !isFollower);
    banner.innerHTML = isFollower
      ? "<strong>Live class active</strong><span>" + title + " · slide " + slide + " · your answers are recorded</span>"
      : "<strong>Live class running</strong><span>" + title + " · slide " + slide + "</span>";
  }

  var classroomPollFailures = 0;
  var classroomPollInFlight = false;

  var inkLayerEl = null;
  var inkLatexLayerEl = null;
  var inkFormulaPadEl = null;
  var inkCanvasEl = null;
  var inkDockEl = null;
  var inkReaderEl = null;
  var inkCtx = null;
  var inkStrokes = [];
  var inkCurrentStroke = null;
  var inkDrawing = false;
  var inkColor = "#5b3df5";
  var inkTool = "pen";
  var inkSizeKey = "s";
  var inkEnabled = false;
  var inkExpanded = false;
  var inkUpdatedAt = null;
  var inkSaveTimer = null;
  var inkCanDraw = false;
  var inkResizeObserver = null;
  var inkSavePending = false;
  var inkDpr = 1;
  var inkLaserCanvasEl = null;
  var inkLaserCtx = null;
  var inkEraserRingEl = null;
  var inkLaserPreviewEl = null;
  var inkLaserTrail = [];
  var inkLaserRaf = null;
  var inkLaserTrailMs = 360;
  var inkLaserMaxPts = 120;
  var inkLaserPos = null;
  var inkLaserSaveTimer = null;
  var inkRemoteLaserAt = null;
  var inkLaserDragging = false;
  var inkLaserPollTimer = null;
  var inkClearArmed = false;
  var inkClearArmTimer = null;
  var inkLocalSlideCache = {};
  var inkActiveSlideIndex = null;
  var inkPendingStamp = null;
  var inkPendingLatex = null;
  var inkFormulaPlaceMode = false;
  var inkShapeToastTimer = null;
  var INK_DOCK_VERSION = "v10";
  var INK_PREFS_KEY = "np-cm-ink-prefs-v2";

  var INK_SIZES = { xs: 1.5, s: 2.6, m: 4.8, l: 9 };
  var INK_ERASER_RADIUS = { xs: 0.005, s: 0.009, m: 0.016, l: 0.032 };
  var INK_LASER_SCALE = { xs: 0.45, s: 0.7, m: 0.95, l: 1.3 };
  var INK_SIZE_LABELS = { xs: "Extra fine", s: "Fine", m: "Medium", l: "Bold" };
  var INK_TOOL_LABELS = {
    pen: "Pro pen",
    smart: "Smart shapes",
    math: "Math ink",
    formula: "Formula pad",
    highlighter: "Highlight",
    laser: "Laser",
    eraser: "Eraser",
  };
  var INK_SIZE_ORDER = ["xs", "s", "m", "l"];
  var INK_ICON_SMART =
    '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 2l1.4 4.3H16l-3.7 2.7 1.4 4.3L10 10.6 6.3 13.3l1.4-4.3L4 6.3h4.6L10 2z" stroke="currentColor" stroke-width="1.35" stroke-linejoin="round"/></svg>';
  var INK_ICON_MATH =
    '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 16V4h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M7 10h6M10 7v6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';
  var INK_ICON_PEN =
    '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 16l1.2-4.2L14.5 2.7a1.2 1.2 0 011.7 0l1.1 1.1a1.2 1.2 0 010 1.7L7 14.8 4 16z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>';
  var INK_ICON_HIGHLIGHTER =
    '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M5 15l2-6 8-2-2 8-6 2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>';
  var INK_ICON_LASER =
    '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M2.5 15.5L8 4l2.2 7.2L14 6l3.5 9.5" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/><circle cx="16.5" cy="15.5" r="1.75" fill="currentColor" opacity="0.9"/></svg>';
  var INK_ICON_ERASER =
    '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 12l6-6 7 7-6 6H4v-7z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>';
  var INK_ICON_UNDO =
    '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M6 7H14a4 4 0 010 8H9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M8 4L5 7l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  function inkSmart() {
    return window.NpInkSmart || null;
  }

  function showInkShapeToast(label) {
    if (!inkDockEl) return;
    var rail = inkDockEl.querySelector(".np-cm-ink-rail");
    if (!rail) return;
    var toast = rail.querySelector("[data-ink-shape-toast]");
    if (!toast) {
      toast = document.createElement("span");
      toast.className = "np-cm-ink-shape-toast";
      toast.setAttribute("data-ink-shape-toast", "true");
      var hint = rail.querySelector("[data-ink-hint]");
      if (hint) rail.insertBefore(toast, hint);
      else rail.appendChild(toast);
    }
    toast.textContent = label;
    toast.classList.add("is-visible");
    if (inkShapeToastTimer) window.clearTimeout(inkShapeToastTimer);
    inkShapeToastTimer = window.setTimeout(function () {
      toast.classList.remove("is-visible");
    }, 1400);
  }

  function shapeToastLabel(stroke) {
    if (!stroke || stroke.kind !== "shape") return "";
    var names = {
      circle: "Circle",
      line: "Line",
      triangle: "Triangle",
      rect: "Rectangle",
    };
    return (names[stroke.shape] || "Shape") + " ✓";
  }

  function inkWidthPx() {
    return INK_SIZES[inkSizeKey] || INK_SIZES.s;
  }

  function inkEraserRadius() {
    return INK_ERASER_RADIUS[inkSizeKey] || INK_ERASER_RADIUS.s;
  }

  function inkLaserScale() {
    return INK_LASER_SCALE[inkSizeKey] || INK_LASER_SCALE.s;
  }

  function loadInkPrefs() {
    try {
      var raw = localStorage.getItem(INK_PREFS_KEY);
      if (!raw) return;
      var prefs = JSON.parse(raw);
      if (prefs.color) inkColor = prefs.color;
      if (prefs.tool && INK_TOOL_LABELS[prefs.tool]) inkTool = prefs.tool;
      if (prefs.sizeKey && INK_SIZES[prefs.sizeKey]) inkSizeKey = prefs.sizeKey;
    } catch (e) {}
  }

  function saveInkPrefs() {
    try {
      localStorage.setItem(
        INK_PREFS_KEY,
        JSON.stringify({ color: inkColor, tool: inkTool, sizeKey: inkSizeKey })
      );
    } catch (e) {}
  }

  function stepInkSize(delta) {
    var idx = INK_SIZE_ORDER.indexOf(inkSizeKey);
    if (idx < 0) idx = 1;
    idx = Math.max(0, Math.min(INK_SIZE_ORDER.length - 1, idx + delta));
    inkSizeKey = INK_SIZE_ORDER[idx];
    if (inkDockEl) {
      inkDockEl.querySelectorAll("[data-ink-size]").forEach(function (b) {
        b.classList.toggle("is-active", b.getAttribute("data-ink-size") === inkSizeKey);
      });
    }
    saveInkPrefs();
    syncInkDockState();
  }

  function disarmInkClear(btn) {
    inkClearArmed = false;
    if (inkClearArmTimer) {
      window.clearTimeout(inkClearArmTimer);
      inkClearArmTimer = null;
    }
    if (!btn) return;
    btn.classList.remove("is-armed");
    btn.textContent = "Clear";
    btn.setAttribute("title", "Clear slide");
  }

  function armInkClear(btn) {
    if (!btn) return;
    inkClearArmed = true;
    btn.classList.add("is-armed");
    btn.textContent = "Confirm?";
    btn.setAttribute("title", "Click again to clear this slide for everyone");
    if (inkClearArmTimer) window.clearTimeout(inkClearArmTimer);
    inkClearArmTimer = window.setTimeout(function () {
      disarmInkClear(btn);
    }, 3500);
  }

  function isInkTeacher() {
    return !!classroomSlideApi;
  }

  function cacheLocalInkForSlide(slideIndex) {
    if (!isInkTeacher() || classroomSession || slideIndex == null) return;
    inkLocalSlideCache[String(slideIndex)] = JSON.parse(JSON.stringify(inkStrokes));
  }

  function restoreLocalInkForSlide(slideIndex) {
    if (!isInkTeacher() || classroomSession || slideIndex == null) return;
    inkStrokes = JSON.parse(JSON.stringify(inkLocalSlideCache[String(slideIndex)] || []));
    inkCurrentStroke = null;
    inkUpdatedAt = null;
    inkActiveSlideIndex = slideIndex;
    redrawInkCanvas();
    updateInkActionButtons();
    updateInkReaderBadge();
  }

  function toggleInkToolbar() {
    if (!isInkTeacher()) return;
    updateInkDock();
    inkExpanded = !inkExpanded;
    if (inkExpanded) {
      inkEnabled = true;
      ensureInkLayer();
    }
    syncInkDockState();
  }

  function openInkForTeaching(options) {
    options = options || {};
    if (!isInkTeacher()) return;
    updateInkDock();
    inkExpanded = true;
    inkEnabled = true;
    if (options.tool) inkTool = options.tool;
    if (options.sizeKey) inkSizeKey = options.sizeKey;
    if (inkDockEl) {
      inkDockEl.querySelectorAll("[data-ink-tool]").forEach(function (b) {
        b.classList.toggle("is-active", b.getAttribute("data-ink-tool") === inkTool);
      });
      inkDockEl.querySelectorAll("[data-ink-color]").forEach(function (b) {
        b.classList.toggle("is-active", b.getAttribute("data-ink-color") === inkColor);
      });
      inkDockEl.querySelectorAll("[data-ink-size]").forEach(function (b) {
        b.classList.toggle("is-active", b.getAttribute("data-ink-size") === inkSizeKey);
      });
    }
    saveInkPrefs();
    ensureInkLayer();
    updateInkToolHint();
    syncInkDockState();
    window.requestAnimationFrame(resizeInkCanvas);
  }

  function inkStrokeStyle(color, tool) {
    if (tool === "highlighter") {
      return { color: color, width: inkWidthPx() * 2.4, alpha: 0.38, tool: "highlighter" };
    }
    if (tool === "smart" || tool === "math") {
      return { color: color, width: inkWidthPx() * 1.05, alpha: 1, tool: tool };
    }
    return { color: color, width: inkWidthPx(), alpha: 1, tool: "pen" };
  }

  function updateInkToolHint() {
    if (!inkDockEl) return;
    var rail = inkDockEl.querySelector(".np-cm-ink-rail");
    if (rail) {
      rail.setAttribute(
        "data-ink-mode",
        inkTool === "laser" ? "laser" : inkTool === "eraser" ? "eraser" : "draw"
      );
    }
    var hintEl = inkDockEl.querySelector("[data-ink-hint]");
    if (hintEl) {
      var extra = "";
      if (inkTool === "smart") extra = " — draw ○ △ □";
      if (inkTool === "math") {
        extra = inkPendingStamp
          ? " — tap slide to place " + inkPendingStamp
          : inkPendingLatex
            ? " — tap slide to place formula"
            : " — symbols, fraction bars, or open ƒx pad";
      }
      if (inkFormulaPlaceMode) extra = " — tap slide to place formula";
      hintEl.textContent =
        (INK_TOOL_LABELS[inkTool] || "Pen") +
        " · " +
        (INK_SIZE_LABELS[inkSizeKey] || "Fine") +
        extra;
    }
    var mathRow = inkDockEl.querySelector("[data-ink-math-row]");
    if (mathRow) {
      mathRow.hidden = inkTool !== "math";
    }
  }

  function renderLatexOverlays() {
    if (!inkLatexLayerEl || !slideEl) return;
    inkLatexLayerEl.innerHTML = "";
    var latexStrokes = inkStrokes.filter(function (s) { return s && s.kind === "latex" && s.latex; });
    if (!latexStrokes.length) return;
    latexStrokes.forEach(function (stroke, idx) {
      var el = document.createElement("div");
      el.className = "np-cm-ink-latex-stamp";
      el.style.left = String(stroke.x * 100) + "%";
      el.style.top = String(stroke.y * 100) + "%";
      el.style.color = stroke.color || inkColor;
      el.style.fontSize = Math.max(14, (stroke.size || 0.038) * slideEl.offsetHeight) + "px";
      el.style.whiteSpace = "normal";
      el.style.maxWidth = Math.max(120, slideEl.offsetWidth * 0.55) + "px";
      el.setAttribute("data-latex-idx", String(idx));
      el.textContent = "\\(" + stroke.latex + "\\)";
      inkLatexLayerEl.appendChild(el);
    });
    if (window.MathJax && window.MathJax.typesetPromise) {
      window.MathJax.typesetPromise([inkLatexLayerEl]).catch(function () {});
    }
  }

  function openFormulaPad() {
    ensureFormulaPad();
    if (!inkFormulaPadEl) return;
    inkFormulaPadEl.hidden = false;
    inkExpanded = true;
    inkEnabled = true;
    var input = inkFormulaPadEl.querySelector("[data-formula-input]");
    if (input) {
      input.focus();
      updateFormulaPreview(input.value);
    }
  }

  function closeFormulaPad() {
    if (inkFormulaPadEl) inkFormulaPadEl.hidden = true;
    inkFormulaPlaceMode = false;
    inkPendingLatex = null;
    syncInkDockState();
  }

  function ensureFormulaPad() {
    if (inkFormulaPadEl || !root) return;
    var smart = inkSmart();
    var keysHtml = "";
    if (smart && smart.FORMULA_KEYS) {
      smart.FORMULA_KEYS.forEach(function (k) {
        keysHtml +=
          '<button type="button" class="np-cm-formula-key" data-formula-insert="' +
          k.insert.replace(/"/g, "&quot;") +
          '">' +
          k.label +
          "</button>";
      });
    }
    inkFormulaPadEl = document.createElement("div");
    inkFormulaPadEl.className = "np-cm-formula-pad";
    inkFormulaPadEl.hidden = true;
    inkFormulaPadEl.innerHTML =
      '<div class="np-cm-formula-pad-head" data-formula-drag-handle title="Drag to move">' +
      '<span class="np-cm-formula-pad-grip" aria-hidden="true">⋮⋮</span>' +
      '<strong>ƒx Formula pad</strong>' +
      '<button type="button" class="np-cm-formula-pad-close" data-formula-close aria-label="Close">×</button>' +
      "</div>" +
      '<p class="np-cm-formula-pad-lead">Type like Desmos — <code>Enter</code> for new line, <code>Ctrl+Enter</code> to place.</p>' +
      '<textarea class="np-cm-formula-input" data-formula-input rows="4" placeholder="Line 1: y = mx + b&#10;Line 2: \\frac{a}{b}" spellcheck="false" autocomplete="off"></textarea>' +
      '<div class="np-cm-formula-preview" data-formula-preview></div>' +
      '<div class="np-cm-formula-keys">' +
      keysHtml +
      "</div>" +
      '<div class="np-cm-formula-actions">' +
      '<button type="button" class="np-cm-formula-place" data-formula-place>Place on slide</button>' +
      "</div>";
    root.appendChild(inkFormulaPadEl);
    bindFormulaPadEvents();
  }

  function updateFormulaPreview(raw) {
    if (!inkFormulaPadEl) return;
    var preview = inkFormulaPadEl.querySelector("[data-formula-preview]");
    var input = inkFormulaPadEl.querySelector("[data-formula-input]");
    if (!preview) return;
    var smart = inkSmart();
    var latex = smart && smart.normalizeLatexInput ? smart.normalizeLatexInput(raw || (input && input.value) || "") : (raw || "");
    if (!latex) {
      preview.innerHTML = '<span class="np-cm-formula-preview-empty">Preview appears here</span>';
      return;
    }
    preview.innerHTML = "\\(" + latex + "\\)";
    if (window.MathJax && window.MathJax.typesetPromise) {
      window.MathJax.typesetPromise([preview]).catch(function () {});
    }
  }

  function bindFormulaPadEvents() {
    if (!inkFormulaPadEl || inkFormulaPadEl.getAttribute("data-bound") === "1") return;
    inkFormulaPadEl.setAttribute("data-bound", "1");
    var input = inkFormulaPadEl.querySelector("[data-formula-input]");
    var closeBtn = inkFormulaPadEl.querySelector("[data-formula-close]");
    var placeBtn = inkFormulaPadEl.querySelector("[data-formula-place]");
    if (input) {
      input.addEventListener("input", function () {
        updateFormulaPreview(input.value);
      });
      input.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) {
          ev.preventDefault();
          armFormulaPlacement();
        }
      });
    }
    if (closeBtn) closeBtn.addEventListener("click", closeFormulaPad);
    if (placeBtn) placeBtn.addEventListener("click", armFormulaPlacement);
    bindFormulaPadDrag();
    inkFormulaPadEl.querySelectorAll("[data-formula-insert]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!input) return;
        var insert = btn.getAttribute("data-formula-insert") || "";
        var start = input.selectionStart || input.value.length;
        var end = input.selectionEnd || start;
        input.value = input.value.slice(0, start) + insert + input.value.slice(end);
        input.focus();
        input.selectionStart = input.selectionEnd = start + insert.length;
        updateFormulaPreview(input.value);
      });
    });
  }

  function bindFormulaPadDrag() {
    if (!inkFormulaPadEl) return;
    var handle = inkFormulaPadEl.querySelector("[data-formula-drag-handle]");
    if (!handle || handle.getAttribute("data-drag-bound") === "1") return;
    handle.setAttribute("data-drag-bound", "1");
    var dragging = false;
    var offsetX = 0;
    var offsetY = 0;

    function onMove(e) {
      if (!dragging || !inkFormulaPadEl) return;
      var x = e.clientX - offsetX;
      var y = e.clientY - offsetY;
      var padW = inkFormulaPadEl.offsetWidth;
      var padH = inkFormulaPadEl.offsetHeight;
      x = Math.max(8, Math.min(window.innerWidth - padW - 8, x));
      y = Math.max(8, Math.min(window.innerHeight - padH - 8, y));
      inkFormulaPadEl.style.left = x + "px";
      inkFormulaPadEl.style.top = y + "px";
    }

    function onUp(e) {
      if (!dragging) return;
      dragging = false;
      inkFormulaPadEl.classList.remove("is-dragging");
      handle.classList.remove("is-dragging");
      try { handle.releasePointerCapture(e.pointerId); } catch (err) {}
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }

    handle.addEventListener("pointerdown", function (e) {
      if (e.target.closest("[data-formula-close]")) return;
      dragging = true;
      var rect = inkFormulaPadEl.getBoundingClientRect();
      inkFormulaPadEl.style.bottom = "auto";
      inkFormulaPadEl.style.transform = "none";
      inkFormulaPadEl.style.left = rect.left + "px";
      inkFormulaPadEl.style.top = rect.top + "px";
      offsetX = e.clientX - rect.left;
      offsetY = e.clientY - rect.top;
      inkFormulaPadEl.classList.add("is-dragging");
      handle.classList.add("is-dragging");
      handle.setPointerCapture(e.pointerId);
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      e.preventDefault();
    });
  }

  function armFormulaPlacement() {
    var input = inkFormulaPadEl && inkFormulaPadEl.querySelector("[data-formula-input]");
    var smart = inkSmart();
    if (!input || !smart || !smart.normalizeLatexInput) return;
    var latex = smart.normalizeLatexInput(input.value);
    if (!latex) return;
    inkPendingLatex = latex;
    inkPendingStamp = null;
    inkFormulaPlaceMode = true;
    inkTool = "math";
    inkEnabled = true;
    if (inkDockEl) {
      inkDockEl.querySelectorAll("[data-ink-tool]").forEach(function (b) {
        b.classList.toggle("is-active", b.getAttribute("data-ink-tool") === "math");
      });
      inkDockEl.querySelectorAll("[data-ink-stamp]").forEach(function (b) {
        b.classList.remove("is-active");
      });
    }
    updateInkToolHint();
    syncInkDockState();
    if (inkFormulaPadEl) inkFormulaPadEl.hidden = true;
  }

  function placeLatexStamp(pt, latex) {
    var smart = inkSmart();
    if (!smart || !smart.createLatexStamp || !latex) return;
    inkStrokes.push(smart.createLatexStamp(latex, pt[0], pt[1], inkColor, 0.042));
    inkPendingLatex = null;
    inkFormulaPlaceMode = false;
    redrawInkCanvas();
    scheduleInkSave();
    updateInkActionButtons();
    updateInkToolHint();
    syncInkDockState();
  }

  function ensureInkLayer() {
    if (!slideEl) return;
    if (!inkLayerEl) {
      inkLayerEl = document.createElement("div");
      inkLayerEl.className = "np-cm-ink-layer";
      inkLayerEl.setAttribute("data-cm-ink-layer", "true");
      inkCanvasEl = document.createElement("canvas");
      inkCanvasEl.className = "np-cm-ink-canvas";
      inkCanvasEl.setAttribute("data-cm-ink-canvas", "true");
      inkLayerEl.appendChild(inkCanvasEl);
      inkLatexLayerEl = document.createElement("div");
      inkLatexLayerEl.className = "np-cm-ink-latex-layer";
      inkLatexLayerEl.setAttribute("data-cm-ink-latex-layer", "true");
      inkLayerEl.appendChild(inkLatexLayerEl);
      slideEl.appendChild(inkLayerEl);
      inkCtx = inkCanvasEl.getContext("2d");
      window.addEventListener("resize", resizeInkCanvas);
      if (stageEl) stageEl.addEventListener("scroll", resizeInkCanvas, { passive: true });
      if (window.ResizeObserver && slideEl) {
        inkResizeObserver = new ResizeObserver(resizeInkCanvas);
        inkResizeObserver.observe(slideEl);
      }
      bindInkPointerEvents();
    } else if (!inkLatexLayerEl) {
      inkLatexLayerEl = document.createElement("div");
      inkLatexLayerEl.className = "np-cm-ink-latex-layer";
      inkLatexLayerEl.setAttribute("data-cm-ink-latex-layer", "true");
      inkLayerEl.appendChild(inkLatexLayerEl);
    }
    ensureLaserCanvas();
    ensureEraserRing();
    ensureLaserPreview();
    updateInkDock();
    resizeInkCanvas();
  }

  function ensureLaserCanvas() {
    if (!inkLayerEl) return;
    if (!inkLaserCanvasEl) {
      inkLaserCanvasEl = document.createElement("canvas");
      inkLaserCanvasEl.className = "np-cm-laser-canvas";
      inkLaserCanvasEl.setAttribute("data-cm-laser-canvas", "true");
      inkLayerEl.appendChild(inkLaserCanvasEl);
      inkLaserCtx = inkLaserCanvasEl.getContext("2d");
    }
  }

  function ensureLaserPreview() {
    if (!inkLayerEl) return;
    if (!inkLaserPreviewEl) {
      inkLaserPreviewEl = document.createElement("div");
      inkLaserPreviewEl.className = "np-cm-laser-preview";
      inkLaserPreviewEl.setAttribute("data-cm-laser-preview", "true");
      inkLaserPreviewEl.innerHTML =
        '<span class="np-cm-laser-preview-ring" aria-hidden="true"></span>' +
        '<span class="np-cm-laser-preview-core" aria-hidden="true"></span>';
      inkLaserPreviewEl.hidden = true;
      inkLayerEl.appendChild(inkLaserPreviewEl);
    }
  }

  function moveLaserPreview(pt) {
    ensureLaserPreview();
    if (!inkLaserPreviewEl || !pt) return;
    inkLaserPreviewEl.hidden = false;
    inkLaserPreviewEl.style.setProperty("--laser-x", String(pt[0] * 100) + "%");
    inkLaserPreviewEl.style.setProperty("--laser-y", String(pt[1] * 100) + "%");
    inkLaserPreviewEl.style.setProperty("--laser-sc", String(inkLaserScale()));
    inkLaserPreviewEl.classList.toggle("is-drawing", !!inkLaserDragging);
  }

  function hideLaserPreview() {
    if (inkLaserPreviewEl) inkLaserPreviewEl.hidden = true;
  }

  function ensureEraserRing() {
    if (!inkLayerEl) return;
    if (!inkEraserRingEl) {
      inkEraserRingEl = document.createElement("div");
      inkEraserRingEl.className = "np-cm-eraser-ring";
      inkEraserRingEl.setAttribute("data-cm-eraser-ring", "true");
      inkEraserRingEl.hidden = true;
      inkLayerEl.appendChild(inkEraserRingEl);
    }
  }

  function resizeLaserCanvas() {
    if (!inkLaserCanvasEl || !slideEl || !inkLaserCtx) return;
    var cssW = slideEl.offsetWidth;
    var cssH = slideEl.offsetHeight;
    if (!cssW || !cssH) return;
    var bufW = Math.max(1, Math.round(cssW * inkDpr));
    var bufH = Math.max(1, Math.round(cssH * inkDpr));
    inkLaserCanvasEl.style.width = cssW + "px";
    inkLaserCanvasEl.style.height = cssH + "px";
    if (inkLaserCanvasEl.width !== bufW || inkLaserCanvasEl.height !== bufH) {
      inkLaserCanvasEl.width = bufW;
      inkLaserCanvasEl.height = bufH;
    }
  }

  function pruneLaserTrail(now) {
    inkLaserTrail = inkLaserTrail.filter(function (p) {
      return now - p.t < inkLaserTrailMs;
    });
    if (inkLaserTrail.length > inkLaserMaxPts) {
      inkLaserTrail = inkLaserTrail.slice(-inkLaserMaxPts);
    }
  }

  function pushLaserTrailPoint(pt) {
    if (!pt) return;
    var now = performance.now();
    inkLaserPos = [pt[0], pt[1]];
    var last = inkLaserTrail.length ? inkLaserTrail[inkLaserTrail.length - 1] : null;
    if (last && Math.hypot(pt[0] - last.x, pt[1] - last.y) < inkLaserMinStep()) return;
    inkLaserTrail.push({ x: pt[0], y: pt[1], t: now });
    pruneLaserTrail(now);
    ensureLaserLoop();
  }

  function laserTrailForPublish() {
    return inkLaserTrail.slice(-14).map(function (p) {
      return [Math.round(p.x * 1000) / 1000, Math.round(p.y * 1000) / 1000];
    });
  }

  function drawLaserHead(ctx, p, life, w, h) {
    if (!p || life <= 0) return;
    var sc = inkLaserScale();
    var x = p.x * w;
    var y = p.y * h;
    var r = (2 + life * 1.5) * inkDpr * sc;
    var glow = ctx.createRadialGradient(x, y, 0, x, y, r * 2.4);
    glow.addColorStop(0, "rgba(255, 255, 255, " + (0.9 * life) + ")");
    glow.addColorStop(0.35, "rgba(255, 90, 70, " + (0.45 * life) + ")");
    glow.addColorStop(1, "rgba(255, 40, 40, 0)");
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(x, y, r * 2.4, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "rgba(255,255,255," + (0.88 * life) + ")";
    ctx.beginPath();
    ctx.arc(x, y, r * 0.5, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawLaserTrailSegment(ctx, p0, p1, life, w, h) {
    if (life <= 0) return;
    var sc = inkLaserScale();
    var x0 = p0.x * w;
    var y0 = p0.y * h;
    var x1 = p1.x * w;
    var y1 = p1.y * h;
    var alpha = life * life;
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "rgba(255, 45, 45, " + (alpha * 0.18) + ")";
    ctx.lineWidth = (6 + life * 4) * inkDpr * sc;
    ctx.shadowColor = "rgba(255, 60, 60, " + (alpha * 0.4) + ")";
    ctx.shadowBlur = 8 * inkDpr * life * sc;
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = "rgba(255, 180, 120, " + (alpha * 0.5) + ")";
    ctx.lineWidth = (2.5 + life * 2) * inkDpr * sc;
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
    ctx.strokeStyle = "rgba(255, 255, 255, " + (alpha * 0.82) + ")";
    ctx.lineWidth = (1 + life * 1.2) * inkDpr * sc;
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
    ctx.restore();
  }

  function drawLaserTrailFrame() {
    if (!inkLaserCtx || !inkLaserCanvasEl) return;
    var now = performance.now();
    pruneLaserTrail(now);
    var w = inkLaserCanvasEl.width;
    var h = inkLaserCanvasEl.height;
    inkLaserCtx.setTransform(1, 0, 0, 1, 0, 0);
    inkLaserCtx.clearRect(0, 0, w, h);
    var pts = inkLaserTrail;
    if (!pts.length) return;
    if (pts.length === 1) {
      var loneLife = 1 - (now - pts[0].t) / inkLaserTrailMs;
      drawLaserHead(inkLaserCtx, pts[0], Math.max(0, loneLife), w, h);
      return;
    }
    for (var i = 1; i < pts.length; i++) {
      var life = 1 - (now - pts[i].t) / inkLaserTrailMs;
      drawLaserTrailSegment(inkLaserCtx, pts[i - 1], pts[i], Math.max(0, life), w, h);
    }
    var head = pts[pts.length - 1];
    var headLife = 1 - (now - head.t) / inkLaserTrailMs;
    drawLaserHead(inkLaserCtx, head, Math.max(0, headLife), w, h);
  }

  function tickLaserTrail() {
    inkLaserRaf = null;
    drawLaserTrailFrame();
    var now = performance.now();
    pruneLaserTrail(now);
    if (inkLaserTrail.length) {
      inkLaserRaf = window.requestAnimationFrame(tickLaserTrail);
    }
  }

  function ensureLaserLoop() {
    if (!inkLaserRaf) inkLaserRaf = window.requestAnimationFrame(tickLaserTrail);
  }

  function clearLaserTrail(immediate) {
    if (inkLaserRaf) {
      window.cancelAnimationFrame(inkLaserRaf);
      inkLaserRaf = null;
    }
    if (immediate) {
      inkLaserTrail = [];
      inkLaserPos = null;
      if (inkLaserCtx && inkLaserCanvasEl) {
        inkLaserCtx.clearRect(0, 0, inkLaserCanvasEl.width, inkLaserCanvasEl.height);
      }
      return;
    }
    ensureLaserLoop();
  }

  function scheduleLaserPublish(active) {
    if (!classroomInkApi || !classroomSlideApi || !classroomSession) return;
    if (inkLaserSaveTimer) window.clearTimeout(inkLaserSaveTimer);
    inkLaserSaveTimer = window.setTimeout(function () {
      publishLaserState(active);
    }, 28);
  }

  function publishLaserState(active) {
    if (!classroomInkApi || !classroomSession) return;
    var slide = slides[idx];
    if (!slide) return;
    fetch(classroomInkApi, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slide_index: parseInt(slide.index, 10),
        laser: {
          active: !!active,
          x: active && inkLaserPos ? inkLaserPos[0] : null,
          y: active && inkLaserPos ? inkLaserPos[1] : null,
          trail: active ? laserTrailForPublish() : [],
        },
      }),
    }).catch(function () {});
  }

  function ingestRemoteLaser(laser) {
    if (!laser) {
      clearLaserTrail(true);
      return;
    }
    var slide = slides[idx];
    if (!slide) return;
    var slideIndex = parseInt(slide.index, 10);
    if (!laser.active || parseInt(laser.slide_index, 10) !== slideIndex) {
      clearLaserTrail(true);
      return;
    }
    ensureInkLayer();
    var now = performance.now();
    var trail = Array.isArray(laser.trail) ? laser.trail : [];
    if (trail.length >= 2) {
      inkLaserTrail = trail.map(function (p, i) {
        return {
          x: Number(p[0]),
          y: Number(p[1]),
          t: now - (trail.length - 1 - i) * 24,
        };
      });
      inkLaserPos = [inkLaserTrail[inkLaserTrail.length - 1].x, inkLaserTrail[inkLaserTrail.length - 1].y];
      ensureLaserLoop();
      return;
    }
    if (laser.x != null && laser.y != null) {
      pushLaserTrailPoint([Number(laser.x), Number(laser.y)]);
    }
  }

  function syncRemoteLaser(force) {
    if (!classroomSession || classroomSlideApi) return;
    var laser = classroomSession.laser || null;
    if (!force && laser && laser.updated_at && laser.updated_at === inkRemoteLaserAt && !laser.active) {
      clearLaserTrail(true);
      return;
    }
    inkRemoteLaserAt = laser ? laser.updated_at || null : null;
    ingestRemoteLaser(laser);
  }

  function startLaserPoll() {
    if (inkLaserPollTimer || classroomSlideApi || !classroomInkApi) return;
    inkLaserPollTimer = window.setInterval(pollRemoteLaser, 100);
  }

  function stopLaserPoll() {
    if (inkLaserPollTimer) window.clearInterval(inkLaserPollTimer);
    inkLaserPollTimer = null;
  }

  function pollRemoteLaser() {
    if (!classroomInkApi || !classroomSession || classroomSlideApi) return;
    var slide = slides[idx];
    if (!slide) return;
    fetch(
      classroomInkApi + "?slide_index=" + encodeURIComponent(slide.index) + "&fields=laser",
      { credentials: "same-origin" }
    )
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.ok || !data.laser) return;
        classroomSession.laser = data.laser;
        syncRemoteLaser(false);
      })
      .catch(function () {});
  }

  function moveEraserRing(pt) {
    ensureEraserRing();
    if (!inkEraserRingEl || !pt) return;
    var radiusPx = Math.max(8, inkEraserRadius() * (slideEl ? slideEl.offsetWidth : 400));
    inkEraserRingEl.hidden = false;
    inkEraserRingEl.style.setProperty("--eraser-x", String(pt[0] * 100) + "%");
    inkEraserRingEl.style.setProperty("--eraser-y", String(pt[1] * 100) + "%");
    inkEraserRingEl.style.setProperty("--eraser-r", String(radiusPx) + "px");
  }

  function hideEraserRing() {
    if (inkEraserRingEl) inkEraserRingEl.hidden = true;
  }

  function buildInkDockHtml() {
    var smart = inkSmart();
    var mathBtns = "";
    if (smart && smart.MATH_STAMPS) {
      smart.MATH_STAMPS.forEach(function (item) {
        mathBtns +=
          '<button type="button" class="np-cm-ink-math-btn" data-ink-stamp="' +
          item.t.replace(/"/g, "&quot;") +
          '" title="' +
          item.label +
          '">' +
          item.t +
          "</button>";
      });
    }
    return (
      '<div class="np-cm-ink-rail-wrap">' +
      '<div class="np-cm-ink-rail">' +
      '<div class="np-cm-ink-rail-group np-cm-ink-rail-group--tools">' +
      '<button type="button" class="np-cm-ink-chip is-active" data-ink-tool="pen" title="Pro pen (smooth ink)">' + INK_ICON_PEN + "</button>" +
      '<button type="button" class="np-cm-ink-chip np-cm-ink-chip--smart" data-ink-tool="smart" title="Smart shapes (M) — circle, triangle, line">' + INK_ICON_SMART + "</button>" +
      '<button type="button" class="np-cm-ink-chip np-cm-ink-chip--math" data-ink-tool="math" title="Math ink (G) — symbols &amp; fraction bars">' + INK_ICON_MATH + "</button>" +
      '<button type="button" class="np-cm-ink-chip" data-ink-tool="highlighter" title="Highlighter">' + INK_ICON_HIGHLIGHTER + "</button>" +
      '<button type="button" class="np-cm-ink-chip np-cm-ink-chip--laser" data-ink-tool="laser" title="Laser (L) — hover to aim, drag for beam">' + INK_ICON_LASER + "</button>" +
      '<button type="button" class="np-cm-ink-chip" data-ink-tool="eraser" title="Eraser (E)">' + INK_ICON_ERASER + "</button>" +
      "</div>" +
      '<span class="np-cm-ink-rail-vsep" aria-hidden="true"></span>' +
      '<div class="np-cm-ink-rail-group np-cm-ink-rail-group--colors">' +
      '<button type="button" class="np-cm-ink-swatch is-active" data-ink-color="#5b3df5" aria-label="Purple"></button>' +
      '<button type="button" class="np-cm-ink-swatch" data-ink-color="#ef4444" aria-label="Red"></button>' +
      '<button type="button" class="np-cm-ink-swatch" data-ink-color="#2563eb" aria-label="Blue"></button>' +
      '<button type="button" class="np-cm-ink-swatch" data-ink-color="#059669" aria-label="Green"></button>' +
      '<button type="button" class="np-cm-ink-swatch" data-ink-color="#1e293b" aria-label="Black"></button>' +
      "</div>" +
      '<span class="np-cm-ink-rail-vsep" aria-hidden="true"></span>' +
      '<div class="np-cm-ink-rail-group np-cm-ink-rail-group--sizes">' +
      '<button type="button" class="np-cm-ink-size-btn" data-ink-size="xs" title="Extra fine"><i></i></button>' +
      '<button type="button" class="np-cm-ink-size-btn is-active" data-ink-size="s" title="Fine"><i></i></button>' +
      '<button type="button" class="np-cm-ink-size-btn" data-ink-size="m" title="Medium"><i></i></button>' +
      '<button type="button" class="np-cm-ink-size-btn" data-ink-size="l" title="Bold"><i></i></button>' +
      "</div>" +
      '<span class="np-cm-ink-rail-hint" data-ink-hint aria-live="polite">Pen · Fine</span>' +
      '<span class="np-cm-ink-rail-vsep" aria-hidden="true"></span>' +
      '<div class="np-cm-ink-rail-group np-cm-ink-rail-group--edit">' +
      '<button type="button" class="np-cm-ink-chip" data-ink-undo title="Undo (U)" disabled>' + INK_ICON_UNDO + "</button>" +
      '<button type="button" class="np-cm-ink-chip np-cm-ink-chip--clear" data-ink-clear title="Clear slide">Clear</button>' +
      "</div>" +
      '<span class="np-cm-ink-sync is-synced" data-ink-status title="Ready">' +
      '<span class="np-cm-ink-sync-dot"></span></span>' +
      '<button type="button" class="np-cm-ink-rail-close" data-ink-collapse title="Close (P)" aria-label="Close pen toolbar">×</button>' +
      "</div>" +
      '<div class="np-cm-ink-math-row" data-ink-math-row hidden>' +
      '<button type="button" class="np-cm-ink-formula-open" data-ink-formula-open title="Formula pad (F) — Desmos-style LaTeX">ƒx</button>' +
      mathBtns +
      "</div>" +
      "</div>"
    );
  }
  function ensureInkCompactButton() {
    if (!inkCompactSlot) return null;
    var btn = inkCompactSlot.querySelector("[data-ink-compact-toggle]");
    if (!btn) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.className = "np-cm-ink-compact";
      btn.setAttribute("data-ink-compact-toggle", "true");
      btn.setAttribute("aria-pressed", "false");
      btn.title = "Open live pen (P) — works before Live Class starts";
      btn.innerHTML = INK_ICON_PEN;
      btn.addEventListener("click", function () {
        toggleInkToolbar();
      });
      inkCompactSlot.appendChild(btn);
    }
    return btn;
  }

  function bindInkDockEvents() {
    if (!inkDockEl || inkDockEl.getAttribute("data-cm-ink-bound") === "1") return;
    inkDockEl.setAttribute("data-cm-ink-bound", "1");

    var collapseBtn = inkDockEl.querySelector("[data-ink-collapse]");
    if (collapseBtn) {
      collapseBtn.addEventListener("click", function () {
        disarmInkClear(inkDockEl.querySelector("[data-ink-clear]"));
        inkExpanded = false;
        inkEnabled = false;
        publishLaserState(false);
        clearLaserTrail(true);
        hideLaserPreview();
        hideEraserRing();
        syncInkDockState();
      });
    }

    inkDockEl.querySelectorAll("[data-ink-tool]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        inkTool = btn.getAttribute("data-ink-tool") || "pen";
        inkPendingStamp = null;
        inkPendingLatex = null;
        inkFormulaPlaceMode = false;
        inkDockEl.querySelectorAll("[data-ink-stamp]").forEach(function (b) {
          b.classList.remove("is-active");
        });
        inkDockEl.querySelectorAll("[data-ink-tool]").forEach(function (b) {
          b.classList.toggle("is-active", b === btn);
        });
        if (inkTool === "laser") {
          inkEnabled = true;
          hideEraserRing();
          clearLaserTrail(true);
        } else {
          hideLaserPreview();
        }
        if (!inkEnabled && inkTool !== "eraser") {
          inkEnabled = true;
        }
        if (inkTool !== "laser") {
          publishLaserState(false);
          clearLaserTrail(true);
        }
        updateInkToolHint();
        syncInkDockState();
        saveInkPrefs();
      });
    });

    inkDockEl.querySelectorAll("[data-ink-stamp]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var sym = btn.getAttribute("data-ink-stamp") || "";
        if (inkPendingStamp === sym) {
          inkPendingStamp = null;
          btn.classList.remove("is-active");
        } else {
          inkPendingStamp = sym;
          inkPendingLatex = null;
          inkFormulaPlaceMode = false;
          inkDockEl.querySelectorAll("[data-ink-stamp]").forEach(function (b) {
            b.classList.toggle("is-active", b === btn);
          });
          inkTool = "math";
          inkEnabled = true;
          inkDockEl.querySelectorAll("[data-ink-tool]").forEach(function (b) {
            b.classList.toggle("is-active", b.getAttribute("data-ink-tool") === "math");
          });
        }
        updateInkToolHint();
        syncInkDockState();
      });
    });

    var formulaOpenBtn = inkDockEl.querySelector("[data-ink-formula-open]");
    if (formulaOpenBtn) {
      formulaOpenBtn.addEventListener("click", function () {
        inkTool = "math";
        inkEnabled = true;
        inkDockEl.querySelectorAll("[data-ink-tool]").forEach(function (b) {
          b.classList.toggle("is-active", b.getAttribute("data-ink-tool") === "math");
        });
        openFormulaPad();
        updateInkToolHint();
        syncInkDockState();
      });
    }

    inkDockEl.querySelectorAll("[data-ink-color]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        inkColor = btn.getAttribute("data-ink-color") || "#ef4444";
        inkDockEl.querySelectorAll("[data-ink-color]").forEach(function (b) {
          b.classList.toggle("is-active", b === btn);
        });
        if (inkTool === "eraser" || inkTool === "laser") {
          inkTool = "pen";
          inkDockEl.querySelectorAll("[data-ink-tool]").forEach(function (b) {
            b.classList.toggle("is-active", b.getAttribute("data-ink-tool") === "pen");
          });
          updateInkToolHint();
        }
        syncInkDockState();
        saveInkPrefs();
      });
    });

    inkDockEl.querySelectorAll("[data-ink-size]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        inkSizeKey = btn.getAttribute("data-ink-size") || "m";
        inkDockEl.querySelectorAll("[data-ink-size]").forEach(function (b) {
          b.classList.toggle("is-active", b === btn);
        });
        syncInkDockState();
        saveInkPrefs();
        if (inkTool === "eraser" && inkEraserRingEl && !inkEraserRingEl.hidden) {
          var ex = parseFloat(inkEraserRingEl.style.getPropertyValue("--eraser-x")) / 100;
          var ey = parseFloat(inkEraserRingEl.style.getPropertyValue("--eraser-y")) / 100;
          if (!isNaN(ex) && !isNaN(ey)) moveEraserRing([ex, ey]);
        }
      });
    });

    var undoBtn = inkDockEl.querySelector("[data-ink-undo]");
    if (undoBtn) {
      undoBtn.addEventListener("click", function () {
        if (!inkStrokes.length) return;
        inkStrokes.pop();
        inkCurrentStroke = null;
        redrawInkCanvas();
        scheduleInkSave();
        updateInkActionButtons();
      });
    }

    var clearBtn = inkDockEl.querySelector("[data-ink-clear]");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        if (!inkStrokes.length) return;
        if (!inkClearArmed) {
          armInkClear(clearBtn);
          return;
        }
        disarmInkClear(clearBtn);
        inkStrokes = [];
        inkCurrentStroke = null;
        redrawInkCanvas();
        scheduleInkSave();
        if (isInkTeacher() && !classroomSession && slides[idx]) {
          cacheLocalInkForSlide(slides[idx].index);
        }
        updateInkActionButtons();
      });
    }
  }

  function updateInkActionButtons() {
    if (!inkDockEl) return;
    var undoBtn = inkDockEl.querySelector("[data-ink-undo]");
    var clearBtn = inkDockEl.querySelector("[data-ink-clear]");
    var hasStrokes = inkStrokes.length > 0;
    if (undoBtn) undoBtn.disabled = !hasStrokes;
    if (clearBtn) clearBtn.disabled = !hasStrokes;
  }

  function setInkStatus(kind, text) {
    if (!inkDockEl) return;
    var statusEl = inkDockEl.querySelector("[data-ink-status]");
    if (!statusEl) return;
    statusEl.classList.remove("is-synced", "is-pending", "is-drawing");
    if (kind) statusEl.classList.add(kind);
    if (text) statusEl.setAttribute("title", text);
  }

  function syncInkDockState() {
    if (inkCompactSlot) {
      var compactBtn = ensureInkCompactButton();
      if (compactBtn) {
        compactBtn.classList.toggle("is-active", !!inkExpanded);
        compactBtn.setAttribute("aria-pressed", inkExpanded ? "true" : "false");
      }
    }
    var chromeTools = root.querySelector("[data-cm-chrome-tools]");
    if (chromeTools) {
      chromeTools.hidden = !inkExpanded;
      chromeTools.classList.toggle("is-ink-open", !!inkExpanded);
    }
    if (!inkExpanded) hideLaserPreview();
    if (!inkDockEl) return;
    if (inkTool === "laser" && inkExpanded) inkEnabled = true;
    var railEl = inkDockEl.querySelector(".np-cm-ink-rail");
    if (railEl) {
      railEl.classList.toggle("is-laser-tool", inkTool === "laser");
    }
    if (inkTool !== "laser") hideLaserPreview();
    root.classList.toggle("is-pen-active", !!(inkEnabled && isInkTeacher() && inkTool !== "laser"));
    root.classList.toggle("is-laser-active", !!(inkEnabled && isInkTeacher() && inkTool === "laser"));
    if (inkCanvasEl) {
      var laserMode = inkTool === "laser" && inkEnabled && inkExpanded;
      var drawable = !!(inkCanDraw && inkEnabled && isInkTeacher() && inkTool !== "eraser" && inkTool !== "laser");
      inkCanvasEl.classList.toggle(
        "is-drawable",
        (inkCanDraw && inkExpanded && isInkTeacher() && inkEnabled) &&
          (drawable || inkTool === "eraser" || inkTool === "laser")
      );
      inkCanvasEl.classList.toggle("is-eraser", inkTool === "eraser" && inkEnabled);
      inkCanvasEl.classList.toggle("is-highlighter", inkTool === "highlighter" && inkEnabled);
      inkCanvasEl.classList.toggle("is-laser", laserMode);
      inkCanvasEl.classList.toggle("is-smart-tool", (inkTool === "smart" || inkTool === "math") && inkEnabled);
      inkCanvasEl.classList.toggle("is-stamp-pending", !!(inkTool === "math" && (inkPendingStamp || inkPendingLatex || inkFormulaPlaceMode) && inkEnabled));
    }
    updateInkActionButtons();
    updateInkToolHint();
  }

  function updateInkReaderBadge() {
    var showReader = !!(classroomSession && !classroomSlideApi);
    if (!showReader) {
      if (inkReaderEl) inkReaderEl.hidden = true;
      return;
    }
    if (!inkReaderEl) {
      inkReaderEl = document.createElement("span");
      inkReaderEl.className = "np-cm-ink-reader";
      inkReaderEl.setAttribute("data-cm-ink-reader", "true");
      inkReaderEl.innerHTML = '<span class="np-cm-ink-reader-dot"></span><span>Teacher notes</span>';
      if (inkChromeHost) inkChromeHost.appendChild(inkReaderEl);
    }
    inkReaderEl.hidden = !(inkStrokes.length > 0 || (classroomSession && classroomSession.ink_updated_at));
  }

  function updateInkDock() {
    updateInkReaderBadge();
    if (!isInkTeacher()) {
      if (inkDockEl) {
        inkDockEl.innerHTML = "";
        inkDockEl.removeAttribute("data-cm-ink-bound");
        inkDockEl.removeAttribute("data-cm-ink-version");
      }
      if (inkRailHost) inkRailHost.hidden = true;
      if (inkCompactSlot) inkCompactSlot.hidden = true;
      inkExpanded = false;
      inkCanDraw = false;
      stopLaserPoll();
      syncInkDockState();
      return;
    }
    inkCanDraw = true;
    if (inkCompactSlot) {
      inkCompactSlot.hidden = false;
      ensureInkCompactButton();
    }
    if (!inkRailHost) return;
    inkRailHost.hidden = false;
    if (!inkDockEl) {
      inkDockEl = document.createElement("div");
      inkDockEl.setAttribute("data-cm-ink-toolbar", "true");
      inkRailHost.appendChild(inkDockEl);
    }
    if (!inkDockEl.innerHTML || inkDockEl.getAttribute("data-cm-ink-version") !== INK_DOCK_VERSION) {
      inkDockEl.innerHTML = buildInkDockHtml();
      inkDockEl.setAttribute("data-cm-ink-version", INK_DOCK_VERSION);
      inkDockEl.removeAttribute("data-cm-ink-bound");
      bindInkDockEvents();
    }
    inkDockEl.querySelectorAll("[data-ink-tool]").forEach(function (b) {
      b.classList.toggle("is-active", b.getAttribute("data-ink-tool") === inkTool);
    });
    inkDockEl.querySelectorAll("[data-ink-color]").forEach(function (b) {
      b.classList.toggle("is-active", b.getAttribute("data-ink-color") === inkColor);
    });
    inkDockEl.querySelectorAll("[data-ink-size]").forEach(function (b) {
      b.classList.toggle("is-active", b.getAttribute("data-ink-size") === inkSizeKey);
    });
    syncInkDockState();
    updateInkActionButtons();
  }

  function resizeInkCanvas() {
    if (!inkCanvasEl || !slideEl || !inkCtx) return;
    inkDpr = window.devicePixelRatio || 1;
    var cssW = slideEl.offsetWidth;
    var cssH = slideEl.offsetHeight;
    if (!cssW || !cssH) return;
    var bufW = Math.max(1, Math.round(cssW * inkDpr));
    var bufH = Math.max(1, Math.round(cssH * inkDpr));
    inkCanvasEl.style.width = cssW + "px";
    inkCanvasEl.style.height = cssH + "px";
    if (inkCanvasEl.width !== bufW || inkCanvasEl.height !== bufH) {
      inkCanvasEl.width = bufW;
      inkCanvasEl.height = bufH;
      redrawInkCanvas();
    }
    resizeLaserCanvas();
  }

  function redrawInkCanvas() {
    if (!inkCtx || !inkCanvasEl) return;
    inkCtx.setTransform(1, 0, 0, 1, 0, 0);
    inkCtx.clearRect(0, 0, inkCanvasEl.width, inkCanvasEl.height);
    inkStrokes.forEach(function (stroke) { drawInkStroke(stroke); });
    if (inkCurrentStroke) drawInkStroke(inkCurrentStroke);
    renderLatexOverlays();
  }

  function drawInkStroke(stroke) {
    if (!inkCtx || !inkCanvasEl) return;
    var bw = inkCanvasEl.width;
    var bh = inkCanvasEl.height;
    var smart = inkSmart();
    if (smart && smart.drawStroke) {
      smart.drawStroke(inkCtx, stroke, bw, bh, inkDpr, { pro: true });
      return;
    }
    if (!stroke || !stroke.points || stroke.points.length < 2) return;
    var lw = (stroke.width || 4) * (inkDpr || 1);
    inkCtx.save();
    inkCtx.strokeStyle = stroke.color || "#ef4444";
    inkCtx.lineWidth = lw;
    inkCtx.globalAlpha = stroke.alpha == null ? 1 : stroke.alpha;
    inkCtx.lineCap = "round";
    inkCtx.lineJoin = "round";
    var points = stroke.points;
    inkCtx.beginPath();
    inkCtx.moveTo(points[0][0] * bw, points[0][1] * bh);
    for (var i = 1; i < points.length - 1; i++) {
      var mx = (points[i][0] + points[i + 1][0]) * 0.5 * bw;
      var my = (points[i][1] + points[i + 1][1]) * 0.5 * bh;
      inkCtx.quadraticCurveTo(points[i][0] * bw, points[i][1] * bh, mx, my);
    }
    var last = points[points.length - 1];
    inkCtx.lineTo(last[0] * bw, last[1] * bh);
    inkCtx.stroke();
    inkCtx.restore();
  }

  function strokeHitPoints(stroke) {
    var smart = inkSmart();
    if (smart && smart.sampleStrokePoints) return smart.sampleStrokePoints(stroke);
    return stroke && stroke.points ? stroke.points : [];
  }

  function eraseStrokesNearPoint(pt, radius) {
    if (!pt) return false;
    radius = radius == null ? inkEraserRadius() : radius;
    var before = inkStrokes.length;
    inkStrokes = inkStrokes.filter(function (stroke) {
      var pts = strokeHitPoints(stroke);
      if (!pts.length) return false;
      return !pts.some(function (p) {
        return Math.hypot(p[0] - pt[0], p[1] - pt[1]) <= radius;
      });
    });
    return inkStrokes.length !== before;
  }

  function inkPointFromEvent(e) {
    var rect = inkCanvasEl.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    return [
      Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)),
      Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)),
    ];
  }

  function bindInkPointerEvents() {
    if (!inkCanvasEl) return;
    inkCanvasEl.addEventListener("pointerenter", function () {
      if (inkTool === "laser" && inkEnabled && inkExpanded) {
        inkCanvasEl.classList.add("is-laser-hover");
      }
    });
    inkCanvasEl.addEventListener("pointerleave", function () {
      inkCanvasEl.classList.remove("is-laser-hover");
      if (!inkLaserDragging) hideLaserPreview();
    });
    inkCanvasEl.addEventListener("pointerdown", function (e) {
      if (!inkCanDraw || !isInkTeacher() || !inkEnabled) return;
      e.preventDefault();
      var pt = inkPointFromEvent(e);
      if (!pt) return;
      if (inkTool === "laser") {
        inkLaserDragging = true;
        pushLaserTrailPoint(pt);
        moveLaserPreview(pt);
        scheduleLaserPublish(true);
        inkCanvasEl.setPointerCapture(e.pointerId);
        return;
      }
      if (inkTool === "eraser") {
        inkDrawing = true;
        moveEraserRing(pt);
        if (eraseStrokesNearPoint(pt)) {
          redrawInkCanvas();
          scheduleInkSave();
          updateInkActionButtons();
        }
        inkCanvasEl.setPointerCapture(e.pointerId);
        return;
      }
      if (inkTool === "math" && inkPendingLatex) {
        placeLatexStamp(pt, inkPendingLatex);
        return;
      }
      if (inkTool === "math" && inkPendingStamp) {
        var smart = inkSmart();
        if (smart && smart.createStamp) {
          inkStrokes.push(smart.createStamp(inkPendingStamp, pt[0], pt[1], inkColor, 0.034));
          inkPendingStamp = null;
          if (inkDockEl) {
            inkDockEl.querySelectorAll("[data-ink-stamp]").forEach(function (b) {
              b.classList.remove("is-active");
            });
          }
          redrawInkCanvas();
          scheduleInkSave();
          updateInkActionButtons();
          updateInkToolHint();
          syncInkDockState();
        }
        return;
      }
      inkDrawing = true;
      hideEraserRing();
      var style = inkStrokeStyle(inkColor, inkTool);
      inkCurrentStroke = {
        points: [[pt[0], pt[1], Date.now()]],
        color: style.color,
        width: style.width,
        alpha: style.alpha,
        tool: style.tool,
      };
      setInkStatus("is-drawing", "Drawing…");
      inkCanvasEl.setPointerCapture(e.pointerId);
      redrawInkCanvas();
    });
    inkCanvasEl.addEventListener("pointermove", function (e) {
      if (!inkEnabled || !inkExpanded) return;
      var pt = inkPointFromEvent(e);
      if (inkTool === "laser") {
        if (!pt) return;
        moveLaserPreview(pt);
        if (inkLaserDragging) {
          e.preventDefault();
          pushLaserTrailPoint(pt);
          scheduleLaserPublish(true);
        }
        return;
      }
      hideLaserPreview();
      if (inkTool === "eraser" && pt) {
        moveEraserRing(pt);
      }
      if (!inkDrawing) return;
      e.preventDefault();
      if (!pt) return;
      if (inkTool === "eraser") {
        if (eraseStrokesNearPoint(pt)) {
          redrawInkCanvas();
          scheduleInkSave();
          updateInkActionButtons();
        }
        return;
      }
      if (!inkCurrentStroke) return;
      var pts = inkCurrentStroke.points;
      var last = pts[pts.length - 1];
      if (Math.hypot(pt[0] - last[0], pt[1] - last[1]) < 0.0012) return;
      pts.push([pt[0], pt[1], Date.now()]);
      redrawInkCanvas();
    });
    function finishStroke(e) {
      if (inkTool === "laser") {
        inkLaserDragging = false;
        if (inkLaserPreviewEl) inkLaserPreviewEl.classList.remove("is-drawing");
        try { inkCanvasEl.releasePointerCapture(e.pointerId); } catch (err) {}
        scheduleLaserPublish(false);
        return;
      }
      if (inkTool === "eraser") {
        hideEraserRing();
      }
      if (!inkDrawing) return;
      inkDrawing = false;
      if (inkTool !== "eraser" && inkCurrentStroke && inkCurrentStroke.points.length >= 2) {
        var smart = inkSmart();
        var finalized = inkCurrentStroke;
        if (smart && smart.finalizeStroke && inkTool === "smart") {
          finalized = smart.finalizeStroke(inkCurrentStroke, inkTool) || inkCurrentStroke;
          var toast = shapeToastLabel(finalized);
          if (toast) showInkShapeToast(toast);
        }
        inkStrokes.push(finalized);
        scheduleInkSave();
        updateInkActionButtons();
      }
      inkCurrentStroke = null;
      try { inkCanvasEl.releasePointerCapture(e.pointerId); } catch (err) {}
      redrawInkCanvas();
      updateInkReaderBadge();
      if (!inkSavePending) setInkStatus("is-synced", inkStrokes.length ? "Synced" : "Ready");
    }
    inkCanvasEl.addEventListener("pointerup", finishStroke);
    inkCanvasEl.addEventListener("pointercancel", finishStroke);
  }

  function scheduleInkSave() {
    if (!classroomInkApi || !classroomSlideApi || !classroomSession) return;
    inkSavePending = true;
    setInkStatus("is-pending", "Saving…");
    if (inkSaveTimer) window.clearTimeout(inkSaveTimer);
    inkSaveTimer = window.setTimeout(publishInkStrokes, 280);
  }

  function publishInkStrokes() {
    if (!classroomInkApi || !classroomSession) return;
    var slide = slides[idx];
    if (!slide) return;
    fetch(classroomInkApi, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slide_index: parseInt(slide.index, 10),
        strokes: inkStrokes,
      }),
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        inkSavePending = false;
        if (data && data.ok && data.updated_at) inkUpdatedAt = data.updated_at;
        setInkStatus("is-synced", inkStrokes.length ? "Synced · " + inkStrokes.length : "Ready");
      })
      .catch(function () {
        inkSavePending = false;
        setInkStatus("is-pending", "Sync retry…");
      });
  }

  function loadInkForCurrentSlide(force) {
    if (!classroomInkApi || !classroomSession) return;
    var slide = slides[idx];
    if (!slide) return;
    var slideIndex = parseInt(slide.index, 10);
    fetch(
      classroomInkApi + "?slide_index=" + encodeURIComponent(slideIndex),
      { credentials: "same-origin" }
    )
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.ok) return;
        if (!force && data.updated_at && data.updated_at === inkUpdatedAt) {
          if (data.laser && classroomSession) classroomSession.laser = data.laser;
          syncRemoteLaser(false);
          return;
        }
        inkUpdatedAt = data.updated_at || null;
        inkStrokes = Array.isArray(data.strokes) ? data.strokes : [];
        inkCurrentStroke = null;
        if (data.laser && classroomSession) classroomSession.laser = data.laser;
        ensureInkLayer();
        redrawInkCanvas();
        updateInkActionButtons();
        updateInkReaderBadge();
        syncRemoteLaser(false);
        clearLaserTrail(true);
      })
      .catch(function () {});
  }

  function syncInkFromSession(force) {
    if (!classroomSession) {
      if (!isInkTeacher()) {
        inkStrokes = [];
        inkUpdatedAt = null;
        if (inkLayerEl) inkLayerEl.hidden = true;
        clearLaserTrail(true);
        hideEraserRing();
        stopLaserPoll();
        return;
      }
      ensureInkLayer();
      if (inkLayerEl) inkLayerEl.hidden = false;
      updateInkDock();
      return;
    }
    ensureInkLayer();
    if (inkLayerEl) inkLayerEl.hidden = false;
    var remoteInkAt = classroomSession.ink_updated_at || null;
    if (force || remoteInkAt !== inkUpdatedAt) {
      loadInkForCurrentSlide(force);
    } else {
      syncRemoteLaser(force);
    }
    if (classroomSlideApi) {
      stopLaserPoll();
    } else {
      startLaserPoll();
      syncRemoteLaser(force);
    }
  }
  function loadClassroomSession() {
    if (!classroomActiveApi || classroomPollInFlight) return;
    classroomPollInFlight = true;
    fetch(classroomActiveApi, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.ok) {
          classroomPollFailures += 1;
          if (classroomPollFailures >= 10) setClassroomSession(null);
          return;
        }
        classroomPollFailures = 0;
        setClassroomSession(data.active ? (data.session || null) : null);
      })
      .catch(function () {
        classroomPollFailures += 1;
        if (classroomPollFailures >= 10) setClassroomSession(null);
      })
      .finally(function () {
        classroomPollInFlight = false;
      });
  }

  function publishCurrentClassroomSlide(attempt) {
    attempt = attempt || 0;
    if (!classroomSession || !classroomSlideApi || !slides[idx]) return;
    var slideIndex = parseInt(slides[idx].index, 10) || 1;
    if (lastPublishedClassroomSlide === slideIndex && attempt === 0) return;
    window.clearTimeout(classroomSlidePublishTimer);
    classroomSlidePublishTimer = window.setTimeout(function () {
      fetch(classroomSlideApi, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ slide_index: slideIndex }),
      })
        .then(function (r) {
          return r.json().catch(function () { return null; }).then(function (data) {
            if (!r.ok || !data || !data.ok) {
              throw new Error((data && data.error) || "Could not sync the class slide.");
            }
            lastPublishedClassroomSlide = slideIndex;
            if (data.slide_updated_at) {
              classroomSession.slide_updated_at = data.slide_updated_at;
              lastKnownSlideUpdatedAt = data.slide_updated_at;
            }
          });
        })
        .catch(function (err) {
          if (attempt < 2) {
            window.setTimeout(function () { publishCurrentClassroomSlide(attempt + 1); }, 400 * (attempt + 1));
            return;
          }
          showClassroomResponseNotice((err && err.message) || "Could not sync the class slide.", true);
        });
    }, attempt > 0 ? 0 : 220);
  }

  function submitClassroomResponse(payload, attempt) {
    attempt = attempt || 0;
    if (!classroomSession || !classroomResponseApi) return;
    fetch(classroomResponseApi, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json().catch(function () { return null; }).then(function (data) {
          if (!r.ok || !data || !data.ok) {
            throw new Error((data && data.error) || "Live response was not saved.");
          }
          showClassroomResponseNotice("Saved to live classroom.", false);
        });
      })
      .catch(function (err) {
        if (attempt < 1) {
          window.setTimeout(function () { submitClassroomResponse(payload, attempt + 1); }, 500);
          return;
        }
        showClassroomResponseNotice((err && err.message) || "Live response was not saved. Ask the teacher to refresh the class.", true);
      });
  }

  function showClassroomResponseNotice(message, isError) {
    var notice = root.querySelector("[data-cm-classroom-notice]");
    if (!notice) {
      notice = document.createElement("div");
      notice.setAttribute("data-cm-classroom-notice", "true");
      notice.className = "cm-classroom-notice";
      root.appendChild(notice);
    }
    notice.textContent = message;
    notice.classList.toggle("is-error", !!isError);
    notice.classList.add("is-visible");
    window.clearTimeout(notice._hideTimer);
    notice._hideTimer = window.setTimeout(function () {
      notice.classList.remove("is-visible");
    }, isError ? 7000 : 2200);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  var livePopoverOpen = false;
  var liveSections = { dist: true, students: true, overview: false, missing: true };

  function liveSection(key, title, badge, inner) {
    var open = !!liveSections[key];
    return (
      '<section class="np-cm-live-sec' + (open ? " is-open" : "") + '">' +
      '<button type="button" class="np-cm-live-sec-head" data-cm-live-sec="' + key + '">' +
      '<span class="np-cm-live-sec-title">' + title + '</span>' +
      (badge ? '<span class="np-cm-live-sec-badge">' + badge + '</span>' : "") +
      '<span class="np-cm-live-sec-chev" aria-hidden="true"></span>' +
      '</button>' +
      '<div class="np-cm-live-sec-body"' + (open ? "" : " hidden") + '>' + inner + '</div>' +
      '</section>'
    );
  }

  function renderLiveResults(slide) {
    if (!liveResultsEl || !classroomSummaryApi || !slide) return;
    var isQuestion = slide.kind === "question" || slide.kind === "practice" || slide.kind === "example";
    if (!isQuestion) {
      liveResultsEl.hidden = true;
      return;
    }
    var summary = classroomSummary || {};
    var session = summary.session || null;
    if (!session) {
      liveResultsEl.hidden = false;
      liveResultsEl.innerHTML =
        '<button type="button" class="np-cm-live-chip" data-cm-live-open><span>Live</span><strong>Start</strong></button>' +
        '<div class="np-cm-live-popover" data-cm-live-popover' + (livePopoverOpen ? "" : " hidden") + '>' +
        '<div class="np-cm-live-popover-head"><strong>Live Results</strong><button type="button" data-cm-live-close>×</button></div>' +
        "<p>Start a live class to see this slide's accuracy here while students answer.</p>" +
        (classroomStartApi ? '<button type="button" class="np-cm-live-btn" data-cm-start-live>Start live class</button>' : "") +
        '</div>';
      bindLivePopover();
      var startBtn = liveResultsEl.querySelector("[data-cm-start-live]");
      if (startBtn) {
        startBtn.onclick = function () {
          fetch(classroomStartApi, { method: "POST", credentials: "same-origin" })
            .then(function () {
              loadClassroomSession();
              return loadClassroomSummary();
            })
            .catch(function () {});
        };
      }
      return;
    }
    var q = null;
    (summary.questions || []).some(function (item) {
      if (parseInt(item.slide_index, 10) === parseInt(slide.index, 10)) {
        q = item;
        return true;
      }
      return false;
    });
    if (!q) {
      liveResultsEl.hidden = true;
      return;
    }
    var submitted = q.submitted || 0;
    var accuracy = q.accuracy == null ? "—" : q.accuracy + "%";
    var rosterCount = summary.roster_count || 0;
    var completionPct = q.completion == null ? 0 : q.completion;
    var completion = q.completion == null ? "—" : q.completion + "%";
    var missingList = q.missing_students || [];
    var missingCount = missingList.length;
    var readyText = q.teach_ready ? "Ready to teach" : (q.almost_ready ? "Almost ready" : "Keep working");
    var readyClass = q.teach_ready ? "is-ready" : (q.almost_ready ? "is-almost" : "is-waiting");

    var correctAnswer = "";
    (q.responses || []).some(function (r) {
      if (r.correct_answer) { correctAnswer = String(r.correct_answer).trim(); return true; }
      return false;
    });

    var choiceCounts = q.choice_counts || {};
    var choiceBars = Object.keys(choiceCounts).sort().map(function (choice) {
      var count = choiceCounts[choice] || 0;
      var pct = submitted ? Math.round(100 * count / submitted) : 0;
      var isAns = correctAnswer && choice.trim() === correctAnswer;
      return '<li class="' + (isAns ? "is-correct-bar" : "") + '">' +
        '<span>' + escapeHtml(choice) + (isAns ? ' <i>✓</i>' : '') + '</span>' +
        '<b style="width:' + pct + '%"></b><em>' + escapeHtml(count) + '</em></li>';
    }).join("");
    if (!choiceBars) choiceBars = '<li class="is-empty"><span>No choices yet</span></li>';

    var rows = (q.responses || []).slice().sort(function (a, b) {
      if (!!a.is_correct !== !!b.is_correct) return a.is_correct ? 1 : -1;
      return String(a.username).toLowerCase() < String(b.username).toLowerCase() ? -1 : 1;
    }).map(function (r) {
      return '<li class="' + (r.is_correct ? "is-correct" : "is-wrong") + '">' +
        '<span class="np-cm-live-row-name">' + escapeHtml(r.username) + '</span>' +
        '<strong>' + escapeHtml(r.selected_answer || "—") + '</strong>' +
        '<i>' + (r.is_correct ? "✓" : "✗") + '</i>' +
        '</li>';
    }).join("");
    if (!rows) rows = '<li class="is-empty"><span>Waiting for students...</span></li>';

    var breakdown = (summary.report && summary.report.student_breakdown) || [];
    var overviewRows = breakdown.map(function (st) {
      var acc = st.accuracy == null ? null : st.accuracy;
      var tone = !st.submitted ? "is-idle" : acc >= 80 ? "is-good" : acc >= 50 ? "is-warn" : "is-risk";
      var accText = acc == null ? "—" : acc + "%";
      var wrongCount = (st.wrong_questions || []).length;
      return '<li class="' + tone + '">' +
        '<span class="np-cm-live-row-name">' + escapeHtml(st.username) + '</span>' +
        '<span class="np-cm-live-ov-meta">' + escapeHtml(st.submitted || 0) + ' done' +
        (wrongCount ? ' · ' + escapeHtml(wrongCount) + ' wrong' : '') + '</span>' +
        '<strong>' + escapeHtml(accText) + '</strong>' +
        '</li>';
    }).join("");
    if (!overviewRows) overviewRows = '<li class="is-empty"><span>No students yet</span></li>';

    var missing = missingList.slice(0, 16).map(function (r) {
      return '<span>' + escapeHtml(r.username) + '</span>';
    }).join("");
    if (missingList.length > 16) {
      missing += '<span>+' + escapeHtml(missingList.length - 16) + ' more</span>';
    }
    if (!missing) missing = '<span class="is-none">Everyone submitted 🎉</span>';

    liveResultsEl.hidden = false;
    liveResultsEl.innerHTML =
      '<button type="button" class="np-cm-live-chip" data-cm-live-open>' +
      '<i class="np-cm-live-dot" aria-hidden="true"></i>' +
      '<span>Live</span><strong>' + escapeHtml(accuracy) + '</strong><em>' + escapeHtml(submitted) + '/' + escapeHtml(rosterCount || submitted) + '</em>' +
      '</button>' +
      '<div class="np-cm-live-popover" data-cm-live-popover' + (livePopoverOpen ? "" : " hidden") + '>' +
      '<div class="np-cm-live-popover-head">' +
      '<div class="np-cm-live-head-copy"><i class="np-cm-live-dot" aria-hidden="true"></i>' +
      '<strong>Slide ' + escapeHtml(slide.index) + '</strong><span>Live Results</span></div>' +
      '<button type="button" data-cm-live-close>×</button></div>' +
      '<div class="np-cm-live-readiness ' + readyClass + '">' +
      '<div class="np-cm-live-readiness-copy"><strong>' + escapeHtml(readyText) + '</strong>' +
      '<span>' + escapeHtml(missingCount) + ' not submitted · ' + escapeHtml(completion) + ' complete</span></div>' +
      '<div class="np-cm-live-progress"><b style="width:' + completionPct + '%"></b></div>' +
      '</div>' +
      '<div class="np-cm-live-stats">' +
      '<div><b>' + escapeHtml(accuracy) + '</b><span>accuracy</span></div>' +
      '<div><b>' + escapeHtml(q.correct || 0) + '/' + escapeHtml(submitted) + '</b><span>correct</span></div>' +
      '<div><b>' + escapeHtml(submitted) + '/' + escapeHtml(rosterCount || submitted) + '</b><span>submitted</span></div>' +
      '<div><b>' + escapeHtml(missingCount) + '</b><span>missing</span></div>' +
      '</div>' +
      liveSection("dist", "Choice distribution", correctAnswer ? "Answer " + escapeHtml(correctAnswer) : "", '<ul class="np-cm-live-bars">' + choiceBars + '</ul>') +
      liveSection("students", "This question", escapeHtml(submitted) + " response" + (submitted === 1 ? "" : "s"), '<ul class="np-cm-live-list">' + rows + '</ul>') +
      liveSection("overview", "Class overview", escapeHtml(breakdown.length) + " student" + (breakdown.length === 1 ? "" : "s"), '<ul class="np-cm-live-list np-cm-live-overview">' + overviewRows + '</ul>') +
      liveSection("missing", "Not submitted", escapeHtml(missingCount) || "", '<div class="np-cm-live-missing-chips">' + missing + '</div>') +
      '</div>';
    bindLivePopover();
  }

  function bindLivePopover() {
    if (!liveResultsEl) return;
    var openBtn = liveResultsEl.querySelector("[data-cm-live-open]");
    var popover = liveResultsEl.querySelector("[data-cm-live-popover]");
    var closeBtn = liveResultsEl.querySelector("[data-cm-live-close]");
    if (!openBtn || !popover) return;
    openBtn.onclick = function () {
      livePopoverOpen = popover.hidden;
      popover.hidden = !popover.hidden;
    };
    if (closeBtn) {
      closeBtn.onclick = function () {
        livePopoverOpen = false;
        popover.hidden = true;
      };
    }
    liveResultsEl.querySelectorAll("[data-cm-live-sec]").forEach(function (btn) {
      btn.onclick = function () {
        var key = btn.getAttribute("data-cm-live-sec");
        liveSections[key] = !liveSections[key];
        var sec = btn.closest(".np-cm-live-sec");
        var body = sec ? sec.querySelector(".np-cm-live-sec-body") : null;
        if (sec) sec.classList.toggle("is-open", liveSections[key]);
        if (body) body.hidden = !liveSections[key];
      };
    });
  }

  function loadClassroomSummary() {
    if (!classroomSummaryApi) return Promise.resolve();
    return fetch(classroomSummaryApi, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        classroomSummary = data && data.ok ? data : null;
        renderLiveResults(slides[idx]);
      })
      .catch(function () {});
  }

  function saveProgress() {
    var slide = slides[idx];
    if (slide) {
      progress.last_slide_index = slide.index;
      progress.last_active_at = Date.now();
    }
    try {
      localStorage.setItem(storageKey, JSON.stringify(progress));
    } catch (e) {}
    saveGlobalLastVisit();
    updateStudyStat();
    updateMastery();
    syncOutlineDone();
    updateKnowledgeMap();
    scheduleProgressSync();
  }

  function saveCheckpointRecord(rec) {
    try {
      localStorage.setItem(checkpointKey, JSON.stringify(rec));
    } catch (e) {}
    updateMastery();
    updateKnowledgeMap();
    scheduleProgressSync();
  }

  function loadCheckpointRecord() {
    try {
      var raw = localStorage.getItem(checkpointKey);
      return raw ? JSON.parse(raw) : { best_score: 0, best_total: 0, last_run: null, missed: [] };
    } catch (e) {
      return { best_score: 0, best_total: 0, last_run: null, missed: [] };
    }
  }

  function lessonHref(slug) {
    if (!slug) return null;
    var path = window.location.pathname.replace(/\/[^/]+\/?$/, "/" + slug);
    return path;
  }

  function shuffleArray(arr) {
    var copy = arr.slice();
    for (var i = copy.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var tmp = copy[i];
      copy[i] = copy[j];
      copy[j] = tmp;
    }
    return copy;
  }

  function buildCheckpointMcqHtml(item) {
    var buttons = (item.choices || []).map(function (c) {
      return (
        '<button type="button" class="cm-mcq-choice" data-choice="' + c.letter + '">' +
        '<span class="cm-mcq-letter">' + c.letter + '</span>' +
        '<span class="cm-mcq-text">' + c.text + "</span></button>"
      );
    }).join("");
    return (
      '<div class="cm-mcq-interactive cm-mcq-interactive--checkpoint" data-cm-mcq data-cm-correct="' +
      item.correct +
      '">' +
      '<p class="cm-mcq-prompt">Select your answer, then check.</p>' +
      '<div class="cm-mcq-grid">' +
      buttons +
      "</div>" +
      '<div class="cm-mcq-actions">' +
      '<button type="button" class="cm-mcq-check" data-cm-check-mcq disabled>Check answer</button>' +
      "</div></div>"
    );
  }

  function initCheckpointMcq(mcq, onDone) {
    var selected = null;
    var choices = Array.prototype.slice.call(mcq.querySelectorAll(".cm-mcq-choice"));
    var checkBtn = mcq.querySelector("[data-cm-check-mcq]");
    choices.forEach(function (btn) {
      btn.onclick = function () {
        if (mcq.classList.contains("is-checked")) return;
        choices.forEach(function (c) { c.classList.remove("is-selected"); });
        btn.classList.add("is-selected");
        selected = btn.getAttribute("data-choice");
        if (checkBtn) checkBtn.disabled = false;
      };
    });
    if (checkBtn) {
      checkBtn.onclick = function () {
        if (!selected || mcq.classList.contains("is-checked")) return;
        var correct = mcq.getAttribute("data-cm-correct");
        var isCorrect = correct && selected === correct;
        choices.forEach(function (c) {
          c.classList.add("is-locked");
          if (!correct) return;
          var letter = c.getAttribute("data-choice");
          if (letter === correct) c.classList.add("is-correct");
          else if (letter === selected) c.classList.add("is-incorrect");
        });
        mcq.classList.add("is-checked");
        if (isCorrect) mcq.classList.add("is-correct-answer");
        else mcq.classList.add("is-wrong-answer");
        checkBtn.disabled = true;
        if (onDone) onDone(isCorrect, selected, correct);
      };
    }
  }

  function renderCheckpointQuestion() {
    if (!checkpointEl) return;
    var body = checkpointEl.querySelector("[data-cm-checkpoint-body]");
    var foot = checkpointEl.querySelector("[data-cm-checkpoint-foot]");
    var results = checkpointEl.querySelector("[data-cm-checkpoint-results]");
    var counter = checkpointEl.querySelector("[data-cm-checkpoint-counter]");
    var bar = checkpointEl.querySelector("[data-cm-checkpoint-bar]");
    var sub = checkpointEl.querySelector("[data-cm-checkpoint-sub]");
    var nextBtn = checkpointEl.querySelector("[data-cm-checkpoint-next]");
    if (results) results.hidden = true;
    if (foot) foot.hidden = false;
    if (nextBtn) nextBtn.hidden = true;

    var pos = checkpointState.cursor;
    var total = checkpointState.order.length;
    if (pos >= total) {
      showCheckpointResults();
      return;
    }
    var item = checkpointState.order[pos];
    if (!body || !item) return;

    body.innerHTML =
      '<p class="np-cm-checkpoint-section">' + (item.section || "Practice") + "</p>" +
      '<h3 class="np-cm-checkpoint-qtitle">' + item.title + "</h3>" +
      item.stem_html +
      buildCheckpointMcqHtml(item);

    if (counter) counter.textContent = (pos + 1) + " / " + total;
    if (bar) bar.style.width = String(Math.round((pos / total) * 100)) + "%";
    if (sub) {
      sub.textContent = "Drawn from this lesson — " + total + " questions from your slides.";
    }

    var mcq = body.querySelector("[data-cm-mcq]");
    initCheckpointMcq(mcq, function (isCorrect) {
      checkpointState.results.push({
        slide_index: item.slide_index,
        title: item.title,
        correct: isCorrect,
        answer_index: item.answer_index
      });
      if (isCorrect && progress.done.indexOf(item.slide_index) === -1) {
        markDone(item.slide_index);
      }
      if (nextBtn) {
        nextBtn.hidden = false;
        nextBtn.textContent = pos + 1 >= total - 1 ? "See results" : "Next question →";
      }
      if (window.MathJax && window.MathJax.typesetPromise) {
        window.MathJax.typesetPromise([body]).catch(function () {});
      }
    });

    if (window.MathJax && window.MathJax.typesetPromise) {
      window.MathJax.typesetPromise([body]).catch(function () {});
    }
    var dialog = checkpointEl.querySelector(".np-cm-checkpoint-dialog");
    if (dialog) dialog.scrollTop = 0;
  }

  function showCheckpointResults() {
    if (!checkpointEl) return;
    var body = checkpointEl.querySelector("[data-cm-checkpoint-body]");
    var foot = checkpointEl.querySelector("[data-cm-checkpoint-foot]");
    var results = checkpointEl.querySelector("[data-cm-checkpoint-results]");
    var bar = checkpointEl.querySelector("[data-cm-checkpoint-bar]");
    var counter = checkpointEl.querySelector("[data-cm-checkpoint-counter]");
    var total = checkpointState.results.length;
    var score = checkpointState.results.filter(function (r) { return r.correct; }).length;
    var pct = total ? Math.round(100 * score / total) : 0;
    if (body) body.innerHTML = "";
    if (foot) foot.hidden = true;
    if (bar) bar.style.width = "100%";
    if (counter) counter.textContent = score + " / " + total;

    var rec = loadCheckpointRecord();
    if (score > rec.best_score || !rec.best_total) {
      rec.best_score = score;
      rec.best_total = total;
    }
    rec.last_run = { score: score, total: total, pct: pct, at: Date.now() };
    rec.missed = checkpointState.results.filter(function (r) { return !r.correct; }).map(function (r) {
      return { slide_index: r.slide_index, title: r.title, answer_index: r.answer_index };
    });
    saveCheckpointRecord(rec);

    var missedHtml = rec.missed.length
      ? rec.missed.map(function (m) {
          return (
            '<li><button type="button" class="np-cm-checkpoint-miss" data-cm-goto="' +
            m.slide_index +
            '">' +
            m.title +
            " · review slide</button></li>"
          );
        }).join("")
      : "<li>Perfect — every concept checked out.</li>";

    var nextLesson = lessonMeta.next_lesson_slug;
    var nextHtml = nextLesson
      ? '<a class="np-cm-checkpoint-btn np-cm-checkpoint-btn--accent" href="' +
        lessonHref(nextLesson) +
        '">Next lesson →</a>'
      : "";

    if (results) {
      results.hidden = false;
      results.innerHTML =
        '<div class="np-cm-checkpoint-score">' +
        '<span class="np-cm-checkpoint-score-num">' +
        pct +
        "%</span>" +
        "<p>" +
        score +
        " of " +
        total +
        " correct on this run.</p>" +
        (rec.best_score > score
          ? "<p class=\"np-cm-checkpoint-best\">Best: " + rec.best_score + "/" + rec.best_total + "</p>"
          : "<p class=\"np-cm-checkpoint-best\">New personal best!</p>") +
        "</div>" +
        '<div class="np-cm-checkpoint-review">' +
        "<strong>Review if needed</strong><ul>" +
        missedHtml +
        "</ul></div>" +
        '<div class="np-cm-checkpoint-actions">' +
        '<button type="button" class="np-cm-checkpoint-btn np-cm-checkpoint-btn--ghost" data-cm-checkpoint-retry>Try again</button>' +
        '<button type="button" class="np-cm-checkpoint-btn" data-cm-checkpoint-close>Back to slides</button>' +
        nextHtml +
        "</div>";
      results.querySelectorAll("[data-cm-goto]").forEach(function (btn) {
        btn.onclick = function () {
          closeCheckpoint();
          goToSlideNumber(parseInt(btn.getAttribute("data-cm-goto"), 10));
        };
      });
      var retryBtn = results.querySelector("[data-cm-checkpoint-retry]");
      if (retryBtn) retryBtn.onclick = function () { openCheckpoint(); };
      results.querySelectorAll("[data-cm-checkpoint-close]").forEach(function (btn) {
        btn.onclick = closeCheckpoint;
      });
    }
  }

  function closeCheckpoint() {
    if (!checkpointEl) return;
    checkpointState.active = false;
    checkpointState.cursor = 0;
    checkpointState.results = [];
    checkpointEl.hidden = true;
    checkpointEl.setAttribute("aria-hidden", "true");
    checkpointEl.classList.remove("is-open");
    document.body.classList.remove("np-cm-checkpoint-open");
    var results = checkpointEl.querySelector("[data-cm-checkpoint-results]");
    var body = checkpointEl.querySelector("[data-cm-checkpoint-body]");
    var foot = checkpointEl.querySelector("[data-cm-checkpoint-foot]");
    if (results) {
      results.hidden = true;
      results.innerHTML = "";
    }
    if (body) body.innerHTML = "";
    if (foot) foot.hidden = false;
  }

  function openCheckpoint() {
    if (!checkpointEl || !checkpointItems.length) return;
    checkpointState.order = shuffleArray(checkpointItems);
    checkpointState.cursor = 0;
    checkpointState.results = [];
    checkpointState.active = true;
    checkpointEl.hidden = false;
    checkpointEl.setAttribute("aria-hidden", "false");
    checkpointEl.classList.add("is-open");
    document.body.classList.add("np-cm-checkpoint-open");
    var results = checkpointEl.querySelector("[data-cm-checkpoint-results]");
    if (results) {
      results.hidden = true;
      results.innerHTML = "";
    }
    renderCheckpointQuestion();
  }

  function sectionMastery(section) {
    var items = section.items || [];
    if (!items.length) return 0;
    var done = 0;
    items.forEach(function (item) {
      if (progress.done.indexOf(item.index) !== -1) done += 1;
      else if ((progress.viewed || []).indexOf(item.index) !== -1) done += 0.4;
    });
    return Math.round(100 * done / items.length);
  }

  function updateKnowledgeMap() {
    if (!knowledgeListEl || !knowledgeMap.length) return;
    knowledgeListEl.innerHTML = knowledgeMap.map(function (section) {
      var pct = sectionMastery(section);
      return (
        '<li class="np-cm-knowledge-item">' +
        '<button type="button" class="np-cm-knowledge-btn" data-cm-goto-section="' +
        section.start_index +
        '">' +
        '<span class="np-cm-knowledge-name">' +
        section.title +
        "</span>" +
        '<span class="np-cm-knowledge-pct">' +
        pct +
        "%</span>" +
        '<span class="np-cm-knowledge-bar"><i style="width:' +
        pct +
        '%"></i></span>' +
        "</button></li>"
      );
    }).join("");
    knowledgeListEl.querySelectorAll("[data-cm-goto-section]").forEach(function (btn) {
      btn.onclick = function () {
        goToSlideNumber(parseInt(btn.getAttribute("data-cm-goto-section"), 10));
        if (window.matchMedia && window.matchMedia("(max-width: 1100px)").matches) {
          setOutlineOpen(false);
        }
      };
    });
  }

  function injectClosingCheckpointCta() {
    injectClosingNextLesson();
    if (!checkpointItems.length || bodyEl.querySelector("[data-cm-lesson-check-cta]")) return;
    var wrap = document.createElement("div");
    wrap.className = "cm-lesson-check-cta";
    wrap.setAttribute("data-cm-lesson-check-cta", "");
    wrap.innerHTML =
      '<div class="cm-lesson-check-cta-copy">' +
      "<strong>Ready to lock in this lesson?</strong>" +
      "<span>Take a " +
      checkpointItems.length +
      "-question check built from today's slides.</span></div>" +
      '<button type="button" class="cm-lesson-check-cta-btn" data-cm-open-checkpoint-inline>Start lesson check</button>';
    bodyEl.appendChild(wrap);
    var btn = wrap.querySelector("[data-cm-open-checkpoint-inline]");
    if (btn) btn.onclick = openCheckpoint;
  }

  function injectClosingNextLesson() {
    var nextSlug = lessonMeta.next_lesson_slug;
    if (!nextSlug || bodyEl.querySelector("[data-cm-next-lesson-cta]")) return;
    var wrap = document.createElement("div");
    wrap.className = "cm-next-lesson-cta";
    wrap.setAttribute("data-cm-next-lesson-cta", "");
    wrap.innerHTML =
      '<div class="cm-next-lesson-cta-copy">' +
      "<strong>Finished this lesson?</strong>" +
      "<span>Continue to the next deck in your unit path.</span></div>" +
      '<a class="cm-next-lesson-cta-btn" href="' +
      lessonHref(nextSlug) +
      '">Next lesson →</a>';
    bodyEl.appendChild(wrap);
  }

  function injectIntroOverview() {
    if (bodyEl.querySelector("[data-cm-intro-overview]")) return;
    var sectionCount = knowledgeMap.length;
    var challengeCount = lessonMeta.interactive_count || checkpointItems.length || lessonMeta.checkpoint_count || 0;
    var checkCount = checkpointItems.length || lessonMeta.checkpoint_count || 0;
    var wrap = document.createElement("div");
    wrap.className = "cm-intro-overview";
    wrap.setAttribute("data-cm-intro-overview", "");
    wrap.innerHTML =
      '<p class="cm-intro-overview-kicker">Lesson overview</p>' +
      '<ul class="cm-intro-overview-stats">' +
      (sectionCount ? "<li><strong>" + sectionCount + "</strong> sections</li>" : "") +
      (challengeCount ? "<li><strong>" + challengeCount + "</strong> challenges</li>" : "") +
      (checkCount ? "<li><strong>" + checkCount + "</strong> lesson-check questions</li>" : "") +
      "<li><strong>" + (lessonMeta.slide_count || slides.length) + "</strong> slides</li>" +
      "</ul>" +
      (checkCount
        ? '<button type="button" class="cm-intro-overview-check" data-cm-open-checkpoint-inline>Preview lesson check</button>'
        : "");
    bodyEl.appendChild(wrap);
    var checkBtn = wrap.querySelector("[data-cm-open-checkpoint-inline]");
    if (checkBtn && checkpointItems.length) checkBtn.onclick = openCheckpoint;
  }

  function loadStudyMode() {
    try {
      return localStorage.getItem(studyKey) !== "off";
    } catch (e) {
      return true;
    }
  }

  function saveStudyMode() {
    try {
      localStorage.setItem(studyKey, studyMode ? "on" : "off");
    } catch (e) {}
    root.classList.toggle("is-study-off", !studyMode);
    if (studyToggle) {
      studyToggle.setAttribute("aria-pressed", studyMode ? "true" : "false");
      studyToggle.classList.toggle("is-active", studyMode);
    }
    scheduleProgressSync();
  }

  function markViewed(slideIndex) {
    if (!progress.viewed) progress.viewed = [];
    if (progress.viewed.indexOf(slideIndex) === -1) {
      progress.viewed.push(slideIndex);
      saveProgress();
    }
  }

  function markDone(slideIndex) {
    if (progress.done.indexOf(slideIndex) === -1) {
      progress.done.push(slideIndex);
      saveProgress();
    }
  }

  function slideByIndex(n) {
    for (var i = 0; i < slides.length; i++) {
      if (slides[i].index === n) return slides[i];
    }
    return null;
  }

  function goToIndex(targetIdx, options) {
    if (targetIdx >= 0 && targetIdx < slides.length) {
      idx = targetIdx;
      render();
    }
  }

  function goToSlideNumber(num, options) {
    for (var i = 0; i < slides.length; i++) {
      if (slides[i].index === num) {
        goToIndex(i, options);
        return;
      }
    }
  }

  function findNextChallenge(fromIdx) {
    for (var i = fromIdx + 1; i < slides.length; i++) {
      var k = slides[i].kind;
      if (k === "question" || k === "practice" || k === "example") return slides[i];
    }
    return null;
  }

  function setOutlineOpen(open) {
    root.classList.toggle("is-path-open", open);
    outlineToggles.forEach(function (btn) {
      btn.setAttribute("aria-pressed", open ? "true" : "false");
    });
  }

  function applyFilter(filter) {
    activeFilter = filter;
    filterBtns.forEach(function (btn) {
      var on = btn.getAttribute("data-cm-filter") === filter;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    outlineItems.forEach(function (item) {
      var group = item.getAttribute("data-cm-group") || "learn";
      var kind = item.getAttribute("data-cm-kind") || "";
      var show = filter === "all";
      if (!show && filter === "learn") {
        show = group === "learn" && kind !== "section";
      }
      if (!show && filter === "practice") {
        show = group === "practice";
      }
      item.classList.toggle("is-filtered-out", !show);
    });
  }

  function updateStudyStat() {
    if (!studyStatEl) return;
    var total = slides.filter(function (s) {
      return s.interactive || s.kind === "question" || s.kind === "practice" || s.kind === "example";
    }).length;
    var done = progress.done.filter(function (n) {
      var s = slideByIndex(n);
      return s && (s.interactive || s.kind === "question" || s.kind === "practice" || s.kind === "example");
    }).length;
    studyStatEl.textContent = done + " / " + total + " challenges";
  }

  function updateMastery() {
    var total = slides.filter(function (s) { return s.kind !== "section"; }).length;
    if (!total) return;
    var viewed = (progress.viewed || []).filter(function (n) {
      var s = slideByIndex(n);
      return s && s.kind !== "section";
    }).length;
    var done = progress.done.length;
    var slidePct = Math.min(100, Math.round(100 * (viewed * 0.35 + done * 0.45) / total));
    var cpRec = loadCheckpointRecord();
    var cpPct = cpRec.last_run ? cpRec.last_run.pct : (cpRec.best_total ? Math.round(100 * cpRec.best_score / cpRec.best_total) : 0);
    var pct = checkpointItems.length
      ? Math.min(100, Math.round(slidePct * 0.65 + cpPct * 0.35))
      : slidePct;
    if (masteryPctEl) masteryPctEl.textContent = pct + "%";
    if (masteryRingEl) {
      var circ = 2 * Math.PI * 18;
      masteryRingEl.style.strokeDasharray = circ;
      masteryRingEl.style.strokeDashoffset = circ - (pct / 100) * circ;
    }
  }

  function syncOutlineDone() {
    outlineBtns.forEach(function (btn) {
      var n = parseInt(btn.getAttribute("data-cm-index"), 10);
      var done = progress.done.indexOf(n) !== -1;
      var viewed = (progress.viewed || []).indexOf(n) !== -1;
      btn.classList.toggle("is-done", done);
      btn.classList.toggle("is-viewed", viewed && !done);
    });
  }

  function loadFocusMode() {
    try {
      return sessionStorage.getItem(focusKey) === "1";
    } catch (e) {
      return false;
    }
  }

  function saveFocusMode(on) {
    try {
      sessionStorage.setItem(focusKey, on ? "1" : "0");
    } catch (e) {}
  }

  function getFullscreenElement() {
    return document.fullscreenElement || document.webkitFullscreenElement || document.msFullscreenElement || null;
  }

  function requestProjectionFullscreen() {
    var target = document.documentElement || root;
    var request =
      target.requestFullscreen ||
      target.webkitRequestFullscreen ||
      target.msRequestFullscreen;
    if (!request) return;
    try {
      var result = request.call(target);
      if (result && result.catch) result.catch(function () {});
    } catch (e) {}
  }

  function exitProjectionFullscreen() {
    if (!getFullscreenElement()) return;
    var exit =
      document.exitFullscreen ||
      document.webkitExitFullscreen ||
      document.msExitFullscreen;
    if (!exit) return;
    try {
      var result = exit.call(document);
      if (result && result.catch) result.catch(function () {});
    } catch (e) {}
  }

  function setFocusMode(on, options) {
    options = options || {};
    if (on) {
      pathOpenBeforeFocus = root.classList.contains("is-path-open");
      setOutlineOpen(false);
    } else if (pathOpenBeforeFocus) {
      setOutlineOpen(true);
    }
    root.classList.toggle("is-focus-mode", on);
    document.documentElement.classList.toggle("is-cm-projector", on);
    document.body.classList.toggle("is-cm-projector", on);
    if (focusToggle) {
      focusToggle.classList.toggle("is-active", on);
      focusToggle.setAttribute("aria-pressed", on ? "true" : "false");
      var label = focusToggle.querySelector(".np-cm-btn-label");
      if (label) label.textContent = on ? "Exit projector" : "Projector";
    }
    if (focusInlineExit) {
      focusInlineExit.hidden = !on;
    }
    if (coachEl && on) {
      coachEl.hidden = true;
    } else if (!on && slides[idx]) {
      updateCoach(slides[idx]);
    }
    if (options.fullscreen !== false) {
      if (on) requestProjectionFullscreen();
      else exitProjectionFullscreen();
    }
    saveFocusMode(on);
    if (on && isInkTeacher()) {
      openInkForTeaching({ tool: "pen", sizeKey: "s" });
    }
    if (on) window.requestAnimationFrame(resizeInkCanvas);
  }

  function exitFocusMode() {
    if (root.classList.contains("is-focus-mode")) {
      setFocusMode(false);
    }
  }

  function toggleFocusMode() {
    setFocusMode(!root.classList.contains("is-focus-mode"));
  }

  function isCanvasSlide(slide) {
    var kind = slide.kind || "lesson";
    return kind === "section" || kind === "closing" || kind === "intro" || kind === "content";
  }

  function updateCoach(slide) {
    var kind = slide.kind || "lesson";
    if (coachEl) {
      coachEl.hidden = isCanvasSlide(slide);
    }
    if (coachTipEl) {
      coachTipEl.textContent = slide.study_tip || "Work through each slide at your own pace.";
    }
    if (hintBtn) {
      if (slide.strategy_hint && studyMode && (kind === "question" || kind === "practice" || kind === "example")) {
        hintBtn.hidden = false;
        hintBtn.setAttribute("data-hint", slide.strategy_hint);
      } else {
        hintBtn.hidden = true;
      }
    }
    if (hintPanel) {
      hintPanel.hidden = true;
      hintPanel.textContent = "";
    }
    if (nextChallengeBtn) {
      var next = findNextChallenge(idx);
      if (next && !isCanvasSlide(slide) && (kind === "answer" || kind === "solution" || progress.done.indexOf(slide.index) !== -1)) {
        nextChallengeBtn.hidden = false;
        nextChallengeBtn.setAttribute("data-target", String(next.index));
      } else {
        nextChallengeBtn.hidden = true;
      }
    }
    if (reflectEl) {
      var showReflect = studyMode && (kind === "answer" || kind === "solution") && slide.question_index;
      reflectEl.hidden = !showReflect;
    }
  }

  function initSolutionPanel(panel) {
    if (!studyMode) {
      panel.classList.remove("cm-is-collapsed");
      return;
    }
    panel.classList.add("cm-is-collapsed");
  }

  function initStepBlocks(toolbar) {
    if (!studyMode) {
      root.querySelectorAll(".cm-step-block").forEach(function (b) {
        b.classList.remove("cm-step--hidden");
      });
      if (toolbar) toolbar.style.display = "none";
      return;
    }
    if (toolbar) toolbar.style.display = "";
    var blocks = Array.prototype.slice.call(root.querySelectorAll(".cm-step-block"));
    blocks.forEach(function (b, i) {
      b.classList.toggle("cm-step--hidden", i > 0);
    });
    var nextBtn = toolbar.querySelector("[data-cm-next-step]");
    var allBtn = toolbar.querySelector("[data-cm-show-all-steps]");

    function refresh() {
      var visible = blocks.filter(function (b) { return !b.classList.contains("cm-step--hidden"); }).length;
      if (nextBtn) {
        nextBtn.disabled = visible >= blocks.length;
        nextBtn.textContent = visible >= blocks.length
          ? "All steps shown"
          : "Next step (" + (visible + 1) + "/" + blocks.length + ")";
      }
    }

    if (nextBtn) {
      nextBtn.onclick = function () {
        for (var i = 0; i < blocks.length; i++) {
          if (blocks[i].classList.contains("cm-step--hidden")) {
            blocks[i].classList.remove("cm-step--hidden");
            blocks[i].classList.add("cm-step--revealing");
            window.setTimeout(function (el) {
              return function () { el.classList.remove("cm-step--revealing"); };
            }(blocks[i]), 320);
            if (window.MathJax && window.MathJax.typesetPromise) {
              window.MathJax.typesetPromise([blocks[i]]).catch(function () {});
            }
            break;
          }
        }
        refresh();
      };
    }
    if (allBtn) {
      allBtn.onclick = function () {
        blocks.forEach(function (b) { b.classList.remove("cm-step--hidden"); });
        if (window.MathJax && window.MathJax.typesetPromise) {
          window.MathJax.typesetPromise([bodyEl]).catch(function () {});
        }
        refresh();
      };
    }
    refresh();
  }

  function normalizeGridInValue(raw) {
    if (!raw) return "";
    return String(raw)
      .trim()
      .toLowerCase()
      .replace(/[\u2212\u2013\u2014]/g, "-")
      .replace(/\s+/g, "")
      .replace(/^=+/, "")
      .replace(/\\dfrac\{([^{}]+)\}\{([^{}]+)\}/g, "$1/$2")
      .replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, "$1/$2")
      .replace(/\\cdot/g, "*")
      .replace(/\\times/g, "*")
      .replace(/[{}]/g, "");
  }

  function gridInMatches(input, acceptList) {
    var val = normalizeGridInValue(input);
    if (!val) return false;
    var normalized = (acceptList || []).map(normalizeGridInValue);
    if (normalized.indexOf(val) !== -1) return true;
    if (/^-?\d+\.?\d*$/.test(val)) {
      var num = parseFloat(val);
      for (var i = 0; i < normalized.length; i++) {
        if (/^-?\d+\.?\d*$/.test(normalized[i])) {
          if (Math.abs(parseFloat(normalized[i]) - num) < 0.001) return true;
        }
      }
    }
    return false;
  }

  function initGridIn(widget) {
    var input = widget.querySelector(".cm-grid-in-input");
    var checkBtn = widget.querySelector("[data-cm-check-grid-in]");
    var feedback = widget.querySelector(".cm-grid-in-feedback");
    var accept = [];
    try {
      accept = JSON.parse(widget.getAttribute("data-cm-accept") || "[]");
    } catch (e) {
      accept = [];
    }

    function refreshBtn() {
      if (!checkBtn) return;
      checkBtn.disabled = !input || !input.value.trim() || widget.classList.contains("is-checked");
    }

    if (input) {
      input.addEventListener("input", refreshBtn);
      input.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" && checkBtn && !checkBtn.disabled) {
          ev.preventDefault();
          checkBtn.click();
        }
      });
    }

    if (checkBtn) {
      checkBtn.onclick = function () {
        if (!input || widget.classList.contains("is-checked")) return;
        var isCorrect = gridInMatches(input.value, accept);
        widget.classList.add("is-checked");
        input.classList.add("is-locked");
        input.readOnly = true;
        checkBtn.disabled = true;
        if (isCorrect) {
          widget.classList.add("is-correct-answer");
          if (feedback) feedback.textContent = "Correct! Compare with the worked solution.";
        } else {
          widget.classList.add("is-wrong-answer");
          if (feedback) {
            feedback.textContent = "Not quite — open the worked solution to see the correct answer.";
          }
        }
        markDone(slides[idx].index);
        submitClassroomResponse({
          slide_index: slides[idx].index,
          question_title: slides[idx].title || "",
          selected_answer: input.value || "",
          correct_answer: (accept && accept.length ? accept[0] : ""),
          is_correct: !!isCorrect,
        });
      };
    }
    refreshBtn();
  }

  function initMcq(mcq) {
    var selected = null;
    var choices = Array.prototype.slice.call(mcq.querySelectorAll(".cm-mcq-choice"));
    var checkBtn = mcq.querySelector("[data-cm-check-mcq]");
    var skipBtn = mcq.querySelector("[data-cm-go-answer]");

    choices.forEach(function (btn) {
      btn.onclick = function () {
        if (mcq.classList.contains("is-checked")) return;
        choices.forEach(function (c) { c.classList.remove("is-selected"); });
        btn.classList.add("is-selected");
        selected = btn.getAttribute("data-choice");
        if (checkBtn) checkBtn.disabled = false;
      };
    });

    if (checkBtn) {
      checkBtn.onclick = function () {
        if (!selected) return;
        var correct = mcq.getAttribute("data-cm-correct");
        var isCorrect = correct && selected === correct;
        choices.forEach(function (c) {
          c.classList.add("is-locked");
          if (!correct) return;
          var letter = c.getAttribute("data-choice");
          if (letter === correct) c.classList.add("is-correct");
          else if (letter === selected) c.classList.add("is-incorrect");
        });
        checkBtn.disabled = true;
        mcq.classList.add("is-checked");
        if (isCorrect) mcq.classList.add("is-correct-answer");
        else if (correct) mcq.classList.add("is-wrong-answer");
        markDone(slides[idx].index);
        var prompt = mcq.querySelector(".cm-mcq-prompt");
        if (prompt) {
          if (correct) {
            prompt.textContent = isCorrect
              ? "Correct! Compare with the worked solution."
              : "Not quite — the correct answer is " + correct + ". Review the solution.";
          } else {
            prompt.textContent = "Answer recorded — now compare with the worked solution.";
          }
        }
        submitClassroomResponse({
          slide_index: slides[idx].index,
          question_title: slides[idx].title || "",
          selected_answer: selected,
          correct_answer: correct || "",
          is_correct: !!isCorrect,
        });
      };
    }

    if (skipBtn) {
      skipBtn.onclick = function () {
        var slide = slides[idx];
        if (slide.answer_index) {
          markDone(slide.index);
          goToSlideNumber(slide.answer_index);
        }
      };
    }
  }

  function bindInteractivity(slide) {
    bodyEl.querySelectorAll("[data-cm-jump-section]").forEach(function (btn) {
      btn.onclick = function () {
        var target = parseInt(btn.getAttribute("data-cm-jump-section"), 10);
        if (target) goToSlideNumber(target);
      };
    });
    bodyEl.querySelectorAll("[data-cm-solution-panel]").forEach(initSolutionPanel);
    bodyEl.querySelectorAll("[data-cm-reveal-solution]").forEach(function (btn) {
      btn.onclick = function () {
        var panel = bodyEl.querySelector("[data-cm-solution-panel]");
        if (panel) {
          panel.classList.remove("cm-is-collapsed");
          panel.classList.add("cm-is-revealing");
          if (window.MathJax && window.MathJax.typesetPromise) {
            window.MathJax.typesetPromise([panel]).catch(function () {});
          }
        }
        var banner = bodyEl.querySelector("[data-cm-try-banner]");
        if (banner) banner.classList.add("is-dismissed");
        markDone(slide.index);
        updateCoach(slide);
      };
    });
    bodyEl.querySelectorAll("[data-cm-go-answer]").forEach(function (btn) {
      if (btn.closest(".cm-mcq-interactive")) return;
      btn.onclick = function () {
        if (slide.answer_index) {
          markDone(slide.index);
          goToSlideNumber(slide.answer_index);
        }
      };
    });
    var stepsToolbar = bodyEl.querySelector("[data-cm-steps-toolbar]");
    if (stepsToolbar) initStepBlocks(stepsToolbar);
    bodyEl.querySelectorAll("[data-cm-mcq]").forEach(initMcq);
    bodyEl.querySelectorAll("[data-cm-grid-in]").forEach(initGridIn);

    if ((slide.kind === "question" || slide.kind === "practice") && studyMode) {
      var focusInput = bodyEl.querySelector(".cm-grid-in-input:not(.is-locked)");
      if (focusInput) {
        window.setTimeout(function () {
          try {
            focusInput.focus({ preventScroll: true });
          } catch (e) {
            focusInput.focus();
          }
        }, 280);
      }
    }
  }

  function render() {
    var slide = slides[idx];
    if (!slide) return;
    var kind = slide.kind || "lesson";
    var canvas = isCanvasSlide(slide);

    slideEl.className = "np-cm-slide np-cm-slide--" + kind + (canvas ? " np-cm-slide--canvas" : "") + " is-entering";
    if (deckEl) {
      deckEl.classList.toggle("is-canvas-mode", canvas);
    }
    if (slideHeadEl) {
      slideHeadEl.hidden = canvas;
    }
    window.setTimeout(function () { slideEl.classList.remove("is-entering"); }, 420);

    bodyEl.innerHTML = slide.html || "";
    titleEl.textContent = slide.title || ("Slide " + slide.index);
    if (sectionEl) {
      sectionEl.textContent = slide.section ? slide.section : "";
    }
    badgeEl.textContent = String(slide.index).padStart(2, "0");
    counterEl.textContent = slide.index + " / " + slides.length;
    if (railCounterEl) railCounterEl.textContent = slide.index + " / " + slides.length;
    if (kindPill) {
      kindPill.textContent = kindLabels[kind] || "Lesson";
      kindPill.className = "np-cm-kind-pill np-cm-kind-pill--" + kind;
    }
    if (progressEl) {
      progressEl.style.width = String(Math.round(100 * slide.index / slides.length)) + "%";
    }
    if (pathCurrentEl && slide.section) {
      pathCurrentEl.textContent = slide.section;
    }
    if (sectionLabelEl && slide.section) {
      sectionLabelEl.textContent = slide.section + " · " + slides.length + " slides";
    }
    if (stageEl) stageEl.scrollTop = 0;

    markViewed(slide.index);

    outlineBtns.forEach(function (btn) {
      var active = String(btn.getAttribute("data-cm-index")) === String(slide.index);
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-current", active ? "true" : "false");
      if (active) btn.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });

    bindInteractivity(slide);
    renderLiveResults(slide);
    updateCoach(slide);
    updateClassroomPaceBadge();
    publishCurrentClassroomSlide();
    if (isInkTeacher() && !classroomSession && inkActiveSlideIndex !== null && slide.index !== inkActiveSlideIndex) {
      cacheLocalInkForSlide(inkActiveSlideIndex);
    }
    ensureInkLayer();
    if (isInkTeacher() && !classroomSession) {
      restoreLocalInkForSlide(slide.index);
    } else {
      loadInkForCurrentSlide(true);
    }
    if (kind === "intro") injectIntroOverview();
    if (kind === "closing") injectClosingCheckpointCta();

    if (window.MathJax) {
      if (window.MathJax.typesetClear) window.MathJax.typesetClear([bodyEl, titleEl]);
      if (window.MathJax.typesetPromise) window.MathJax.typesetPromise([bodyEl, titleEl]).catch(function () {});
    }
  }

  function guardedNavigate(delta) {
    if (isClassroomFollower()) {
      loadClassroomSession();
      return;
    }
    go(delta);
  }

  function guardedGoToSlideNumber(num) {
    if (isClassroomFollower()) {
      loadClassroomSession();
      return;
    }
    goToSlideNumber(num);
  }

  function go(delta) {
    idx = (idx + delta + slides.length) % slides.length;
    render();
  }

  outlineToggles.forEach(function (btn) {
    btn.addEventListener("click", function () {
      setOutlineOpen(!root.classList.contains("is-path-open"));
    });
  });

  filterBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      applyFilter(btn.getAttribute("data-cm-filter") || "all");
    });
  });

  if (studyToggle) {
    studyToggle.addEventListener("click", function () {
      studyMode = !studyMode;
      saveStudyMode();
      render();
    });
  }

  if (focusToggle) {
    focusToggle.addEventListener("click", toggleFocusMode);
  }
  focusExitBtns.forEach(function (btn) {
    btn.addEventListener("click", exitFocusMode);
  });
  ["fullscreenchange", "webkitfullscreenchange", "MSFullscreenChange"].forEach(function (eventName) {
    document.addEventListener(eventName, function () {
      if (getFullscreenElement() && root.classList.contains("is-focus-mode")) {
        window.requestAnimationFrame(resizeInkCanvas);
      }
      if (!getFullscreenElement() && root.classList.contains("is-focus-mode")) {
        setFocusMode(false, { fullscreen: false });
      }
    });
  });

  if (hintBtn && hintPanel) {
    hintBtn.addEventListener("click", function () {
      var hint = hintBtn.getAttribute("data-hint") || "";
      hintPanel.textContent = hint;
      hintPanel.hidden = !hintPanel.hidden;
    });
  }

  if (resumeGoBtn) {
    resumeGoBtn.addEventListener("click", function () {
      var target = parseInt(progress.last_slide_index, 10) || 1;
      hideResumeBanner();
      goToSlideNumber(target);
    });
  }
  if (resumeDismissBtn) {
    resumeDismissBtn.addEventListener("click", function () {
      hideResumeBanner();
      try {
        sessionStorage.setItem(resumeDismissKey, "1");
      } catch (e) {}
    });
  }

  if (nextChallengeBtn) {
    nextChallengeBtn.addEventListener("click", function () {
      var target = parseInt(nextChallengeBtn.getAttribute("data-target"), 10);
      if (target) goToSlideNumber(target);
    });
  }

  var gotItBtn = root.querySelector("[data-cm-got-it]");
  var reviewBtn = root.querySelector("[data-cm-review-again]");
  if (gotItBtn) {
    gotItBtn.addEventListener("click", function () {
      markDone(slides[idx].index);
      if (reflectEl) reflectEl.hidden = true;
      var next = findNextChallenge(idx);
      if (next) goToSlideNumber(next.index);
    });
  }
  if (reviewBtn) {
    reviewBtn.addEventListener("click", function () {
      if (stageEl) stageEl.scrollTop = 0;
      var toolbar = bodyEl.querySelector("[data-cm-steps-toolbar]");
      if (toolbar) {
        root.querySelectorAll(".cm-step-block").forEach(function (b) { b.classList.remove("cm-step--hidden"); });
      }
    });
  }

  root.querySelector("[data-cm-prev]").addEventListener("click", function () { guardedNavigate(-1); });
  root.querySelector("[data-cm-next]").addEventListener("click", function () { guardedNavigate(1); });

  document.querySelectorAll("[data-cm-open-checkpoint]").forEach(function (btn) {
    btn.addEventListener("click", openCheckpoint);
  });
  if (checkpointEl) {
    checkpointEl.addEventListener("click", function (e) {
      if (e.target.closest("[data-cm-checkpoint-close]")) {
        e.preventDefault();
        e.stopPropagation();
        closeCheckpoint();
      }
    });
    var cpNext = checkpointEl.querySelector("[data-cm-checkpoint-next]");
    if (cpNext) {
      cpNext.addEventListener("click", function () {
        checkpointState.cursor += 1;
        renderCheckpointQuestion();
      });
    }
  }

  outlineBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var target = parseInt(btn.getAttribute("data-cm-index"), 10);
      if (target > 0) {
        guardedGoToSlideNumber(target);
        if (window.matchMedia && window.matchMedia("(max-width: 1100px)").matches) {
          setOutlineOpen(false);
        }
      }
    });
  });

  document.addEventListener("keydown", function (e) {
    var tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (e.key === "Escape" && checkpointEl && checkpointEl.classList.contains("is-open")) {
      e.preventDefault();
      closeCheckpoint();
      return;
    }
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); guardedNavigate(1); }
    if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); guardedNavigate(-1); }
    if ((e.key === "p" || e.key === "P") && isInkTeacher()) {
      e.preventDefault();
      toggleInkToolbar();
      return;
    }
    if ((e.key === "u" || e.key === "U") && isInkTeacher() && inkStrokes.length) {
      e.preventDefault();
      inkStrokes.pop();
      inkCurrentStroke = null;
      redrawInkCanvas();
      scheduleInkSave();
      updateInkActionButtons();
      return;
    }
    if ((e.key === "l" || e.key === "L") && isInkTeacher() && inkExpanded) {
      e.preventDefault();
      inkTool = "laser";
      inkEnabled = true;
      if (inkDockEl) {
        inkDockEl.querySelectorAll("[data-ink-tool]").forEach(function (b) {
          b.classList.toggle("is-active", b.getAttribute("data-ink-tool") === "laser");
        });
      }
      updateInkToolHint();
      syncInkDockState();
      return;
    }
    if ((e.key === "e" || e.key === "E") && isInkTeacher() && inkExpanded) {
      e.preventDefault();
      inkTool = "eraser";
      inkEnabled = true;
      inkPendingStamp = null;
      if (inkDockEl) {
        inkDockEl.querySelectorAll("[data-ink-tool]").forEach(function (b) {
          b.classList.toggle("is-active", b.getAttribute("data-ink-tool") === "eraser");
        });
      }
      updateInkToolHint();
      syncInkDockState();
      saveInkPrefs();
      return;
    }
    if ((e.key === "m" || e.key === "M") && isInkTeacher() && inkExpanded) {
      e.preventDefault();
      inkTool = "smart";
      inkEnabled = true;
      inkPendingStamp = null;
      if (inkDockEl) {
        inkDockEl.querySelectorAll("[data-ink-tool]").forEach(function (b) {
          b.classList.toggle("is-active", b.getAttribute("data-ink-tool") === "smart");
        });
      }
      updateInkToolHint();
      syncInkDockState();
      saveInkPrefs();
      return;
    }
    if ((e.key === "f" || e.key === "F") && isInkTeacher() && inkExpanded) {
      e.preventDefault();
      inkTool = "math";
      inkEnabled = true;
      if (inkDockEl) {
        inkDockEl.querySelectorAll("[data-ink-tool]").forEach(function (b) {
          b.classList.toggle("is-active", b.getAttribute("data-ink-tool") === "math");
        });
      }
      openFormulaPad();
      updateInkToolHint();
      syncInkDockState();
      return;
    }
    if ((e.key === "g" || e.key === "G") && isInkTeacher() && inkExpanded) {
      e.preventDefault();
      inkTool = "math";
      inkEnabled = true;
      if (inkDockEl) {
        inkDockEl.querySelectorAll("[data-ink-tool]").forEach(function (b) {
          b.classList.toggle("is-active", b.getAttribute("data-ink-tool") === "math");
        });
      }
      updateInkToolHint();
      syncInkDockState();
      saveInkPrefs();
      return;
    }
    if ((e.key === "[" || e.key === "]") && isInkTeacher() && inkExpanded) {
      e.preventDefault();
      stepInkSize(e.key === "]" ? 1 : -1);
      return;
    }
    if (e.key === "f" || e.key === "F") { e.preventDefault(); toggleFocusMode(); }
    if (e.key === "Escape" && root.classList.contains("is-focus-mode")) {
      e.preventDefault();
      exitFocusMode();
    }
  });

  saveStudyMode();
  applyFilter("all");
  syncOutlineDone();
  updateStudyStat();
  updateMastery();
  updateKnowledgeMap();
  loadClassroomSession();
  if (classroomActiveApi) {
    var pollJitter = 0;
    try {
      pollJitter = parseInt(sessionStorage.getItem("cmPollJitter") || "0", 10);
      if (!pollJitter) {
        pollJitter = Math.floor(Math.random() * 800);
        sessionStorage.setItem("cmPollJitter", String(pollJitter));
      }
    } catch (e) {
      pollJitter = Math.floor(Math.random() * 800);
    }
    window.setTimeout(function () {
      loadClassroomSession();
      window.setInterval(loadClassroomSession, 2500);
    }, pollJitter);
    // Background tabs throttle timers; resync immediately when the student
    // comes back so they land on the teacher's current slide right away.
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) loadClassroomSession();
    });
    window.addEventListener("focus", loadClassroomSession);
    window.addEventListener("pageshow", function () { loadClassroomSession(); });
  }
  if (classroomSummaryApi) {
    loadClassroomSummary();
    classroomSummaryTimer = window.setInterval(loadClassroomSummary, 4000);
    window.addEventListener("beforeunload", function () {
      if (classroomSummaryTimer) window.clearInterval(classroomSummaryTimer);
    });
  }
  if (window.matchMedia && window.matchMedia("(min-width: 1101px)").matches) {
    if (!loadFocusMode()) {
      setOutlineOpen(true);
    }
  }
  if (isInkTeacher()) {
    loadInkPrefs();
    updateInkDock();
  }
  setFocusMode(loadFocusMode(), { fullscreen: false });
  var initialSlide = parseInitialSlide();
  if (initialSlide > 0) {
    goToSlideNumber(initialSlide);
  }
  loadRemoteProgress().then(function () {
    if (initialSlide <= 0 && progress.last_slide_index > 1) {
      showResumeBanner();
    }
    render();
  });
})();
