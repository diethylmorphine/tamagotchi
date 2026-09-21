-- Apply before deploying the pet picker. Existing progress and names are unchanged.
alter table public.pets
    add column species text not null default 'cat'
    check (species in ('cat', 'fox'));
