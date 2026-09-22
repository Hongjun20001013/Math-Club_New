/**
 * AP Calculus lesson viewer UI: course dropdown, knowledge map modes, resume banner, explore gates.
 */
(function () {
  "use strict";

  var root = document.querySelector(".np-cm-viewer--ap-calc[data-cm-viewer]");
  if (!root) return;

  var lessonSlug = root.getAttribute("data-lesson-slug") || "lesson";
  var kmKey = "np-ap-km-mode-" + lessonSlug;
  var lessonStartedKey = "np-ap-started-" + lessonSlug;
  var resumeDismissKey = "np-cm-resume-dismiss-" + lessonSlug;

  var resumeEl = root.querySelector("[data-cm-resume]");
  var resumeConsumed = false;

  function consumeResumeBanner() {
    resumeConsumed = true;
    if (resumeEl) resumeEl.hidden = true;
    try {
      sessionStorage.setItem(resumeDismissKey, "1");
    } catch (e) {}
  }

  try {
    if (sessionStorage.getItem(resumeDismissKey) === "1") {
      resumeConsumed = true;
      if (resumeEl) resumeEl.hidden = true;
    }
  } catch (e) {}

  /* ── Course dropdown ── */
  var courseToggle = root.querySelector("[data-cm-course-menu-toggle]");
  var courseMenu = root.querySelector("[data-cm-course-menu]");
  if (courseToggle && courseMenu) {
    courseToggle.addEventListener("click", function () {
      var open = courseMenu.hidden;
      courseMenu.hidden = !open;
      courseToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", function (e) {
      if (!root.contains(e.target) || (!courseToggle.contains(e.target) && !courseMenu.contains(e.target))) {
        courseMenu.hidden = true;
        courseToggle.setAttribute("aria-expanded", "false");
      }
    });
    courseToggle.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        courseMenu.hidden = true;
        courseToggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* ── Knowledge map: expanded | compact | collapsed ── */
  function setKnowledgeMode(mode) {
    root.classList.remove("is-km-expanded", "is-km-compact", "is-km-collapsed");
    if (mode === "expanded") root.classList.add("is-km-expanded");
    else if (mode === "compact") root.classList.add("is-km-compact");
    else root.classList.add("is-km-collapsed");
    root.querySelectorAll("[data-cm-km-mode]").forEach(function (btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-cm-km-mode") === mode);
    });
    try {
      localStorage.setItem(kmKey, mode);
    } catch (e) {}
  }

  function loadKnowledgeMode() {
    var started = false;
    try {
      started = localStorage.getItem(lessonStartedKey) === "1";
    } catch (e) {}
    var mode = "expanded";
    try {
      mode = localStorage.getItem(kmKey) || (started ? "compact" : "expanded");
    } catch (e) {}
    setKnowledgeMode(mode);
  }

  root.querySelectorAll("[data-cm-km-mode]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setKnowledgeMode(btn.getAttribute("data-cm-km-mode"));
    });
  });

  var kmBackdrop = root.querySelector("[data-cm-km-drawer-backdrop]");
  if (kmBackdrop) {
    kmBackdrop.addEventListener("click", function () {
      root.classList.remove("is-km-mobile-open");
      kmBackdrop.hidden = true;
    });
  }

  var kmOpenBtn = root.querySelector("[data-cm-km-drawer-open]");
  if (kmOpenBtn) {
    kmOpenBtn.addEventListener("click", function () {
      root.classList.add("is-km-mobile-open");
      if (kmBackdrop) kmBackdrop.hidden = false;
    });
  }

  function markLessonStarted() {
    try {
      localStorage.setItem(lessonStartedKey, "1");
    } catch (e) {}
    if (!root.classList.contains("is-km-expanded") && !root.classList.contains("is-km-collapsed")) return;
    if (localStorage.getItem(kmKey)) return;
    setKnowledgeMode("compact");
  }

  /* ── Resume banner: entry only ── */
  window.ApCalcLessonUI = {
    consumeResumeBanner: consumeResumeBanner,
    markLessonStarted: markLessonStarted,
    isResumeConsumed: function () { return resumeConsumed; },
  };

  /* ── Explore phase gates ── */
  function bindExploreGates(scope) {
    (scope || root).querySelectorAll("[data-ap-start-investigation]").forEach(function (btn) {
      if (btn._apBound) return;
      btn._apBound = true;
      btn.addEventListener("click", function () {
        var phase = btn.closest("[data-ap-explore-phase]");
        if (!phase) return;
        var gate = phase.querySelector("[data-ap-explore-gate]");
        var panel = phase.querySelector("[data-ap-explore-panel]");
        if (gate) gate.hidden = true;
        if (panel) panel.hidden = false;
        markLessonStarted();
        window.dispatchEvent(new Event("resize"));
        if (window.MathJax && window.MathJax.typesetPromise) {
          window.MathJax.typesetPromise([phase]).catch(function () {});
        }
      });
    });
  }

  bindExploreGates(root);
  document.addEventListener("np-cm-slide-rendered", function () {
    bindExploreGates(root);
  });

  /* ── Focus mode: collapse knowledge map ── */
  var focusToggle = root.querySelector("[data-cm-focus-toggle]");
  if (focusToggle) {
    focusToggle.addEventListener("click", function () {
      window.setTimeout(function () {
        if (root.classList.contains("is-focus-mode")) {
          setKnowledgeMode("collapsed");
          root.classList.remove("is-path-open");
        }
      }, 0);
    });
  }

  loadKnowledgeMode();
})();
