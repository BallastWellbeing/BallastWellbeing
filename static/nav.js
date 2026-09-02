/* Mobile navigation disclosure.
   Progressive enhancement: with JS off the nav renders as a plain list and
   everything stays reachable, so nothing is lost. */
(function () {
  var btn = document.querySelector(".nav-toggle");
  var nav = document.getElementById("primary-nav");
  if (!btn || !nav) return;

  // The .js class is set by an inline script in <head>, not here — adding it
  // from a deferred script meant the nav rendered expanded and then collapsed.
  document.documentElement.classList.add("js");

  function setOpen(open) {
    btn.setAttribute("aria-expanded", String(open));
    nav.classList.toggle("is-open", open);
  }

  btn.addEventListener("click", function () {
    setOpen(btn.getAttribute("aria-expanded") !== "true");
  });

  // Escape closes and returns focus to the trigger. Listener is on the
  // document, not the nav: after clicking the toggle, focus sits on the button,
  // which is outside the nav, so a nav-scoped listener never fired.
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && btn.getAttribute("aria-expanded") === "true") {
      setOpen(false);
      btn.focus();
    }
  });

  // A click outside the open menu closes it, which is what people expect.
  document.addEventListener("click", function (e) {
    if (btn.getAttribute("aria-expanded") !== "true") return;
    if (nav.contains(e.target) || btn.contains(e.target)) return;
    setOpen(false);
  });

  // Reset state when the layout crosses back to the desktop breakpoint,
  // otherwise the menu can be left hidden with aria-expanded stale.
  // Must match the collapse breakpoint in base.css (76rem). See the comment
  // there for how that number was measured.
  var mq = window.matchMedia("(min-width: 76rem)");
  (mq.addEventListener ? mq.addEventListener.bind(mq, "change") : mq.addListener.bind(mq))(function () {
    if (mq.matches) setOpen(false);
  });
})();
