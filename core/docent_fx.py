from __future__ import annotations
from pathlib import Path

# Extra CSS: glowing border + pulse on new docent text
EXTRA_CSS = r"""
<!-- V8 docent FX -->
<style>
  .docent-box {
    position: relative;
    box-shadow: 0 0 0 1px #00ff99;
    transition: box-shadow 0.4s ease-out;
  }
  .docent-box.docent-glow {
    animation: docentGlow 1.8s ease-out;
  }
  .docent-box.docent-pulse::after {
    content: "";
    position: absolute;
    right: 10px;
    top: 10px;
    width: 10px;
    height: 10px;
    border-radius: 999px;
    box-shadow: 0 0 0 0 rgba(0,255,153,0.9);
    animation: docentPulse 1.8s ease-out;
  }
  @keyframes docentGlow {
    0%   { box-shadow: 0 0 0 0 rgba(0,255,153,1); }
    100% { box-shadow: 0 0 25px 0 rgba(0,255,153,0); }
  }
  @keyframes docentPulse {
    0%   { transform: scale(1);   opacity: 1;   box-shadow: 0 0 0 0 rgba(0,255,153,0.7); }
    100% { transform: scale(2.2); opacity: 0;   box-shadow: 0 0 0 16px rgba(0,255,153,0); }
  }
</style>
"""

# Extra JS: TTS + camera auto-pan + [AI docent] tag
EXTRA_JS = r"""
<!-- V8 docent TTS + camera auto-pan -->
<script>
(function () {
  function injectLabels() {
    var nodes = Array.from(document.querySelectorAll("div,section"));
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!el.textContent) continue;
      var t = el.textContent.trim();
      if (t.indexOf("Block details") === 0) {
        el.dataset.sovBlockDetails = "1";
      }
      if (t.indexOf("AI docent note") === 0) {
        el.dataset.sovDocent = "1";
      }
    }
  }

  function findDocentBox() {
    var el = document.querySelector("[data-sov-docent='1']");
    if (el) return el;
    var cards = Array.from(document.querySelectorAll("div,section"));
    for (var i = 0; i < cards.length; i++) {
      var c = cards[i];
      if (c.textContent && c.textContent.indexOf("AI docent note") !== -1) {
        return c;
      }
    }
    return null;
  }

  function markHeightLabel() {
    var root = document.querySelector("[data-sov-block-details='1']") || document.body;
    var spans = root.querySelectorAll("strong,span");
    for (var i = 0; i < spans.length; i++) {
      var s = spans[i];
      if (!s.textContent) continue;
      var t = s.textContent.trim();
      if (t.indexOf("Height:") === 0 && t.indexOf("[AI docent]") === -1) {
        s.textContent = t + "  [AI docent]";
        break;
      }
    }
  }

  function speak(text) {
    if (!("speechSynthesis" in window)) return;
    try {
      window.speechSynthesis.cancel();
      var u = new SpeechSynthesisUtterance(text);
      u.rate = 0.95;
      u.pitch = 1.02;
      u.volume = 0.92;
      window.speechSynthesis.speak(u);
    } catch (e) {
      console.log("[docent-tts] error:", e);
    }
  }

  function onDocentChange(box) {
    if (!box) return;
    var raw = (box.innerText || box.textContent || "");
    var text = raw.replace(/^AI docent note\s*/i, "").trim();
    if (!text) return;

    box.classList.remove("docent-glow", "docent-pulse");
    void box.offsetWidth; // restart animation
    box.classList.add("docent-box", "docent-glow", "docent-pulse");

    try {
      box.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (e) {}

    speak(text);
  }

  function setupObserver() {
    injectLabels();
    markHeightLabel();
    var box = findDocentBox();
    if (!box) return;
    window.__sovDocentBox = box;

    var last = (box.innerText || "").trim();
    onDocentChange(box);

    var obs = new MutationObserver(function () {
      var current = (box.innerText || "").trim();
      if (!current || current === last) return;
      last = current;
      onDocentChange(box);
    });

    obs.observe(box, { childList: true, subtree: true, characterData: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupObserver);
  } else {
    setupObserver();
  }
})();
</script>
"""

def inject_docent_fx(out_path: Path) -> None:
  """Inject V8 CSS/JS into MESSAGE_MIRROR.html (idempotent)."""
  try:
    html = out_path.read_text(encoding="utf-8")
  except FileNotFoundError:
    return

  if "<!-- V8 docent FX -->" in html:
    # Already patched
    return

  if "</head>" in html:
    html = html.replace("</head>", EXTRA_CSS + "\n</head>", 1)
  else:
    html = EXTRA_CSS + html

  if "</body>" in html:
    html = html.replace("</body>", EXTRA_JS + "\n</body>", 1)
  else:
    html = html + EXTRA_JS

  out_path.write_text(html, encoding="utf-8")
