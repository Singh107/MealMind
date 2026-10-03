-- Apply after 202609140001_account_storage.sql. No changes to existing policies.
begin;
create table public.pantry_items (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade,
 name text not null check (length(btrim(name)) between 1 and 120),
 normalized_name text not null check (length(normalized_name) between 1 and 240),
 food_state text,
 identity_status text not null check (identity_status in ('recognized', 'unresolved')),
 identity_key text not null check (identity_key ~ '^[a-f0-9]{64}$'),
 quantity double precision check (quantity > 0 and quantity <= 100000),
 unit text check (unit in ('g','kg','mg','oz','lb','ml','l','tsp','tbsp','cup',
                          'piece','clove','breast','egg','slice','large','medium','small')),
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique (user_id, identity_key)
);
create index pantry_items_user_date on public.pantry_items(user_id, created_at, id);
alter table public.pantry_items enable row level security;
alter table public.pantry_items force row level security;
revoke all on public.pantry_items from anon;
grant select, insert, update, delete on public.pantry_items to authenticated;
create policy own_select on public.pantry_items for select to authenticated using ((select auth.uid()) = user_id);
create policy own_insert on public.pantry_items for insert to authenticated with check ((select auth.uid()) = user_id);
create policy own_update on public.pantry_items for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy own_delete on public.pantry_items for delete to authenticated using ((select auth.uid()) = user_id);
create trigger set_updated_at before update on public.pantry_items for each row execute function public.mealmind_updated_at();
commit;
