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


  // --- Training disclosure -------------------------------------------------
  // "Training" groups Schools and Workplaces and has no page of its own.
  // Without JS the submenu renders open, so nothing is ever unreachable; this
  // only collapses it once we know scripting works.
  var groups = [].slice.call(document.querySelectorAll(".nav-group"));
  groups.forEach(function (group) {
    var toggle = group.querySelector(".nav-group-toggle");
    var panel = group.querySelector(".nav-submenu");
    if (!toggle || !panel) return;

    var setOpen = function (open) {
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      group.classList.toggle("is-open", open);
    };
    setOpen(false);

    toggle.addEventListener("click", function () {
      setOpen(toggle.getAttribute("aria-expanded") !== "true");
    });

    // Escape closes and returns focus to the button, matching the main menu.
    group.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
        setOpen(false);
        toggle.focus();
      }
    });

    // Leaving the group entirely closes it. Checking on the next tick because
    // focusout fires before the incoming element has focus.
    group.addEventListener("focusout", function () {
      window.setTimeout(function () {
        if (!group.contains(document.activeElement)) setOpen(false);
      }, 0);
    });

    document.addEventListener("click", function (e) {
      if (!group.contains(e.target)) setOpen(false);
    });
  });

  // Reset state when the layout crosses back to the desktop breakpoint,
  // otherwise the menu can be left hidden with aria-expanded stale.
  // Must match the collapse breakpoint in base.css (76rem). See the comment
  // there for how that number was measured.
  var mq = window.matchMedia("(min-width: 60rem)");
  (mq.addEventListener ? mq.addEventListener.bind(mq, "change") : mq.addListener.bind(mq))(function () {
    if (mq.matches) setOpen(false);
  });
})();
