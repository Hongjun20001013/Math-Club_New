(function () {
    "use strict";

    var reduceMotion = false;
    try {
        reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (e) {}

    document.documentElement.classList.add("np-pl-js");

    /* Remove legacy curtain if present */
    var curtain = document.getElementById("np-pl-curtain");
    if (curtain && curtain.parentNode) {
        curtain.parentNode.removeChild(curtain);
    }
    document.documentElement.classList.remove("np-pl-curtain-lock");

    function bindRecoveryCopy(scope) {
        (scope || document).querySelectorAll("[data-pl-copy-recovery]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var ticket = btn.closest("[data-pl-ticket]") || btn.closest(".np-pl-ticket");
                var codeEl = ticket && ticket.querySelector("[data-pl-recovery-code]");
                var text = codeEl ? (codeEl.textContent || "").trim() : "";
                if (!text) return;
                var done = function () {
                    btn.textContent = "Copied";
                    if (ticket) ticket.classList.add("is-copied");
                    window.setTimeout(function () {
                        btn.textContent = "Copy code";
                        if (ticket) ticket.classList.remove("is-copied");
                    }, 1600);
                };
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(text).then(done).catch(function () {
                        window.prompt("Copy this recovery code", text);
                    });
                } else {
                    window.prompt("Copy this recovery code", text);
                }
            });
        });
    }
    bindRecoveryCopy(document);

    var root = document.querySelector(".np-pl2--atelier");
    if (!root) return;

    function reveal(el) {
        el.classList.add("is-visible");
    }

    function flushVisible(nodes) {
        if (!nodes || !nodes.length) return;
        var vh = window.innerHeight || document.documentElement.clientHeight;
        nodes.forEach(function (el) {
            var rect = el.getBoundingClientRect();
            if (rect.top < vh * 0.92 && rect.bottom > 0) {
                reveal(el);
            }
        });
    }

    var scrollReveal = root.querySelectorAll("[data-pl-reveal]");
    if (reduceMotion || !("IntersectionObserver" in window)) {
        scrollReveal.forEach(reveal);
    } else {
        var io = new IntersectionObserver(
            function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        reveal(entry.target);
                        io.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.08, rootMargin: "0px 0px 0px 0px" }
        );

        scrollReveal.forEach(function (el) {
            io.observe(el);
        });

        flushVisible(scrollReveal);
        window.addEventListener("load", function () {
            flushVisible(scrollReveal);
        }, { once: true });
    }

    root.querySelectorAll("[data-pl-stagger]").forEach(function (wrap) {
        var kids = wrap.querySelectorAll(":scope > [data-pl-reveal], :scope > .np-pl-tier, :scope > .np-pl-part__card");
        kids.forEach(function (kid, i) {
            kid.style.setProperty("--pl-i", String(i));
        });
    });

    /* Lightweight device tilt — throttled, desktop only */
    if (!reduceMotion && window.matchMedia("(min-width: 900px)").matches) {
        var device = root.querySelector(".np-pl-device--tilt");
        var shell = device && device.querySelector(".np-pl-device__shell");
        if (shell) {
            var tiltPending = false;
            var lastX = 0;
            var lastY = 0;
            device.addEventListener("mousemove", function (ev) {
                var r = device.getBoundingClientRect();
                lastX = (ev.clientX - r.left) / r.width - 0.5;
                lastY = (ev.clientY - r.top) / r.height - 0.5;
                if (tiltPending) return;
                tiltPending = true;
                requestAnimationFrame(function () {
                    shell.style.transform =
                        "rotateY(" + (lastX * 8) + "deg) rotateX(" + (-lastY * 6) + "deg)";
                    tiltPending = false;
                });
            });
            device.addEventListener("mouseleave", function () {
                shell.style.transform = "";
            });
        }
    }

    var drop = root.querySelector("[data-pl-drop]");
    if (drop) {
        var fileInput = drop.querySelector('input[type="file"]');
        var list = drop.querySelector("[data-pl-drop-list]");
        function kb(n) {
            return Math.max(1, Math.floor((n || 0) / 1024)) + " KB";
        }
        function renderQueue() {
            if (!list || !fileInput) return;
            var files = fileInput.files || [];
            list.innerHTML = "";
            if (!files.length) {
                list.hidden = true;
                return;
            }
            list.hidden = false;
            Array.prototype.forEach.call(files, function (file) {
                var li = document.createElement("li");
                var name = document.createElement("strong");
                name.textContent = file.name || "page";
                var size = document.createElement("span");
                size.textContent = kb(file.size);
                li.appendChild(name);
                li.appendChild(size);
                list.appendChild(li);
            });
        }
        function setDrag(on) {
            drop.classList.toggle("is-drag", !!on);
        }
        drop.addEventListener("dragenter", function (ev) {
            ev.preventDefault();
            setDrag(true);
        });
        drop.addEventListener("dragover", function (ev) {
            ev.preventDefault();
            setDrag(true);
        });
        drop.addEventListener("dragleave", function (ev) {
            if (!drop.contains(ev.relatedTarget)) setDrag(false);
        });
        drop.addEventListener("drop", function (ev) {
            ev.preventDefault();
            setDrag(false);
            if (!fileInput || !ev.dataTransfer || !ev.dataTransfer.files.length) return;
            try {
                fileInput.files = ev.dataTransfer.files;
            } catch (err) {}
            renderQueue();
        });
        if (fileInput) {
            fileInput.addEventListener("change", renderQueue);
        }
    }
})();
