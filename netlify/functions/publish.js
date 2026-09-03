// Publish an article without git.
//
// Norman writes at /admin, this commits the Markdown to GitHub, and the push
// triggers the normal Netlify build. No CMS library, no third-party script on
// the domain, no OAuth app to register — the site's privacy policy says there
// is no third-party script on any page, and that stays true.
//
// Auth is a single shared token in ADMIN_TOKEN, compared in constant time and
// rate limited. That is proportionate for a one-person practice; it is not a
// multi-user permission system and does not pretend to be.
//
// Env: GITHUB_TOKEN (fine-grained PAT, Contents: read+write, this repo only)
//      GITHUB_REPO  ("BallastWellbeing/BallastWellbeing")
//      ADMIN_TOKEN  (long random string)

import { createClient } from "@supabase/supabase-js";
import { createHash, timingSafeEqual } from "node:crypto";

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY,
  { auth: { persistSession: false } }
);

const REPO = process.env.GITHUB_REPO || "";
const BRANCH = "main";
const DIR = "site/content/insights";
const CATEGORIES = ["Schools", "Workplaces", "Research"];
const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

const MAX_ATTEMPTS = 10;      // per window, per address
const WINDOW_MIN = 10;

const json = (status, body) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });

// Same length or not, comparison takes the same time. A plain === leaks the
// length of the token and, on some engines, the position of the first
// mismatching byte.
function tokenMatches(given) {
  const expected = process.env.ADMIN_TOKEN || "";
  if (!expected || expected.length < 24) return false;   // refuse a weak secret
  const a = createHash("sha256").update(String(given)).digest();
  const b = createHash("sha256").update(expected).digest();
  return timingSafeEqual(a, b);
}

// Reuses the verify_attempts table with a namespaced hash rather than adding a
// second table, so this needs no schema change to deploy.
async function rateLimited(context) {
  const since = new Date(Date.now() - WINDOW_MIN * 60_000).toISOString();
  const ipHash = "publish:" + createHash("sha256")
    .update((context.ip ?? "unknown") + (process.env.IP_HASH_SALT ?? ""))
    .digest("hex");
  const { count } = await supabase
    .from("verify_attempts")
    .select("*", { count: "exact", head: true })
    .eq("ip_hash", ipHash)
    .gte("attempted_at", since);
  await supabase.from("verify_attempts").insert({ ip_hash: ipHash });
  return (count ?? 0) >= MAX_ATTEMPTS;
}

async function gh(path, init = {}) {
  const res = await fetch(`https://api.github.com${path}`, {
    ...init,
    headers: {
      authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
      accept: "application/vnd.github+json",
      "user-agent": "ballast-publish",
      ...(init.headers || {}),
    },
  });
  return res;
}

