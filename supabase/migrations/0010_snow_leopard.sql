-- Apply before deploying the snow leopard species. Existing pets, progress and names are unchanged.
-- The inline check from 0007 is auto-named pets_species_check; drop it by lookup in case the name differs.
do $$
declare
    existing text;
begin
    for existing in
        select conname from pg_constraint
        where conrelid = 'public.pets'::regclass
          and contype = 'c'
          and pg_get_constraintdef(oid) ilike '%species%'
    loop
        execute format('alter table public.pets drop constraint %I', existing);
    end loop;
end $$;

alter table public.pets
    add constraint pets_species_check
    check (species in ('cat', 'fox', 'snow_leopard'));
