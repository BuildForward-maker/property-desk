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

**There is no claim any more, and that is the point.** An earlier version let a
signed-in person add themselves to a workspace that had no members yet, once,
which was how pre-accounts rows were carried across. That migration is done and
the clause is gone: **a workspace code grants nothing**, and the only way into a
workspace is an existing member adding you by email.

**If you ran the earlier block, re-run this one.** Deleting the claim box from
the app changes nothing on its own: the anon key is public by design, so anyone
could still have inserted into `workspace_members` from a console for as long as
the `ws_unclaimed()` arm of `wm_insert` was there. The guarantee lives in these
policies, not in the UI.

**The trap in removing it**, written down because it is not obvious: that same
clause was what let a *new* account create its first workspace. Drop it on its
own and nobody can ever sign up again. Creation moves server-side instead, into
`create_workspace()`, which generates the code itself so there is nothing for a
caller to choose. Until you run this, the app falls back to the old client-side
insert and says so in Settings.

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

-- The workspace is generated here, not chosen by the caller. This replaces
-- the ws_unclaimed() claim, which was both the migration door and the only
-- way a new account could bootstrap itself.
drop function if exists ws_unclaimed(text);

create or replace function create_workspace() returns text
language plpgsql security definer set search_path = public as $$
declare w text;
begin
  if auth.uid() is null then raise exception 'not signed in'; end if;
  w := encode(gen_random_bytes(9), 'hex');
  insert into workspace_members(workspace, user_id, role)
    values (w, auth.uid(), 'owner');
  return w;
end $$;
revoke all on function create_workspace() from public;
grant execute on function create_workspace() to authenticated;

-- Who is in this workspace. profiles_self below means a member can read the
-- uuids in workspace_members and learn nothing about whose they are, so the
-- list has to be a definer function, gated on the caller already being in.
create or replace function workspace_people(w text)
returns table(id uuid, email text, name text, role text)
language sql security definer stable set search_path = public as $$
  select p.id, p.email, p.name, m.role
    from workspace_members m join profiles p on p.id = m.user_id
   where m.workspace = w and is_member(w)
   order by m.created_at;
$$;
revoke all on function workspace_people(text) from public;
grant execute on function workspace_people(text) to authenticated;

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
-- One rule, and it is the whole access model: only a member may add anybody,
-- including themselves. A code on its own is a name, not a key.
create policy wm_insert on workspace_members for insert
  with check (is_member(workspace));
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

### Carrying rows from before accounts

There is no claim flow in the app any more, so this is a SQL job and it is
deliberately not one anybody can do from the browser. Find the workspace code
in your old `#cfg=` link, sign in once so you have a user id, then:

```sql
insert into workspace_members (workspace, user_id, role)
select 'your-old-code', id, 'owner' from auth.users where email = 'you@example.com';
```

Everything keyed to that workspace is yours again. Anyone you want beside you
goes in through **Settings → Share with someone**, not through this.

## 2d. What the admin view still wants

Two columns the app renders around rather than inventing. Both are optional;
without them the People table shows a dash and "mark as read" is kept per
workspace instead of per row.

```sql
-- so "last seen" is a date rather than a dash
alter table profiles add column if not exists last_seen timestamptz;

-- so a read flag belongs to the row rather than to a preferences blob
alter table feedback add column if not exists read boolean default false;
```

Promotion is deliberate and has no button anywhere in the app:

```sql
update profiles set role = 'admin' where email = 'you@example.com';
```

## 2c. The two values in the file

Near the top of the script, `SB_URL` and `SB_KEY` name the backend this copy
talks to. **They are already set**, to project `xhzdnetooocjqumqjvun`. That is
what makes the published address show a sign-in screen; emptying them puts the
app back to local mode for anyone without a `#cfg` link.

Change them only when pointing a fork at a different project. Check any key
you paste before you commit it: decode the middle segment and confirm
`"role":"anon"` and that `ref` matches the project ref in the URL.

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

**1. Your existing rows.** If you had a workspace before accounts, run the
insert under "Carrying rows from before accounts" above, then open your old
`#cfg=` link and sign in.
→ *Look for:* your tracked flats, exactly as they were. If the board is empty,
do not add anything: check the code in the insert against your old link first.

**2. The magic link itself.** Sign out, then sign in again with the same
address.
→ *Look for:* the mail arrives within a minute; opening it lands you back in
the app signed in, and the address bar reads `#cfg=` and not `?cfg=`.

**3. A brand-new account.** Use a second address you control. Sign in and fill
in the profile.
→ *Look for:* an empty board, Settings showing a workspace code that is not
your first one, and your first account's flats nowhere in it. The code is
generated by `create_workspace()` and is hex; a code in the old dashed
letter-groups means the function is missing and the app fell back.

**3b. A code is not a key.** Still signed in as the second account, open the
browser console and run:

```js
await supabase.createClient(SB_URL, SB_KEY).from('workspace_members')
  .insert({workspace:'your-first-accounts-code', user_id:'<this account id>'});
```

→ *Look for:* a row-level security error. If it succeeds, `wm_insert` still
carries the `ws_unclaimed()` arm and the block in 2b has not been re-run.

**4. The wall.** While signed in as the second account, paste your **first**
account's full `#cfg=` link into the address bar and reload.
→ *Look for:* "This workspace is not shared with you." Not an empty board, not
an error: that sentence. If you can read the first account's rows here, the
policies in 2b did not apply and nothing else in this list matters.

**5. Add by email.** Back as the first account, Settings → Add somebody by
email → the second account's address.
→ *Look for:* "Added." Then reload the second account on the first's link; the
flats are there.
→ *If it says no account uses that address* when you know one does, the
function is the thing to check, not the email. Signed out it answers
`PGRST202`, which is correct because it is granted to `authenticated` only;
signed in it must return a uuid. `grant execute on function
user_id_by_email(text) to authenticated;` is the line that does it.

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
- **A workspace code grants nothing.** It names a workspace; it is not a key.
  There is no claim, and a workspace with no members is unreachable rather
  than claimable. The only route in is an existing member adding you.
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
