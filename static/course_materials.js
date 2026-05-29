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
  var focusToggle = root.querySelector("[data-cm-focus-toggle]");
  var focusInlineExit = root.querySelector(".np-cm-focus-inline-exit");
  var focusExitBtns = Array.prototype.slice.call(root.querySelectorAll("[data-cm-focus-exit]"));
  var focusKey = "np-cm-focus-" + lessonSlug;
  var pathOpenBeforeFocus = false;
  var coachEl = root.querySelector("[data-cm-coach]");
  var slideHeadEl = root.querySelector(".np-cm-slide-head");
  var deckEl = root.querySelector(".np-cm-deck");
  var reflectEl = root.querySelector("[data-cm-reflect]");
  var outlineItems = Array.prototype.slice.call(root.querySelectorAll(".np-cm-outline-item"));
  var outlineBtns = Array.prototype.slice.call(root.querySelectorAll("[data-cm-index]"));
  var outlineToggles = Array.prototype.slice.call(root.querySelectorAll("[data-cm-toggle-outline]"));
  var filterBtns = Array.prototype.slice.call(root.querySelectorAll("[data-cm-filter]"));

  var kindLabels = {
    lesson: "Lesson",
    concept: "Concept",
    practice: "Practice",
    question: "Question",
    example: "Example",
    solution: "Solution",
    answer: "Answer",
    section: "Section",
    intro: "Intro",
    content: "Outline",
    closing: "Closing"
  };

  var progress = loadProgress();
  var studyMode = loadStudyMode();

  function loadProgress() {
    try {
      var raw = localStorage.getItem(storageKey);
      return raw ? JSON.parse(raw) : { done: [], viewed: [], reflections: {} };
    } catch (e) {
      return { done: [], viewed: [], reflections: {} };
    }
  }

  function saveProgress() {
    try {
      localStorage.setItem(storageKey, JSON.stringify(progress));
    } catch (e) {}
    updateStudyStat();
    updateMastery();
    syncOutlineDone();
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

  function goToIndex(targetIdx) {
    if (targetIdx >= 0 && targetIdx < slides.length) {
      idx = targetIdx;
      render();
    }
  }

  function goToSlideNumber(num) {
    for (var i = 0; i < slides.length; i++) {
      if (slides[i].index === num) {
        goToIndex(i);
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
    var pct = Math.min(100, Math.round(100 * (viewed * 0.4 + done * 0.6) / total));
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

  function setFocusMode(on) {
    if (on) {
      pathOpenBeforeFocus = root.classList.contains("is-path-open");
      setOutlineOpen(false);
    } else if (pathOpenBeforeFocus) {
      setOutlineOpen(true);
    }
    root.classList.toggle("is-focus-mode", on);
    if (focusToggle) {
      focusToggle.classList.toggle("is-active", on);
      focusToggle.setAttribute("aria-pressed", on ? "true" : "false");
      var label = focusToggle.querySelector(".np-cm-btn-label");
      if (label) label.textContent = on ? "Exit focus" : "Focus";
    }
    if (focusInlineExit) {
      focusInlineExit.hidden = !on;
    }
    if (coachEl && on) {
      coachEl.hidden = true;
    } else if (!on && slides[idx]) {
      updateCoach(slides[idx]);
    }
    saveFocusMode(on);
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
        choices.forEach(function (c) { c.classList.add("is-locked"); });
        checkBtn.disabled = true;
        mcq.classList.add("is-checked");
        markDone(slides[idx].index);
        var prompt = mcq.querySelector(".cm-mcq-prompt");
        if (prompt) prompt.textContent = "Answer recorded — now compare with the worked solution.";
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
    updateCoach(slide);

    if (window.MathJax) {
      if (window.MathJax.typesetClear) window.MathJax.typesetClear([bodyEl, titleEl]);
      if (window.MathJax.typesetPromise) window.MathJax.typesetPromise([bodyEl, titleEl]).catch(function () {});
    }
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

  if (hintBtn && hintPanel) {
    hintBtn.addEventListener("click", function () {
      var hint = hintBtn.getAttribute("data-hint") || "";
      hintPanel.textContent = hint;
      hintPanel.hidden = !hintPanel.hidden;
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

  root.querySelector("[data-cm-prev]").addEventListener("click", function () { go(-1); });
  root.querySelector("[data-cm-next]").addEventListener("click", function () { go(1); });
  outlineBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var target = parseInt(btn.getAttribute("data-cm-index"), 10) - 1;
      if (target >= 0 && target < slides.length) {
        idx = target;
        render();
        if (window.matchMedia && window.matchMedia("(max-width: 1100px)").matches) {
          setOutlineOpen(false);
        }
      }
    });
  });

  document.addEventListener("keydown", function (e) {
    var tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); go(1); }
    if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); go(-1); }
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
  if (window.matchMedia && window.matchMedia("(min-width: 1101px)").matches) {
    if (!loadFocusMode()) {
      setOutlineOpen(true);
    }
  }
  setFocusMode(loadFocusMode());
  render();
})();
