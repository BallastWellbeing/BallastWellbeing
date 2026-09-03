// Email capture at the foot of each article.
//
// The form on the page posts here directly (no JavaScript required), so this
// has to redirect on both success and failure rather than return JSON.
//
// Consent scope matters: an address collected here is for article updates only.
// It is deliberately kept in a separate table from `enquiries` so the two
// consents can never be quietly merged.

import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY,
  { auth: { persistSession: false } }
);

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const redirect = (path) => new Response(null, { status: 303, headers: { location: path } });

// The page's own form always posts form-encoded data. Anything else — a
// scanner, a bot probing with JSON — used to throw inside request.formData(),
// which Netlify surfaced as a 502 carrying a Node stack trace. Found by
// posting JSON at the live endpoint. Answer those plainly instead: nothing
// here owes an explanation to a caller that isn't the form.
async function readForm(request) {
  try {
    return await request.formData();
  } catch {
    return null;
  }
}

export default async (request) => {
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });

  const body = await readForm(request);
  if (!body) return new Response("Expected form data", { status: 400 });

  // Send the visitor back to the article they were reading. Must be a
  // same-site absolute path: anything else is an open-redirect vector.
  const raw = String(body.get("return_to") || "/insights");
  const back = /^\/[A-Za-z0-9\-._~/]*$/.test(raw) && !raw.startsWith("//")
    ? raw : "/insights";

  // Honeypot.
  if (body.get("website")) return redirect(`${back}?subscribed=1`);

  const email = String(body.get("email") || "").trim().toLowerCase().slice(0, 320);
  if (!EMAIL_RE.test(email)) return redirect(`${back}?error=email`);

  // onConflict so a repeat subscribe is idempotent rather than an error, and
  // so re-subscribing after an unsubscribe clears the flag.
  const { error } = await supabase
    .from("subscribers")
    .upsert({ email, unsubscribed_at: null }, { onConflict: "email" });

  if (error) {
    console.error("subscribe failed", error);
    return redirect(`${back}?error=1`);
  }
  return redirect(`${back}?subscribed=1`);
};

export const config = { path: "/api/subscribe" };
