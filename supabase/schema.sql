-- JarvisCyber cloud schema. Applied via Supabase SQL Editor on 2026-10-04.
-- Project: xflhofkqakxhagtbwycp
-- API secrets and OAuth refresh tokens must never be placed in payloads.
begin;

alter table public.gpt enable row level security;

create table public.jarvis_records (
  user_id uuid not null references auth.users(id) on delete cascade,
  id uuid not null default gen_random_uuid(),
  kind text not null check (kind in ('conversation','message','memory','settings','scan','cache')),
  payload jsonb not null check (jsonb_typeof(payload) = 'object' and octet_length(payload::text) <= 1048576),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  expires_at timestamptz,
  primary key (user_id, id)
);
create index jarvis_records_kind_time on public.jarvis_records (user_id, kind, created_at desc);
create index jarvis_records_expiry on public.jarvis_records (expires_at) where expires_at is not null;
alter table public.jarvis_records enable row level security;
revoke all on public.jarvis_records from anon;
grant select, insert, update, delete on public.jarvis_records to authenticated;
create policy jarvis_records_owner on public.jarvis_records
  for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

insert into storage.buckets (id, name, public, file_size_limit)
values ('jarvis-private', 'jarvis-private', false, 16777216);
create policy jarvis_private_owner on storage.objects
  for all to authenticated
  using (bucket_id = 'jarvis-private' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'jarvis-private' and (storage.foldername(name))[1] = (select auth.uid())::text);

commit;