function yamlString(s) {
  // Double-quoted with escapes: titles and standfirsts contain colons, commas
  // and apostrophes, all of which break a bare YAML scalar.
  return `"${String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function buildMarkdown(a) {
  const d = new Date(a.date + "T12:00:00Z");
  const display = d.toLocaleDateString("en-GB",
    { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  // ~200 wpm, rounded up, floor of 1 — matches how the existing articles read.
  const words = a.body.trim().split(/\s+/).filter(Boolean).length;
  const reading = Math.max(1, Math.round(words / 200));
  const lines = [
    "---",
    `title: ${yamlString(a.title)}`,
    `slug: ${a.slug}`,
    `category: ${a.category}`,
    `date: ${a.date}`,
    `date_display: ${yamlString(display)}`,
    `reading_time: ${reading}`,
    `standfirst: ${yamlString(a.standfirst)}`,
    `seo_title: ${yamlString(a.seo_title || a.title)}`,
    `seo_description: ${yamlString(a.seo_description || a.standfirst)}`,
  ];
  if (a.cta_text) lines.push(`cta_text: ${yamlString(a.cta_text)}`);
  if (a.cta_label) lines.push(`cta_label: ${yamlString(a.cta_label)}`);
  if (a.cta_url) lines.push(`cta_url: ${yamlString(a.cta_url)}`);
  lines.push("---", "", a.body.trim(), "");
  return lines.join("\n");
}

// The build fails the whole site on a character outside this set, so reject it
// here where the message can be useful rather than in a red deploy log.
const ALLOWED_NON_ASCII = new Set(
  "–—‘’“”·…éèêüöàç®©™ →✓×−".split(""));

function badCharacters(text) {
  const bad = new Set();
  for (const ch of text) {
    if (ch.codePointAt(0) > 127 && !ALLOWED_NON_ASCII.has(ch)) bad.add(ch);
  }
  return [...bad];
}

export default async (request, context) => {
  if (request.method !== "POST") return json(405, { error: "Method not allowed" });

  let payload;
  try {
    payload = await request.json();
  } catch {
    return json(400, { error: "Expected JSON" });
  }

  if (await rateLimited(context)) {
    return json(429, { error: "Too many attempts. Wait ten minutes." });
  }
  if (!tokenMatches(payload.token)) {
    return json(401, { error: "Wrong publishing password." });
  }
  if (!process.env.GITHUB_TOKEN || !REPO) {
    return json(500, { error: "Publishing is not configured: GITHUB_TOKEN and GITHUB_REPO are unset." });
  }

  const action = payload.action || "publish";

  if (action === "list") {
    const res = await gh(`/repos/${REPO}/contents/${DIR}?ref=${BRANCH}`);
    if (!res.ok) return json(502, { error: `GitHub said ${res.status}` });
    const files = await res.json();
    return json(200, {
      articles: files.filter((f) => f.name.endsWith(".md"))
                     .map((f) => ({ slug: f.name.replace(/\.md$/, ""), sha: f.sha })),
    });
  }

  if (action === "load") {
    const res = await gh(`/repos/${REPO}/contents/${DIR}/${payload.slug}.md?ref=${BRANCH}`);
    if (!res.ok) return json(404, { error: "No article with that name." });
    const file = await res.json();
    return json(200, {
      sha: file.sha,
      content: Buffer.from(file.content, "base64").toString("utf-8"),
    });
  }

  // --- publish ------------------------------------------------------------
  const a = {
    title: String(payload.title || "").trim(),
    slug: String(payload.slug || "").trim().toLowerCase(),
    category: String(payload.category || "").trim(),
    date: String(payload.date || "").trim(),
    standfirst: String(payload.standfirst || "").trim(),
    seo_title: String(payload.seo_title || "").trim(),
    seo_description: String(payload.seo_description || "").trim(),
    cta_text: String(payload.cta_text || "").trim(),
    cta_label: String(payload.cta_label || "").trim(),
    cta_url: String(payload.cta_url || "").trim(),
    body: String(payload.body || ""),
  };

  for (const f of ["title", "slug", "category", "date", "standfirst", "body"]) {
    if (!a[f]) return json(400, { error: `${f.replace("_", " ")} is required.` });
  }
  if (!SLUG_RE.test(a.slug)) {
    return json(400, { error: "The web address may use lowercase letters, numbers and hyphens only." });
  }
  if (!CATEGORIES.includes(a.category)) {
    return json(400, { error: `Category must be one of: ${CATEGORIES.join(", ")}` });
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(a.date) || Number.isNaN(Date.parse(a.date))) {
    return json(400, { error: "Date must be YYYY-MM-DD." });
  }
  if (a.cta_url && !/^\/[A-Za-z0-9\-._~/]*$/.test(a.cta_url)) {
    return json(400, { error: "The link must be a path on this site, starting with /" });
  }
  const bad = badCharacters(a.title + a.standfirst + a.body + a.seo_title + a.seo_description);
  if (bad.length) {
    return json(400, {
      error: `These characters would fail the build — usually a paste from Word: ${bad.join(" ")}`,
    });
  }

  const path = `${DIR}/${a.slug}.md`;
  // Look for an existing file: the contents API needs its sha to update rather
  // than to fail with 422.
  let sha;
  const existing = await gh(`/repos/${REPO}/contents/${path}?ref=${BRANCH}`);
  if (existing.ok) sha = (await existing.json()).sha;
  if (existing.ok && !payload.overwrite) {
    return json(409, {
      error: `An article already lives at /insights/${a.slug}. Tick "replace" to update it.`,
    });
  }

  const put = await gh(`/repos/${REPO}/contents/${path}`, {
    method: "PUT",
    body: JSON.stringify({
      message: `${sha ? "Update" : "Publish"} article: ${a.title}`,
      content: Buffer.from(buildMarkdown(a), "utf-8").toString("base64"),
      branch: BRANCH,
      ...(sha ? { sha } : {}),
    }),
  });
  if (!put.ok) {
    console.error("github publish failed", put.status, await put.text());
    return json(502, { error: `GitHub refused the change (${put.status}).` });
  }

  return json(200, {
    ok: true,
    updated: Boolean(sha),
    url: `/insights/${a.slug}`,
    message: sha
      ? "Updated. The site rebuilds in about a minute."
      : "Published. The site rebuilds in about a minute.",
  });
};

export const config = { path: "/api/publish" };
