/* /admin — writes an article and posts it to /api/publish.
   Vanilla, self-hosted, no dependencies: the privacy policy says this site
   loads no third-party script on any page, and a CMS bundle from a CDN would
   have made that false. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var form = $("admin-form");
  if (!form) return;

  var status = $("admin-status");
  var slugTouched = false;

  function say(text, kind) {
    status.textContent = text;
    status.className = "admin-status" + (kind ? " is-" + kind : "");
  }

  function slugify(s) {
    return s.toLowerCase()
      .replace(/[’'"]/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 70);
  }

  $("date").value = new Date().toISOString().slice(0, 10);

  $("title").addEventListener("input", function () {
    if (!slugTouched) $("slug").value = slugify(this.value);
  });
  $("slug").addEventListener("input", function () { slugTouched = true; });

  $("body").addEventListener("input", function () {
    var n = this.value.trim().split(/\s+/).filter(Boolean).length;
    $("wordcount").textContent = n + (n === 1 ? " word" : " words") +
      " · about " + Math.max(1, Math.round(n / 200)) + " min read";
  });

  function post(payload) {
    payload.token = $("token").value;
    return fetch("/api/publish", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, data: d }; });
    });
  }

  // --- new vs edit --------------------------------------------------------
  var loaded = false;
  form.addEventListener("change", function (e) {
    if (e.target.name !== "mode") return;
    var editing = e.target.value === "edit";
    $("existing-wrap").hidden = !editing;
    if (editing && !loaded) {
      if (!$("token").value) { say("Enter the publishing password first.", "error"); return; }
      say("Loading your articles…");
      post({ action: "list" }).then(function (r) {
        if (!r.ok) { say(r.data.error || "Could not load the list.", "error"); return; }
        var sel = $("existing");
        sel.innerHTML = '<option value="">Choose an article</option>';
        r.data.articles.forEach(function (a) {
          var o = document.createElement("option");
          o.value = a.slug; o.textContent = a.slug;
          sel.appendChild(o);
        });
        loaded = true;
        say("");
      });
    }
  });

  // Frontmatter is a fixed shape written by the function, so a small parser is
  // enough here and avoids shipping a YAML library to do nine keys.
  function parseArticle(text) {
    var m = text.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
    if (!m) return null;
    var meta = {};
    m[1].split("\n").forEach(function (line) {
      var kv = line.match(/^([a-z_]+):\s*(.*)$/);
      if (!kv) return;
      var v = kv[2].trim();
      if (v.charAt(0) === '"' && v.charAt(v.length - 1) === '"') {
        v = v.slice(1, -1).replace(/\\"/g, '"').replace(/\\\\/g, "\\");
      }
      meta[kv[1]] = v;
    });
    meta.body = m[2];
    return meta;
  }

  $("existing").addEventListener("change", function () {
    if (!this.value) return;
    say("Loading…");
    post({ action: "load", slug: this.value }).then(function (r) {
      if (!r.ok) { say(r.data.error || "Could not load it.", "error"); return; }
      var a = parseArticle(r.data.content);
      if (!a) { say("That file isn't in the expected format.", "error"); return; }
      ["title", "slug", "category", "date", "standfirst", "seo_title",
       "seo_description", "cta_text", "cta_label", "cta_url"].forEach(function (k) {
        if ($(k) && a[k] != null) $(k).value = a[k];
      });
      $("body").value = a.body.trim();
      $("body").dispatchEvent(new Event("input"));
      $("overwrite").checked = true;
      slugTouched = true;
      say("Loaded. Edit and publish when you're ready.", "ok");
    });
  });

  // --- publish ------------------------------------------------------------
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var required = ["token", "title", "slug", "standfirst", "body"];
    for (var i = 0; i < required.length; i++) {
      if (!$(required[i]).value.trim()) {
        say("Still needed: " + required[i].replace("_", " ") + ".", "error");
        $(required[i]).focus();
        return;
      }
    }
    var btn = $("publish");
    btn.disabled = true;
    say("Publishing…");
    post({
      action: "publish",
      title: $("title").value, slug: $("slug").value,
      category: $("category").value, date: $("date").value,
      standfirst: $("standfirst").value, body: $("body").value,
      seo_title: $("seo_title").value, seo_description: $("seo_description").value,
      cta_text: $("cta_text").value, cta_label: $("cta_label").value,
      cta_url: $("cta_url").value, overwrite: $("overwrite").checked
    }).then(function (r) {
      btn.disabled = false;
      if (!r.ok) { say(r.data.error || "Something went wrong.", "error"); return; }
      say(r.data.message + " It will appear at " + r.data.url, "ok");
    }).catch(function () {
      btn.disabled = false;
      say("Could not reach the server. Check your connection and try again.", "error");
    });
  });
})();
