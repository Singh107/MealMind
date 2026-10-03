-- Run against a development Supabase database AFTER the migration.
-- All fixtures and changes roll back. This exercises actual RLS, not application mocks.
begin;
insert into auth.users(id) values
 ('00000000-0000-4000-8000-000000000001'),
 ('00000000-0000-4000-8000-000000000002');
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"00000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
insert into public.saved_recipes(user_id, source_id, recipe)
 values ('00000000-0000-4000-8000-000000000001', 'rls-test', '{}');
insert into public.profiles(user_id, display_name)
 values ('00000000-0000-4000-8000-000000000001', 'Owner');
insert into public.user_preferences(user_id)
 values ('00000000-0000-4000-8000-000000000001');
select set_config('request.jwt.claims', '{"sub":"00000000-0000-4000-8000-000000000002","role":"authenticated"}', true);
do $$
declare affected integer;
begin
 if exists(select 1 from public.saved_recipes where source_id = 'rls-test')
    or exists(select 1 from public.profiles where display_name = 'Owner')
    or exists(select 1 from public.user_preferences where user_id = '00000000-0000-4000-8000-000000000001') then
   raise exception 'RLS leaked another user data';
 end if;
 delete from public.saved_recipes where source_id = 'rls-test';
 get diagnostics affected = row_count;
 if affected <> 0 then raise exception 'RLS permitted cross-user delete'; end if;
 update public.profiles set display_name = 'Intruder' where user_id = '00000000-0000-4000-8000-000000000001';
 get diagnostics affected = row_count;
 if affected <> 0 then raise exception 'RLS permitted cross-user update'; end if;
 begin
   insert into public.saved_recipes(user_id, source_id, recipe)
    values ('00000000-0000-4000-8000-000000000001', 'forbidden', '{}');
   raise exception 'RLS permitted cross-user insert';
 exception when insufficient_privilege then null;
 end;
end $$;
select set_config('request.jwt.claims', '{"sub":"00000000-0000-4000-8000-000000000001","role":"authenticated"}', true);
do $$ begin
 if (select count(*) from public.saved_recipes where source_id = 'rls-test') <> 1 then
   raise exception 'Owner cannot read own recipe';
 end if;
end $$;
delete from public.saved_recipes where source_id = 'rls-test';
rollback;
