-- One complete snapshot preserves intelligence and original/repaired relationships.
create table public.profiles (
 user_id uuid primary key references auth.users(id) on delete cascade,
 display_name text not null default '' check (length(display_name) <= 120),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table public.saved_recipes (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade,
 source_id text not null check (length(source_id) between 1 and 160),
 recipe jsonb not null check (jsonb_typeof(recipe) = 'object'),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(user_id, source_id)
);
create table public.user_preferences (
 user_id uuid primary key references auth.users(id) on delete cascade,
 dietary_preferences jsonb not null default '[]', allergies jsonb not null default '[]',
 excluded_ingredients jsonb not null default '[]', nutrition_targets jsonb not null default '{}',
 preferred_cuisines jsonb not null default '[]', cooking_preferences jsonb not null default '{}',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index saved_recipes_user_date on public.saved_recipes(user_id, created_at desc);
create function public.mealmind_updated_at() returns trigger language plpgsql set search_path = '' as $$
begin new.updated_at = now(); return new; end; $$;

alter table public.profiles enable row level security;
alter table public.profiles force row level security;
revoke all on public.profiles from anon;
grant select, insert, update, delete on public.profiles to authenticated;
create policy own_select on public.profiles for select to authenticated using ((select auth.uid()) = user_id);
create policy own_insert on public.profiles for insert to authenticated with check ((select auth.uid()) = user_id);
create policy own_update on public.profiles for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy own_delete on public.profiles for delete to authenticated using ((select auth.uid()) = user_id);
create trigger set_updated_at before update on public.profiles for each row execute function public.mealmind_updated_at();

alter table public.saved_recipes enable row level security;
alter table public.saved_recipes force row level security;
revoke all on public.saved_recipes from anon;
grant select, insert, update, delete on public.saved_recipes to authenticated;
create policy own_select on public.saved_recipes for select to authenticated using ((select auth.uid()) = user_id);
create policy own_insert on public.saved_recipes for insert to authenticated with check ((select auth.uid()) = user_id);
create policy own_update on public.saved_recipes for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy own_delete on public.saved_recipes for delete to authenticated using ((select auth.uid()) = user_id);
create trigger set_updated_at before update on public.saved_recipes for each row execute function public.mealmind_updated_at();

alter table public.user_preferences enable row level security;
alter table public.user_preferences force row level security;
revoke all on public.user_preferences from anon;
grant select, insert, update, delete on public.user_preferences to authenticated;
create policy own_select on public.user_preferences for select to authenticated using ((select auth.uid()) = user_id);
create policy own_insert on public.user_preferences for insert to authenticated with check ((select auth.uid()) = user_id);
create policy own_update on public.user_preferences for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy own_delete on public.user_preferences for delete to authenticated using ((select auth.uid()) = user_id);
create trigger set_updated_at before update on public.user_preferences for each row execute function public.mealmind_updated_at();
