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
    updateCoach(slide);
    if (kind === "intro") injectIntroOverview();
    if (kind === "closing") injectClosingCheckpointCta();

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

  root.querySelector("[data-cm-prev]").addEventListener("click", function () { go(-1); });
  root.querySelector("[data-cm-next]").addEventListener("click", function () { go(1); });

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
        goToSlideNumber(target);
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
  updateKnowledgeMap();
  if (window.matchMedia && window.matchMedia("(min-width: 1101px)").matches) {
    if (!loadFocusMode()) {
      setOutlineOpen(true);
    }
  }
  setFocusMode(loadFocusMode());
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
