-- Names come only from verified Telegram initData at the next app opening.
alter table public.pets
    add column owner_name text,
    add column owner_username text;
