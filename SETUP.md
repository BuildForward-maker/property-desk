# Setting up sharing

Property Desk works fully on its own — open `index.html` and everything runs in
your browser. You only need this if you want two people working from the same
data, with photos and notes syncing between you.

The connection form itself lives in the app, under **Settings** (the gear in the
sidebar, or `⌘K` → “Open settings”). These are the steps around it.

## 1. Create the Supabase project

Go to supabase.com , sign in with GitHub or email, and click New project. Name it anything. Choose the Mumbai or Singapore region so it is fast from Bengaluru. Set a database password and save it somewhere — you will not need it for this, but you will want it later. The project takes about two minutes to spin up.

## 2. Create the tables and the photo bucket

In the left sidebar open SQL Editor , click New query, paste the whole block below, and press Run. It creates five small tables, a public bucket for photos, and turns on live sync. You should see "Success. No rows returned."

```sql
-- Property Desk: run this whole block once in Supabase → SQL Editor → New query → Run

create table if not exists desk_tracking (
  workspace   text not null,
  prop_id     text not null,
  visit_status text default '',
  visit_date  date,
  notes       text default '',
  scores      jsonb default '{}'::jsonb,
  custom      jsonb,
  updated_by  text,
  updated_at  timestamptz default now(),
  primary key (workspace, prop_id)
);

create table if not exists desk_checks (
  workspace  text not null,
  item       int  not null,
  done       boolean default false,
  updated_by text,
  updated_at timestamptz default now(),
  primary key (workspace, item)
);

create table if not exists desk_photos (
  id          uuid primary key default gen_random_uuid(),
  workspace   text not null,
  prop_id     text not null,
  slot        text,
  path        text not null,
  url         text not null,
  uploaded_by text,
  created_at  timestamptz default now()
);

create table if not exists desk_prefs (
  workspace  text not null,
  k          text not null,
  v          jsonb default '{}'::jsonb,
  updated_by text,
  updated_at timestamptz default now(),
  primary key (workspace, k)
);

create table if not exists desk_activity (
  id         bigserial primary key,
  workspace  text not null,
  who        text,
  what       text,
  created_at timestamptz default now()
);

alter table desk_tracking enable row level security;
alter table desk_checks   enable row level security;
alter table desk_photos   enable row level security;
alter table desk_activity enable row level security;
alter table desk_prefs    enable row level security;

drop policy if exists desk_tracking_all on desk_tracking;
drop policy if exists desk_checks_all   on desk_checks;
drop policy if exists desk_photos_all   on desk_photos;
drop policy if exists desk_activity_all on desk_activity;
drop policy if exists desk_prefs_all    on desk_prefs;

create policy desk_tracking_all on desk_tracking for all using (true) with check (true);
create policy desk_checks_all   on desk_checks   for all using (true) with check (true);
create policy desk_photos_all   on desk_photos   for all using (true) with check (true);
create policy desk_activity_all on desk_activity for all using (true) with check (true);
create policy desk_prefs_all    on desk_prefs    for all using (true) with check (true);

-- storage bucket for photos
insert into storage.buckets (id, name, public)
values ('desk-photos','desk-photos', true)
on conflict (id) do nothing;

drop policy if exists desk_photos_read   on storage.objects;
drop policy if exists desk_photos_write  on storage.objects;
drop policy if exists desk_photos_delete on storage.objects;

create policy desk_photos_read  on storage.objects for select
  using (bucket_id = 'desk-photos');
create policy desk_photos_write on storage.objects for insert
  with check (bucket_id = 'desk-photos');
create policy desk_photos_delete on storage.objects for delete
  using (bucket_id = 'desk-photos');

-- live sync between you and your partner
alter publication supabase_realtime add table desk_tracking;
alter publication supabase_realtime add table desk_checks;
alter publication supabase_realtime add table desk_photos;
alter publication supabase_realtime add table desk_activity;
alter publication supabase_realtime add table desk_prefs;
```

## 3. Copy your two connection values

