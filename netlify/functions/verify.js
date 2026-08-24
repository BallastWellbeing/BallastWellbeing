// Certificate lookup for /verify.
//
// The browser never talks to Supabase. This function holds the service key,
// rate limits by hashed IP, and returns only the fields the page shows. That
// matters because the table holds participant names: an unthrottled public
// endpoint over guessable serials is a name-harvesting tool.

import { createClient } from "@supabase/supabase-js";
import { createHash } from "node:crypto";

const SERIAL_RE = /^BW-\d{4}-\d{4}-[A-HJ-NP-Z2-9]{4}$/;
const WINDOW_MINUTES = 10;
const MAX_ATTEMPTS = 12;

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY,
  { auth: { persistSession: false } }
);

const json = (status, body) => new Response(JSON.stringify(body), {
  status,
  headers: {
    "content-type": "application/json",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
  },
});

// Not-found and revoked deliberately return the same message. Distinguishing
// them would confirm that a serial exists, which is exactly the signal an
// enumeration attempt is looking for.
const NOT_FOUND = {
  found: false,
  message:
    "No certificate found for that serial number. Check the number and try again. " +
    "If it still doesn't verify, email hello@ballastwellbeing.com.",
};

export default async (request, context) => {
  if (request.method !== "POST") return json(405, { error: "Method not allowed" });

  let serial;
  try {
    ({ serial } = await request.json());
  } catch {
    return json(400, { error: "Malformed request." });
  }

  serial = String(serial ?? "").trim().toUpperCase();

  // Reject anything that isn't a well-formed serial before touching the
  // database. Cheap, and it keeps the rate limit budget for real attempts.
  if (!SERIAL_RE.test(serial)) return json(200, NOT_FOUND);

  // Hash the IP with a server-side secret. We need to count attempts, not
  // know who made them, and storing raw addresses would make this table a
  // small privacy liability of its own.
  const ipHash = createHash("sha256")
    .update((context.ip ?? "unknown") + (process.env.IP_HASH_SALT ?? ""))
    .digest("hex");

  const since = new Date(Date.now() - WINDOW_MINUTES * 60_000).toISOString();
  const { count } = await supabase
    .from("verify_attempts")
    .select("*", { count: "exact", head: true })
    .eq("ip_hash", ipHash)
    .gte("attempted_at", since);

  if ((count ?? 0) >= MAX_ATTEMPTS) {
    return json(429, {
      found: false,
      message:
        "Too many lookups from this connection. Wait a few minutes and try again, " +
        "or email hello@ballastwellbeing.com.",
    });
  }

  await supabase.from("verify_attempts").insert({ ip_hash: ipHash });

  const { data, error } = await supabase
    .from("certificates")
    .select("serial, participant_name, program_title, contact_hours, issue_date, expiry_date, status")
    .eq("serial", serial)
    .maybeSingle();

  if (error) return json(500, { error: "Lookup temporarily unavailable." });
  if (!data || data.status !== "valid") return json(200, NOT_FOUND);

  return json(200, {
    found: true,
    participant_name: data.participant_name,
    program_title: data.program_title,
    contact_hours: data.contact_hours,
    issue_date: data.issue_date,
    expiry_date: data.expiry_date, // null renders no "Valid until" line
  });
};

export const config = { path: "/api/verify" };
