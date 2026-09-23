/**
 * AP Calculus lesson viewer UI: compact chrome, path modes, phase stepper, resume, gates.
 */
(function () {
  "use strict";

  var root = document.querySelector(".np-cm-viewer--ap-calc[data-cm-viewer]");
  if (!root) return;

  var lessonSlug = root.getAttribute("data-lesson-slug") || "lesson";
  var pathKey = "np-ap-path-mode-" + lessonSlug;
  var kmKey = "np-ap-km-mode-" + lessonSlug;
  var lessonStartedKey = "np-ap-started-" + lessonSlug;
  var resumeDismissKey = "np-cm-resume-dismiss-" + lessonSlug;

  var resumeEl = root.querySelector("[data-cm-resume]");
  var resumeConsumed = false;
  var stickyChrome = root.querySelector("[data-ap-sticky-chrome]");
  var stickyCounter = root.querySelector("[data-ap-sticky-counter]");
  var phaseStepper = root.querySelector("[data-ap-phase-stepper]");
  var lessonChrome = root.querySelector("[data-ap-lesson-chrome]");

  function consumeResumeBanner() {
    resumeConsumed = true;
    if (resumeEl) {
      resumeEl.hidden = true;
      resumeEl.classList.add("is-dismissed");
    }
    try {
      sessionStorage.setItem(resumeDismissKey, "1");
    } catch (e) {}
  }

  try {
    if (sessionStorage.getItem(resumeDismissKey) === "1") {
      resumeConsumed = true;
      if (resumeEl) {
        resumeEl.hidden = true;
        resumeEl.classList.add("is-dismissed");
      }
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

  /* ── Unified lesson path: expanded | compact | hidden ── */
  function setPathMode(mode) {
    root.classList.remove("is-path-expanded", "is-path-compact", "is-path-hidden", "is-km-expanded", "is-km-compact", "is-km-collapsed");
    if (mode === "expanded") {
      root.classList.add("is-path-expanded", "is-km-expanded", "is-path-open");
    } else if (mode === "compact") {
      root.classList.add("is-path-compact", "is-km-compact", "is-path-open");
    } else {
      root.classList.add("is-path-hidden", "is-km-collapsed");
      root.classList.remove("is-path-open");
    }
    root.querySelectorAll("[data-ap-path-mode]").forEach(function (btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-ap-path-mode") === mode);
    });
    root.querySelectorAll("[data-cm-km-mode]").forEach(function (btn) {
      var km = mode === "expanded" ? "expanded" : mode === "compact" ? "compact" : "collapsed";
      btn.classList.toggle("is-active", btn.getAttribute("data-cm-km-mode") === km);
    });
    try {
      localStorage.setItem(pathKey, mode);
      localStorage.setItem(kmKey, mode === "hidden" ? "collapsed" : mode);
    } catch (e) {}
  }

  function loadPathMode() {
    var mobile = window.matchMedia("(max-width: 1099px)").matches;
    var started = false;
    try {
      started = localStorage.getItem(lessonStartedKey) === "1";
    } catch (e) {}
    var mode = "expanded";
    try {
      mode = localStorage.getItem(pathKey) || (mobile ? "hidden" : started ? "compact" : "expanded");
    } catch (e) {}
    if (mobile && !localStorage.getItem(pathKey)) mode = "hidden";
    setPathMode(mode);
  }

  root.querySelectorAll("[data-ap-path-mode]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setPathMode(btn.getAttribute("data-ap-path-mode"));
    });
  });

  root.querySelectorAll("[data-cm-km-mode]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var km = btn.getAttribute("data-cm-km-mode");
      setPathMode(km === "collapsed" ? "hidden" : km);
    });
  });

  var kmBackdrop = root.querySelector("[data-cm-km-drawer-backdrop]");
  if (kmBackdrop) {
    kmBackdrop.addEventListener("click", function () {
      root.classList.remove("is-km-mobile-open", "is-path-drawer-open");
      kmBackdrop.hidden = true;
    });
  }

  var kmOpenBtn = root.querySelector("[data-cm-km-drawer-open]");
  if (kmOpenBtn) {
    kmOpenBtn.addEventListener("click", function () {
      root.classList.add("is-km-mobile-open", "is-path-drawer-open");
      if (kmBackdrop) kmBackdrop.hidden = false;
    });
  }

  function markLessonStarted() {
    try {
      localStorage.setItem(lessonStartedKey, "1");
    } catch (e) {}
    if (!localStorage.getItem(pathKey) && root.classList.contains("is-path-expanded")) {
      setPathMode("compact");
    }
  }

  /* ── Sticky compact bar on scroll ── */
  var stageEl = root.querySelector(".np-cm-slide-stage");
  function syncStickyChrome() {
    if (!stickyChrome || !lessonChrome) return;
    var scrolled = (stageEl && stageEl.scrollTop > 48) || window.scrollY > 80;
    stickyChrome.hidden = !scrolled;
    root.classList.toggle("is-chrome-stuck", scrolled);
  }
  if (stageEl) stageEl.addEventListener("scroll", syncStickyChrome, { passive: true });
  window.addEventListener("scroll", syncStickyChrome, { passive: true });

  /* ── Phase stepper ── */
  var PHASES = ["understand", "learn", "investigate", "explain"];

  function setActivePhase(phase) {
    if (!phaseStepper) return;
    phaseStepper.querySelectorAll("[data-ap-phase]").forEach(function (btn) {
      var on = btn.getAttribute("data-ap-phase") === phase;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-current", on ? "step" : "false");
    });
  }

  function phaseFromLabStep(step) {
    if (step <= 0) return "understand";
    if (step <= 2) return "investigate";
    if (step <= 6) return "learn";
    return "explain";
  }

  function phaseFromSlideKind(kind) {
    if (kind === "question" || kind === "practice") return "investigate";
    if (kind === "example" || kind === "solution") return "learn";
    if (kind === "closing") return "explain";
    return "understand";
  }

  function bindPhaseStepper() {
    if (!phaseStepper) return;
    phaseStepper.querySelectorAll("[data-ap-phase]").forEach(function (btn) {
      if (btn._apBound) return;
      btn._apBound = true;
      btn.addEventListener("click", function () {
        consumeResumeBanner();
        setActivePhase(btn.getAttribute("data-ap-phase"));
        var panel = root.querySelector("[data-ap-explore-panel]");
        var gate = root.querySelector("[data-ap-explore-gate]");
        if (btn.getAttribute("data-ap-phase") === "investigate" && gate && panel) {
          gate.hidden = true;
          panel.hidden = false;
          window.dispatchEvent(new Event("resize"));
        }
      });
    });
  }

  function syncPhaseStepperVisibility(slideEl) {
    if (!phaseStepper) return;
    var hasLab = slideEl && slideEl.querySelector("[data-ap-math-lab]");
    var isInvestigation = slideEl && (
      slideEl.classList.contains("np-cm-slide--investigation")
      || slideEl.querySelector(".ap-slide-template--investigation")
      || hasLab
    );
    phaseStepper.hidden = !isInvestigation;
    if (!isInvestigation) return;
    var kindPill = root.querySelector("[data-cm-kind-pill]");
    var kind = kindPill ? kindPill.textContent.toLowerCase() : "lesson";
    setActivePhase(phaseFromSlideKind(kind));
  }

  function syncIntroLayout(slideEl) {
    var isIntro = slideEl && slideEl.classList.contains("np-cm-slide--intro");
    root.classList.toggle("is-intro-slide", !!isIntro);
  }

  function openLabExplorePanels(scope) {
    (scope || root).querySelectorAll("[data-ap-explore-phase]").forEach(function (phase) {
      var gate = phase.querySelector("[data-ap-explore-gate]");
      var panel = phase.querySelector("[data-ap-explore-panel]");
      if (gate) gate.hidden = true;
      if (panel) panel.hidden = false;
    });
  }

  function syncLabSlideLayout(slideEl) {
    var hasLab = slideEl && slideEl.querySelector("[data-ap-math-lab]");
    root.classList.toggle("is-lab-slide", !!hasLab);
  }

  document.addEventListener("np-cm-slide-rendered", function (ev) {
    var slideEl = root.querySelector("[data-cm-slide]");
    syncIntroLayout(slideEl);
    syncLabSlideLayout(slideEl);
    if (document.body.classList.contains("is-cm-projector") || root.classList.contains("is-focus-mode")) {
      openLabExplorePanels(slideEl);
    }
    syncPhaseStepperVisibility(slideEl);
    if (stickyCounter && ev.detail && ev.detail.index) {
      var total = root.getAttribute("data-slide-count") || "?";
      stickyCounter.textContent = ev.detail.index + " / " + total;
    }
    bindExploreGates(root);
    bindPhaseStepper();
  });

  root.addEventListener("ap-math-lab-state", function (ev) {
    var d = ev.detail || {};
    if (d.currentPhase) {
      setActivePhase(d.currentPhase);
    } else if (typeof d.labStep === "number") {
      setActivePhase(phaseFromLabStep(d.labStep));
    }
  });

  function onProjectorChange(on) {
    if (on) {
      setPathMode("hidden");
      if (stickyChrome) stickyChrome.hidden = true;
      root.querySelectorAll("[data-ap-explore-gate]").forEach(function (gate) {
        gate.hidden = true;
      });
      root.querySelectorAll("[data-ap-explore-panel]").forEach(function (panel) {
        panel.hidden = false;
      });
    }
    window.dispatchEvent(new Event("resize"));
    if (window.MathJax && window.MathJax.typesetPromise) {
      window.MathJax.typesetPromise([root]).catch(function () {});
    }
  }

  document.addEventListener("np-cm-focus-mode", function (ev) {
    onProjectorChange(!!(ev.detail && ev.detail.on));
  });

  /* ── Resume banner: entry only ── */
  window.ApCalcLessonUI = {
    consumeResumeBanner: consumeResumeBanner,
    markLessonStarted: markLessonStarted,
    setPathMode: setPathMode,
    onProjectorChange: onProjectorChange,
    isResumeConsumed: function () { return resumeConsumed; },
  };

  /* ── Explore / investigation gates ── */
  function bindExploreGates(scope) {
    (scope || root).querySelectorAll("[data-ap-start-investigation]").forEach(function (btn) {
      if (btn._apBound) return;
      btn._apBound = true;
      btn.addEventListener("click", function () {
        consumeResumeBanner();
        var phase = btn.closest("[data-ap-explore-phase]");
        if (!phase) return;
        var gate = phase.querySelector("[data-ap-explore-gate]");
        var panel = phase.querySelector("[data-ap-explore-panel]");
        if (gate) gate.hidden = true;
        if (panel) panel.hidden = false;
        root.querySelectorAll(".ap-worked-model--collapsible[open]").forEach(function (el) {
          el.removeAttribute("open");
        });
        markLessonStarted();
        setActivePhase("investigate");
        window.dispatchEvent(new Event("resize"));
        if (window.MathJax && window.MathJax.typesetPromise) {
          window.MathJax.typesetPromise([phase]).catch(function () {});
        }
      });
    });
  }

  bindExploreGates(root);
  bindPhaseStepper();
  var initialSlide = root.querySelector("[data-cm-slide]");
  syncIntroLayout(initialSlide);
  syncLabSlideLayout(initialSlide);
  syncPhaseStepperVisibility(initialSlide);

  loadPathMode();
})();
