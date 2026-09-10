-- Run after 0001_pets.sql. Existing pets keep their stats and experience.
alter table public.pets
    add column if not exists name_chosen boolean not null default false;
