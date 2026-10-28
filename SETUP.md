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

## 2b. Turn on accounts

The block above left every policy at `using (true)`, which means anyone holding
the link can read and write that workspace. This second block replaces that with
membership. Run it the same way, in SQL Editor.

**Read the claim rule before you run it.** Rows already in your tables are keyed
to a workspace and carry no user, so the moment these policies land, a workspace
with no member row is a workspace nobody can read. `ws_unclaimed()` is the door
back in: a signed-in person may add *themselves* to a workspace that has no
members yet, once. After that first claim the door shuts, and only an existing
member can add anybody else. The app puts this on the profile screen as
"Already using Property Desk? Enter your workspace code."

```sql
-- Property Desk: accounts. Run after the first block.

create table if not exists profiles (
  id         uuid primary key references auth.users on delete cascade,
  email      text,
  name       text,
  mobile     text,
  created_at timestamptz default now()
);

create table if not exists workspace_members (
  workspace  text not null,
  user_id    uuid not null references auth.users on delete cascade,
  role       text default 'member',
  created_at timestamptz default now(),
  primary key (workspace, user_id)
);

alter table profiles          enable row level security;
alter table workspace_members enable row level security;

-- security definer, so a policy on workspace_members can ask about
-- workspace_members without recursing into its own policy
create or replace function is_member(w text) returns boolean
language sql security definer stable set search_path = public as $$
  select exists (select 1 from workspace_members
                 where workspace = w and user_id = auth.uid());
$$;

create or replace function ws_unclaimed(w text) returns boolean
language sql security definer stable set search_path = public as $$
  select not exists (select 1 from workspace_members where workspace = w);
$$;

-- profiles: your own row, and nobody else's. There is deliberately no
-- select-by-email policy: one would hand every name and mobile in the table
-- to anyone with an account, to find a single uuid.
drop policy if exists profiles_self   on profiles;
drop policy if exists profiles_lookup on profiles;
create policy profiles_self on profiles for all
  using (id = auth.uid()) with check (id = auth.uid());

-- "Add by email" asks this instead. It returns a uuid or null and nothing
-- else, so an address that is not here leaks nothing and an address that is
-- leaks only that it exists.
create or replace function user_id_by_email(email text) returns uuid
language sql security definer stable set search_path = public as $$
  select id from profiles where lower(profiles.email) = lower(user_id_by_email.email) limit 1;
$$;
revoke all on function user_id_by_email(text) from public;
grant execute on function user_id_by_email(text) to authenticated;

-- membership
drop policy if exists wm_select on workspace_members;
drop policy if exists wm_insert on workspace_members;
drop policy if exists wm_delete on workspace_members;
create policy wm_select on workspace_members for select
  using (user_id = auth.uid() or is_member(workspace));
create policy wm_insert on workspace_members for insert
  with check (
    (user_id = auth.uid() and ws_unclaimed(workspace))  -- the one-time claim
    or is_member(workspace)                              -- adding a partner
  );
create policy wm_delete on workspace_members for delete
  using (user_id = auth.uid() or is_member(workspace));

-- the five data tables: membership decides, not the link
drop policy if exists desk_tracking_all on desk_tracking;
drop policy if exists desk_checks_all   on desk_checks;
drop policy if exists desk_photos_all   on desk_photos;
drop policy if exists desk_activity_all on desk_activity;
drop policy if exists desk_prefs_all    on desk_prefs;

create policy desk_tracking_members on desk_tracking for all
  using (is_member(workspace)) with check (is_member(workspace));
create policy desk_checks_members   on desk_checks   for all
  using (is_member(workspace)) with check (is_member(workspace));
create policy desk_photos_members   on desk_photos   for all
  using (is_member(workspace)) with check (is_member(workspace));
create policy desk_activity_members on desk_activity for all
  using (is_member(workspace)) with check (is_member(workspace));
create policy desk_prefs_members    on desk_prefs    for all
  using (is_member(workspace)) with check (is_member(workspace));
```

Then, in **Authentication → Providers**, make sure **Email** is on and
**Confirm email** is on; that is what makes the magic link a magic link. In
**Authentication → URL Configuration**, add the address you published the file
at to **Redirect URLs**, or the link will bounce.

### Claim your existing workspace first

If you were already using this before accounts, do this before anything else:

1. Open your old link, the one with `#cfg=` in it.
2. Sign in with your email.
3. On the profile screen, your workspace code is already filled in. Press
   **Claim this workspace**.
4. Everything you had tracked is there.

If you skip it and sign in anyway, the app gives you a fresh empty workspace,
and the old one sits unclaimed until you enter its code under
**Settings → Claim another workspace**. Nothing is deleted either way.

## 2c. Put the two values in the file

Open `index.html`, find these two lines near the top of the script, and paste
your Project URL and **anon** key in:

