-- Apply before deploying the snake species. Existing pets, progress and names are unchanged.
-- Drop the species check by lookup in case its name differs from pets_species_check.
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
    check (species in ('cat', 'fox', 'snow_leopard', 'snake'));
