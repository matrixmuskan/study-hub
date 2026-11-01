/* Study Hub skin script for pages built before sh-2. Looks only: it removes decorative emoji from
   tabs, headings, buttons, and badges (never from questions or answer options). */
(function () {
  var RE = /(?:[\u2190-\u21FF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF\u{1F000}-\u{1FAFF}](?:\uFE0F|[\u{1F3FB}-\u{1F3FF}])?(?:\u200D[\u2600-\u27BF\u{1F000}-\u{1FAFF}]\uFE0F?)*|\uFE0F|\u20E3)[ \u00A0]?/gu;
  var SEL = "body > header, .top .t, .top .stars, nav#nav button, nav#nav a, nav.map a, header h1, header p, header .pill, header .stars, h1, h2, h3, h4, .btn, .pill, .stars, .tag, .badge, .t, .toast, .watch b, .card > .sub, section > .sub";
  var KEEP = ".opt, .q, .qtext, .stem, .prob .ptext, .question, .choices, .answer, svg, textarea, input, [data-sh-keep-emoji]";
  function clean(root) {
    (root.querySelectorAll ? root : document).querySelectorAll(SEL).forEach(function (el) {
      if (el.closest(KEEP)) return;
      var w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), n, list = [];
      while ((n = w.nextNode())) list.push(n);
      list.forEach(function (t) {
        if (t.parentElement && t.parentElement.closest(KEEP)) return;
        var v = t.nodeValue, nv = v.replace(RE, "");
        if (nv !== v) t.nodeValue = nv.replace(/^\s+(?=\S)/, function (s) { return t.previousSibling ? s : ""; });
      });
    });
  }
  var busy = false;
  function run() { if (busy) return; busy = true; requestAnimationFrame(function () { try { clean(document); } finally { busy = false; } }); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
  new MutationObserver(run).observe(document.documentElement, { childList: true, subtree: true });
})();
