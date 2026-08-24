-- Ballast Wellbeing — database schema
-- Supabase project must be created in the ca-central-1 (Montreal) region.

-- ===========================================================================
-- Certificates
-- ===========================================================================
create table if not exists public.certificates (
  serial           text primary key,
  participant_name text        not null,
  program_title    text        not null,
  contact_hours    numeric(4,1) not null,
  issue_date       date        not null,
  expiry_date      date,                 -- null = does not expire (the norm).
  status           text        not null default 'valid'
                   check (status in ('valid','revoked')),
  created_at       timestamptz not null default now()
);

comment on column public.certificates.expiry_date is
  'Null for an ordinary certificate of completion, which does not expire. Set '
  'only for programs with a genuine refresh interval. The page hides the '
  '"Valid until" line entirely when this is null.';

-- Serial format: BW-YYYY-NNNN-XXXX where XXXX is four random characters.
-- The random suffix is the whole point: without it the serials are sequential
-- and anyone can walk them from 0001 upward and harvest every participant
-- name the business has ever issued.
alter table public.certificates drop constraint if exists certificates_serial_format;
alter table public.certificates add constraint certificates_serial_format
  check (serial ~ '^BW-[0-9]{4}-[0-9]{4}-[A-HJ-NP-Z2-9]{4}$');

-- Row level security: nothing reads this table directly from a browser.
-- The lookup goes through a Netlify Function holding the service key, which
-- rate limits and returns only the fields the page displays.
alter table public.certificates enable row level security;
revoke all on public.certificates from anon, authenticated;

-- ===========================================================================
-- Training enquiries (schools + workplaces)
-- Business contact information, not health information. Kept in ca-central-1
-- alongside everything else rather than in a US form service.
-- ===========================================================================
create table if not exists public.enquiries (
  id                uuid primary key default gen_random_uuid(),
  form              text not null check (form in ('school','workplace')),
  name              text not null,
  role              text not null,
  organization      text not null,   -- school name or organization name
  email             text not null,
  phone             text,
  -- school-only
  school_type       text,
  enrolment         text,
  -- workplace-only
  sector            text,
  headcount         text,
  delivery          text,
  -- both
  interested_in     text[] not null default '{}',
  timeframe         text not null,
  notes             text,
  program_slug      text,             -- set by /contact?program=[slug]
  created_at        timestamptz not null default now()
);

alter table public.enquiries enable row level security;
revoke all on public.enquiries from anon, authenticated;

create index if not exists enquiries_created_at_idx on public.enquiries (created_at desc);

-- ===========================================================================
-- Article subscribers
-- Separate table from `enquiries` on purpose: these are two different consents
-- and must not be merged. Sending article updates to an enquiry address, or
-- vice versa, is exactly what the privacy policy promises does not happen.
-- ===========================================================================
create table if not exists public.subscribers (
  email           text primary key,
  subscribed_at   timestamptz not null default now(),
  unsubscribed_at timestamptz
);

alter table public.subscribers enable row level security;
revoke all on public.subscribers from anon, authenticated;

-- ===========================================================================
-- Rate limiting for the public certificate lookup
-- ===========================================================================
create table if not exists public.verify_attempts (
  ip_hash    text        not null,
  attempted_at timestamptz not null default now()
);
create index if not exists verify_attempts_idx on public.verify_attempts (ip_hash, attempted_at desc);
alter table public.verify_attempts enable row level security;
revoke all on public.verify_attempts from anon, authenticated;

-- Housekeeping: attempts older than an hour are of no further use.
create or replace function public.prune_verify_attempts() returns void
language sql security definer set search_path = public as $$
  delete from public.verify_attempts where attempted_at < now() - interval '1 hour';
$$;
