(function () {
  "use strict";

  const studio = document.querySelector(".np-en-writing-studio");
  const ta = document.getElementById("english-writing-input");
  const out = document.getElementById("english-writing-count");
  const targetEl = document.getElementById("english-writing-target");

  function wordCount(text) {
    return (text || "").trim().split(/\s+/).filter(Boolean).length;
  }

  function updateCount() {
    if (!ta || !out) return;
    const n = wordCount(ta.value);
    out.textContent = n + (n === 1 ? " word" : " words");
    const min = studio ? parseInt(studio.getAttribute("data-word-min") || "200", 10) : 200;
    const max = studio ? parseInt(studio.getAttribute("data-word-max") || "300", 10) : 300;
    out.classList.toggle("is-below-target", n > 0 && n < min);
    out.classList.toggle("is-in-target", n >= min && n <= max);
    out.classList.toggle("is-above-target", n > max);
    if (targetEl && n >= min) {
      targetEl.textContent =
        n > max ? "Above target — you may trim if needed." : "Within target range — keep going or submit when ready.";
    }
  }

  if (ta && out) {
    ta.addEventListener("input", updateCount);
    updateCount();
  }

  document.querySelectorAll(".sat-en-writing-pick-input").forEach((inp) => {
    const sync = () => {
      document.querySelectorAll(".sat-en-writing-pick-card").forEach((c) => c.classList.remove("is-selected"));
      if (inp.checked) {
        const card = inp.closest(".sat-en-writing-pick-card");
        card?.classList.add("is-selected");
        ta?.focus();
      }
    };
    inp.addEventListener("change", sync);
    if (inp.checked) sync();
  });

  const pickRequired = document.querySelector(".sat-en-writing-pick-input");
  const form = document.getElementById("practice-answer-form");
  if (form && pickRequired) {
    form.addEventListener(
      "submit",
      function (ev) {
        const picked = document.querySelector(".sat-en-writing-pick-input:checked");
        if (!picked) {
          ev.preventDefault();
          const status = document.getElementById("sat-answer-status");
          if (status) {
            status.classList.add("is-visible");
            status.textContent = "Choose Option A or B above before saving your essay.";
          }
          document.getElementById("np-en-writing-pick-block")?.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      },
      true
    );
  }
})();
