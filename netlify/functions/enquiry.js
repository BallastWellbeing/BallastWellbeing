// Training enquiry intake for the two segmented forms on /contact.
//
// Not Netlify Forms: those store submissions on US infrastructure and cap the
// free tier at 100 a month. This writes to the same ca-central-1 Supabase
// project as everything else, then sends the notification and the
// autoresponder with the relevant program overview PDF attached.
//
// Nothing here touches the counselling practice. Clinical intake goes through
// the practice management system and never reaches this codebase.

import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY,
  { auth: { persistSession: false } }
);

const SITE = process.env.URL || "https://ballastwellbeing.com";
const INBOX = "hello@ballastwellbeing.com";

const REQUIRED = {
  school: ["name", "role", "organization", "email", "school_type", "enrolment", "timeframe"],
  workplace: ["name", "role", "organization", "email", "sector", "headcount", "delivery", "timeframe"],
};

const OVERVIEW_PDF = {
  school: "ballast-schools-overview.pdf",
  workplace: "ballast-workplaces-overview.pdf",
};

const redirect = (path) => new Response(null, { status: 303, headers: { location: path } });

function autoresponderText(form) {
  const which = form === "school" ? "schools" : "workplace";
  return [
    "Thanks — we've got it. You'll hear back within one business day, usually sooner.",
    "If it's urgent, reply to this email directly.",
    "",
    `In the meantime, here's the ${which} program overview as a PDF — useful if you need to forward it to someone else.`,
    "",
    "— Ballast Wellbeing",
    "",
    "Ballast Wellbeing delivers training and education. We do not provide counselling, assessment, or treatment.",
  ].join("\n");
}

async function sendEmail(payload) {
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      authorization: `Bearer ${process.env.RESEND_API_KEY}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) console.error("email send failed", res.status, await res.text());
  return res.ok;
}

export default async (request) => {
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });

  const body = await request.formData();
  const form = String(body.get("form") || "");
  if (!REQUIRED[form]) return redirect("/contact?error=1");

  // Honeypot: bots fill every field they find.
  if (body.get("website")) return redirect("/contact/thanks");

  const get = (k) => {
    const v = body.get(k);
    return v == null ? null : String(v).trim().slice(0, 2000) || null;
  };

  const record = {
    form,
    name: get("name"),
    role: get("role"),
    organization: get("organization"),
    email: get("email"),
    phone: get("phone"),
    school_type: get("school_type"),
    enrolment: get("enrolment"),
    sector: get("sector"),
    headcount: get("headcount"),
    delivery: get("delivery"),
    interested_in: body.getAll("interested_in").map(String).slice(0, 10),
    timeframe: get("timeframe"),
    notes: get("notes"),
    program_slug: get("program_slug"),
  };

  for (const field of REQUIRED[form]) {
    if (!record[field]) return redirect("/contact?error=1");
  }
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(record.email)) return redirect("/contact?error=1");

  const { error } = await supabase.from("enquiries").insert(record);
  if (error) {
    // Never lose an enquiry to a database problem. Mail it through anyway and
    // let a human sort it out.
    console.error("enquiry insert failed", error);
  }

  const summary = Object.entries(record)
    .filter(([, v]) => v != null && String(v).length)
    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`)
    .join("\n");

  await sendEmail({
    from: `Ballast Wellbeing <${INBOX}>`,
    to: [INBOX],
    reply_to: record.email,
    subject: `New ${form} enquiry — ${record.organization}`,
    text: summary + (error ? "\n\n[WARNING] Database insert failed; this email is the only copy." : ""),
  });

  // The PDF matters: buyers forward these internally, and that is how the
  // enquiry reaches the person who signs.
  let attachments = [];
  try {
    const pdf = await fetch(`${SITE}/static/pdf/${OVERVIEW_PDF[form]}`);
    if (pdf.ok) {
      const buf = Buffer.from(await pdf.arrayBuffer());
      attachments = [{ filename: OVERVIEW_PDF[form], content: buf.toString("base64") }];
    }
  } catch (e) {
    console.error("overview PDF unavailable", e);
  }

  await sendEmail({
    from: `Ballast Wellbeing <${INBOX}>`,
    to: [record.email],
    subject: "Thanks — we've got your enquiry",
    text: autoresponderText(form),
    attachments,
  });

  return redirect("/contact/thanks");
};

export const config = { path: "/api/enquiry" };