```js
const SB_URL='';   /* https://<project-ref>.supabase.co */
const SB_KEY='';   /* the anon public key, the long one starting eyJ */
```

That is what makes the published address show a sign-in screen. Leave them
empty and the app behaves as it did before accounts: local mode for anyone
without a `#cfg` link.

**The anon key belongs in the page.** It is not an admin key, it cannot drop a
table, and the policies in 2b decide what it can reach. The `service_role` key
is the opposite: it ignores every policy and must never go in this file.

A `#cfg` link still wins over these constants, so links already sent keep
working, including ones pointing at a different project.

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

Nine steps, in this order. Each one names the single thing to look at; if that
thing is not there, stop there rather than carrying on.

**1. Claim your existing workspace.** Open your old `#cfg=` link. Sign in with
your email. On the profile screen the workspace code is already filled in.
Press **Claim this workspace**.
→ *Look for:* your tracked flats, exactly as they were. If the board is empty,
do not add anything: check the code against your old link first.

**2. The magic link itself.** Sign out, then sign in again with the same
address.
→ *Look for:* the mail arrives within a minute; opening it lands you back in
the app signed in, and the address bar reads `#cfg=` and not `?cfg=`.

**3. A brand-new account.** Use a second address you control. Sign in, fill in
the profile, do **not** claim anything.
→ *Look for:* an empty board, Settings showing a workspace code that is not
your first one, and your first account's flats nowhere in it.

**4. The wall.** While signed in as the second account, paste your **first**
account's full `#cfg=` link into the address bar and reload.
→ *Look for:* "This workspace is not shared with you." Not an empty board, not
an error: that sentence. If you can read the first account's rows here, the
policies in 2b did not apply and nothing else in this list matters.

**5. Add by email.** Back as the first account, Settings → Add somebody by
email → the second account's address.
→ *Look for:* "Added." Then reload the second account on the first's link; the
flats are there.

**6. Add somebody who does not exist.** Same box, an address nobody has signed
in with.
→ *Look for:* "No account here uses that address." And check Supabase →
Authentication → Users: that address must **not** have appeared.

**7. Signed-out local mode.** Sign out and stay on the sign-in screen, then
press **Browse without an account**.
→ *Look for:* the whole app, a badge reading local mode, and tracking a flat
that survives a reload. Nothing in the console.

**8. No backend at all.** Open `index.html` straight from your filesystem,
with no link.
→ *Look for:* no sign-in screen at all, and Settings saying this copy has no
workspace in its link.

**9. Deletion.** Settings → Export everything as JSON, then ask for your
profile row to be deleted.
→ *Look for:* the export arriving before anything is removed.

## What you are building

A free Supabase project Supabase gives you a Postgres database and file storage on a free tier that is far more than this needs. It is the database; you never have to look at it again after setup. This file, hosted Dropped onto Netlify or Cloudflare, it becomes a real web address. Both of you open the same address on phone or laptop. One link that carries the settings The generator at the bottom builds a link with the connection details inside it. Your partner opens it and is connected — nothing to install or configure at their end.

## What your partner sees, and who did what

Every change writes to a shared activity feed so neither of you has to ask what the other has already looked at. Nothing yet. Connect a workspace and changes will appear here.

## Being honest about the security model

The anon key is meant to be public. It is designed to sit in a web page, it is
not an admin key, and it cannot drop your tables. What used to be wrong was the
policies beside it: `using (true)` meant the link *was* the credential, and
anyone it was forwarded to could read and write.

With the block in 2b, that is no longer true:

- **Membership decides, not the link.** A link names a workspace. A signed-in
  person who is not a member of it is told so and sees nothing.
- **There is no password to steal**, because there is not one. A magic link is
  single use and expires in an hour.
- **An unclaimed workspace can be claimed once**, by whoever holds its code.
  That is the door that lets your existing data through, and it shuts the
  moment the first member exists.
- **Nobody is signed up on somebody else's behalf.** Adding a partner by email
  only works if that address already has an account.

What is still worth knowing:

- The session token lives in this browser's local storage, the way every web
  app's does. Signing out clears it.
- The magic link arrives in email, so the security of the account is the
  security of the mailbox.
- Do not put a PAN, bank details or scanned documents in here. Notes about
  flats, yes. Identity documents, no. That is a judgement about what this is
  for, not about the policies.
- **Never put the `service_role` key in this file.** It ignores every policy
  above.

To wipe a workspace, run `delete from desk_tracking where workspace =
'your-code';` and the same for the other four tables, then
`delete from workspace_members where workspace = 'your-code';`.

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

The anon key is meant to be public and is safe in the page **because** the
policies in 2b check membership. It was not safe before them, when any holder
of the link could read and write. Never put the `service_role` key in this
file: it bypasses every policy.
