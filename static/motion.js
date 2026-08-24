/* Motion controller.
 *
 * Adds `motion` to <html> only when JS is running AND the visitor has not
 * asked for reduced motion. Every animated style in motion.css is scoped to
 * that class, so if this file never runs, or the visitor prefers reduced
 * motion, the page renders complete and static. Nothing is ever left hidden.
 */
(function () {
  var root = document.documentElement;
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");

  if (reduce.matches) return;   // static page, and that is a correct outcome
  root.classList.add("motion");

  // If the setting changes mid-session, drop everything immediately.
  var onChange = function () {
    if (reduce.matches) {
      root.classList.remove("motion");
      document.querySelectorAll("[data-reveal]").forEach(function (el) {
        el.classList.add("is-in");
      });
    } else {
      root.classList.add("motion");
    }
  };
  if (reduce.addEventListener) reduce.addEventListener("change", onChange);

  // ---- Scroll reveal ------------------------------------------------------
  // Common patterns are tagged here rather than in the templates, so the
  // markup stays clean and a no-JS visitor gets plain HTML with no leftover
  // attributes. Explicit data-reveal in a template still works and takes
  // precedence for anything needing bespoke ordering.
  var AUTO = [
    ".section > .container > h2", ".section-lg > .container > h2",
    ".section > .container-tight > h2", ".section-lg > .container-tight > h2",
    ".card", ".track-card", ".rate-card", ".stat", ".source",
    ".credibility > div", ".article-list > li",
    ".quick-facts dl > div", ".program-body > section",
    ".clinical-body > section", ".hub-body > section", ".approach-body > section",
    ".legal-body > section", ".crisis", ".practitioner", ".built-on",
    ".email-capture", ".table-scroll", ".about-portrait", ".about-copy > *"
  ].join(",");

  document.querySelectorAll(AUTO).forEach(function (el) {
    if (!el.hasAttribute("data-reveal") && !el.closest(".hero")) {
      el.setAttribute("data-reveal", "");
    }
  });

  var revealables = [].slice.call(document.querySelectorAll("[data-reveal]"));

  // Anything already in the first screenful reveals immediately, so the page
  // is never blank above the fold while waiting for a scroll event.
  var show = function (el) { el.classList.add("is-in"); };

  if (!("IntersectionObserver" in window)) {
    revealables.forEach(show);
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        show(entry.target);
        io.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.01 });

    revealables.forEach(function (el, i) {
      // Stagger within a group of siblings.
      var sibs = el.parentElement ? el.parentElement.children : [el];
      var idx = [].indexOf.call(sibs, el);
      el.style.setProperty("--reveal-delay", Math.min(idx, 5) * 80 + "ms");
      el.style.setProperty("--i", idx);
      io.observe(el);
    });

    // Backstop: whatever happens, nothing stays hidden past 2 seconds.
    setTimeout(function () { revealables.forEach(show); }, 2000);
  }

  // ---- Header shadow once scrolled ---------------------------------------
  var header = document.querySelector(".site-header");
  if (header) {
    var onScroll = function () {
      header.classList.toggle("is-stuck", window.scrollY > 8);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  // ---- Hero mark ----------------------------------------------------------
  var hull = document.querySelector(".hull");
  var hero = document.querySelector(".hero-mark");

  if (hull && hero) {
    // Hand control from the load animation to the pointer once it finishes.
    hull.addEventListener("animationend", function (e) {
      if (e.animationName !== "hull-settle") return;
      hull.classList.remove("is-rocking");
      hull.classList.add("is-live");
    });

    // Pointer tilt. Fine pointers only: on touch there is no hover state and
    // the tilt would fire on the tap that is trying to scroll.
    if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
      var frame = null;
      hero.closest("section").addEventListener("pointermove", function (e) {
        if (frame) return;
        frame = requestAnimationFrame(function () {
          frame = null;
          if (!hull.classList.contains("is-live")) return;
          var r = hero.getBoundingClientRect();
          var dx = (e.clientX - (r.left + r.width / 2)) / (window.innerWidth / 2);
          hull.style.setProperty("--tilt", (Math.max(-1, Math.min(1, dx)) * 3.5).toFixed(2) + "deg");
        });
      });
      hero.closest("section").addEventListener("pointerleave", function () {
        hull.style.setProperty("--tilt", "0deg");
      });
    }

    // Activating the mark rocks it again. It is a button, so this works from
    // the keyboard too, and it is labelled for screen readers.
    var trigger = document.querySelector(".hero-mark-button");
    if (trigger) {
      trigger.addEventListener("click", function () {
        hull.classList.remove("is-live");
        hull.style.setProperty("--tilt", "0deg");
        void hull.offsetWidth;            // restart the animation
        hull.classList.add("is-rocking");
      });
    }
  }

  // ---- Stat count-up ------------------------------------------------------
  // Figures are read from the rendered text ("27%" -> 27 with a "%" suffix),
  // so the markup carries the real number and a no-JS visitor sees it plainly.
  var stats = [].slice.call(document.querySelectorAll(".stat-figure"))
    .filter(function (el) { return /^\s*\d+\s*%?\s*$/.test(el.textContent); });

  if (stats.length && "IntersectionObserver" in window) {
    var so = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        so.unobserve(entry.target);
        var el = entry.target;
        var text = el.textContent.trim();
        var target = parseFloat(text);
        var suffix = text.indexOf("%") !== -1 ? "%" : "";
        // Reserve the final width so the row does not reflow while counting.
        el.style.minWidth = el.getBoundingClientRect().width + "px";
        el.style.display = "inline-block";
        var start = performance.now();
        var dur = 900;
        var step = function (now) {
          var t = Math.min(1, (now - start) / dur);
          var eased = 1 - Math.pow(1 - t, 3);
          el.textContent = Math.round(target * eased) + suffix;
          if (t < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
      });
    }, { threshold: 0.4 });
    stats.forEach(function (el) { so.observe(el); });
  }
})();
