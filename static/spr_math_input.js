(function () {
    "use strict";

    var input = document.getElementById("spr-answer-input");
    var mirror = document.getElementById("spr-answer-math");
    if (!input || !mirror) return;

    var LATEX_COMMAND =
        /\\(?:frac|sqrt|pi|cdot|times|div|le|ge|ne|infty|theta|alpha|beta|gamma|Delta|pm|mp|left|right|text)\b/;

    function extractParenGroup(s, openIndex) {
        if (s.charAt(openIndex) !== "(") return null;
        var depth = 0;
        for (var i = openIndex; i < s.length; i++) {
            var ch = s.charAt(i);
            if (ch === "(") depth++;
            else if (ch === ")") {
                depth--;
                if (depth === 0) {
                    return { inner: s.slice(openIndex + 1, i), end: i };
                }
            }
        }
        return null;
    }

    function convertSqrt(s) {
        var out = "";
        var i = 0;
        while (i < s.length) {
            var tail = s.slice(i);
            var m = tail.match(/^(?:sqrt|√)\s*\(/i);
            if (!m) {
                out += s.charAt(i);
                i++;
                continue;
            }
            var openAt = i + m[0].length - 1;
            var group = extractParenGroup(s, openAt);
            if (!group) {
                out += m[0];
                i += m[0].length;
                continue;
            }
            out += "\\sqrt{" + asciiMathToTex(group.inner) + "}";
            i = group.end + 1;
        }
        return out;
    }

    function convertPi(s) {
        return s.replace(/\bpi\b/gi, "\\pi ");
    }

    function convertInfinity(s) {
        return s
            .replace(/\binfinity\b/gi, "\\infty ")
            .replace(/\binf\b/gi, "\\infty ");
    }

    function convertScientific(s) {
        return s.replace(
            /(-?\d+(?:\.\d+)?)\s*[eE]\s*([+-]?\d+)/g,
            function (_, coef, exp) {
                return coef + " \\times 10^{" + exp + "}";
            }
        );
    }

    function convertFractions(s) {
        return s.replace(
            /(-?\d+(?:\.\d+)?)\s*\/\s*(-?\d+(?:\.\d+)?)/g,
            function (_, n, d) {
                return "\\frac{" + n + "}{" + d + "}";
            }
        );
    }

    function convertSuperscripts(s) {
        s = s.replace(/\^\{([^{}]+)\}/g, "^{$1}");
        s = s.replace(/\^\(\s*([^()]+)\s*\)/g, function (_, inner) {
            return "^{" + asciiMathToTex(inner) + "}";
        });
        s = s.replace(/\^(-?\d+(?:\.\d+)?)/g, "^{$1}");
        return s;
    }

    function convertSubscripts(s) {
        s = s.replace(/_\{([^{}]+)\}/g, "_{$1}");
        s = s.replace(/_\(\s*([^()]+)\s*\)/g, function (_, inner) {
            return "_{" + asciiMathToTex(inner) + "}";
        });
        s = s.replace(/_([a-zA-Z0-9])/g, "_{$1}");
        return s;
    }

    function convertOperators(s) {
        return s
            .replace(/<=/g, " \\le ")
            .replace(/>=/g, " \\ge ")
            .replace(/!=/g, " \\ne ")
            .replace(/\*/g, " \\cdot ")
            .replace(/×/g, " \\times ")
            .replace(/·/g, " \\cdot ")
            .replace(/÷/g, " \\div ")
            .replace(/°/g, "^{\\circ}");
    }

    function asciiMathToTex(s) {
        s = String(s || "").trim();
        if (!s) return "";

        if (LATEX_COMMAND.test(s)) {
            return s;
        }

        s = convertPi(s);
        s = convertInfinity(s);
        s = convertScientific(s);
        s = convertSqrt(s);
        s = convertFractions(s);
        s = convertSuperscripts(s);
        s = convertSubscripts(s);
        s = convertOperators(s);
        return s;
    }

    function pureFractionTex(s) {
        var mixed = s.match(/^(-?\d+)\s+(-?\d+)\s*\/\s*(-?\d+)$/);
        if (mixed) {
            if (Number(mixed[3]) === 0) return null;
            return (
                "\\(" +
                mixed[1] +
                "\\frac{" +
                mixed[2] +
                "}{" +
                mixed[3] +
                "}\\)"
            );
        }
        var frac = s.match(/^(-?\d+)\s*\/\s*(-?\d+)$/);
        if (frac) {
            if (Number(frac[2]) === 0) return null;
            return "\\(\\frac{" + frac[1] + "}{" + frac[2] + "}\\)";
        }
        return null;
    }

    function inputToTex(raw) {
        var s = String(raw || "");
        if (!s.trim()) return null;

        var trimmed = s.trim();
        var pure = pureFractionTex(trimmed);
        if (pure) return pure;

        var body = asciiMathToTex(trimmed);
        if (!body) return null;
        return "\\(" + body + "\\)";
    }

    function clearMirror() {
        mirror.hidden = true;
        mirror.innerHTML = "";
        input.classList.remove("has-inline-math");
    }

    function renderMirror() {
        var tex = inputToTex(input.value);
        if (!tex) {
            clearMirror();
            return;
        }
        mirror.hidden = false;
        input.classList.add("has-inline-math");
        mirror.innerHTML = tex;
        if (window.MathJax && window.MathJax.typesetPromise) {
            window.MathJax.typesetPromise([mirror]).catch(function () {});
        }
    }

    input.addEventListener("input", renderMirror);
    renderMirror();
})();