In the sidebar go to Project Settings → API . Copy the Project URL (looks like https://abcdefgh.supabase.co ) and the anon public key (a long string starting eyJ ). Paste both into the form in step 5. Do not use the service_role key — that one is an admin key and must never go in a web page.

## 4. Put this file on the web

Easiest: go to app.netlify.com/drop and drag this HTML file onto the page. You get a public address in about ten seconds without even making an account. Netlify will give it a random name; you can rename it in Site settings. More permanent: Cloudflare Pages or GitHub Pages. For GitHub Pages, make a repository, commit this file renamed to index.html , then turn Pages on under Settings → Pages. Free, and the address does not change.

## 5. Generate the shared link

Open **Settings** in the app and fill in the form there:

- **Supabase Project URL** and **anon public key** from step 3
- **Where you hosted it** — the public address, if you published it
- **Workspace code** — any shared secret; anyone with the link sees this workspace
- **Your name** — so the activity feed can attribute changes

Press **Connect this browser**, then send the generated link to the other person.

## 6. Check it works

The badge under the headline should read Shared workspace — live in green. Track a property, set a status, type a note. Open the same link on your phone; the note should already be there. Have your partner change a status and watch it appear on your screen without a refresh.

## What you are building

A free Supabase project Supabase gives you a Postgres database and file storage on a free tier that is far more than this needs. It is the database; you never have to look at it again after setup. This file, hosted Dropped onto Netlify or Cloudflare, it becomes a real web address. Both of you open the same address on phone or laptop. One link that carries the settings The generator at the bottom builds a link with the connection details inside it. Your partner opens it and is connected — nothing to install or configure at their end.

## What your partner sees, and who did what

Every change writes to a shared activity feed so neither of you has to ask what the other has already looked at. Nothing yet. Connect a workspace and changes will appear here.

## Being honest about the security model

The anon key is meant to be public — it is designed to sit in a web page. It is not an admin key and cannot drop your tables. But the policies above allow anyone who has your link to read and write. Protection comes from the workspace code being long and the link being private. That is fine for two people tracking flats. It is not fine for anything you would call confidential. Do not put your PAN, bank details, or scanned documents in here. Notes about flats, yes. Identity documents, no. If you want it properly locked down , turn on Supabase Auth with email sign-in and change the four policies from using (true) to using (auth.uid() is not null) . Then only people you invite can read anything. That is a thirty-minute job rather than a five-minute one. To wipe everything , run delete from desk_tracking where workspace = 'your-code'; and the same for the other four tables.

- The anon key is meant to be public — it is designed to sit in a web page. It is not an admin key and cannot drop your tables.
- But the policies above allow anyone who has your link to read and write. Protection comes from the workspace code being long and the link being private. That is fine for two people tracking flats. It is not fine for anything you would call confidential.
- Do not put your PAN, bank details, or scanned documents in here. Notes about flats, yes. Identity documents, no.
- If you want it properly locked down , turn on Supabase Auth with email sign-in and change the four policies from using (true) to using (auth.uid() is not null) . Then only people you invite can read anything. That is a thirty-minute job rather than a five-minute one.
- To wipe everything , run delete from desk_tracking where workspace = 'your-code'; and the same for the other four tables.

## If something does not work

Symptom Almost always Badge stays amber, "local mode" The URL or key is wrong, or the link lost its # portion. Some chat apps strip everything after the hash — send the link in a way that keeps it intact, or paste the values into the form directly. Badge is red, "connection failed" The SQL in step 2 was not run, or was run against a different project than the URL you pasted. Notes save but photos fail The storage bucket or its policies did not get created. Re-run the storage section of the SQL, and check Storage in the sidebar shows a desk-photos bucket marked public. Partner sees an empty dashboard Different workspace code. Compare the end of both links. Changes do not appear live Realtime was not enabled. Re-run the four alter publication lines. A refresh will still pull everything. Photos upload but do not display The bucket is not public. Storage → desk-photos → Settings → make public.

## Sharing the file itself

Sharing does not require Supabase at all. `index.html` is one self-contained
file: download it and send it over WhatsApp, email or AirDrop. It opens in any
browser, on any device, offline. Nothing installs and nothing phones home.

For a real web link, free: drag the file onto Netlify Drop for a public URL in
about ten seconds, no account needed. Cloudflare Pages or GitHub Pages if you
want something permanent — commit it as `index.html` and turn Pages on.

**Your notes and photos do not travel with the link.** Visit statuses, notes,
scores and images are stored against whoever is viewing, not inside the file.
That is exactly what the Supabase workspace above is for. To hand your working
state to one person without setting a workspace up, use **Export everything as
JSON** in Settings.

**Google Drive caveat.** Sharing an HTML file from Drive makes people download
it rather than view it. It works, it is just clumsier than Netlify Drop.

**Before you share with a broker,** note that the resale pricing model and the
negotiation brief are your side of the table. Send the shortlist, not the
playbook.

## Security, plainly

The anon key is meant to be public, but this schema lets anyone holding your
workspace code read and write that workspace's rows. Treat the link like a
shared password, and never put the `service_role` key in this file.
