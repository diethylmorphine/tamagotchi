begin;

alter table public.pets alter column name set default 'Питомец';

-- Preserve all player-chosen names and gameplay state.
update public.pets
set name = 'Питомец', version = version + 1
where name_chosen = false and name <> 'Питомец';

commit;
