-- Slab Scout community database (free Supabase project)
-- Paste this whole file into Supabase → SQL Editor → Run.

create extension if not exists pgcrypto;

-- Every confirmed card people scan (and reported fakes). Used to recognise future scans.
create table if not exists catalog_cards (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  card_key text not null unique,
  game text, name text, set_name text, number text, year text, brand text,
  rarity text, variant text, card_type text,
  phash text,              -- image fingerprint
  thumb text,              -- small JPEG (base64), ~5 KB
  source text,             -- TCGdex / YGOPRODeck / Scryfall / Lorcast / AI / manual
  confirmations int not null default 1,
  is_fake boolean not null default false,
  fake_reasons text
);
create index if not exists catalog_cards_game on catalog_cards (game);

-- Sales people saw and added (graded or raw).
create table if not exists catalog_sales (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  card_key text not null,
  grade text,              -- Raw, PSA 10, TAG 9 ...
  price numeric check (price >= 0 and price < 10000000),
  sold_on date,
  url text
);
create index if not exists catalog_sales_key on catalog_sales (card_key);

-- Personal vaults, only reachable through the functions below with the vault code.
create table if not exists vault_cards (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  vault_code text not null,
  data jsonb not null
);
create index if not exists vault_cards_code on vault_cards (vault_code);

alter table catalog_cards enable row level security;
alter table catalog_sales enable row level security;
alter table vault_cards enable row level security;

-- Anyone with the app can read the shared catalog and add sales.
drop policy if exists "read catalog" on catalog_cards;
create policy "read catalog" on catalog_cards for select using (true);
drop policy if exists "read sales" on catalog_sales;
create policy "read sales" on catalog_sales for select using (true);
drop policy if exists "add sales" on catalog_sales;
create policy "add sales" on catalog_sales for insert with check (char_length(coalesce(url,'')) < 2000);
-- No direct policies on vault_cards: it is only reachable through the functions.

-- Add a card or count another confirmation of it.
create or replace function add_catalog_card(p jsonb) returns void
language plpgsql security definer set search_path = public as $$
begin
  insert into catalog_cards (card_key, game, name, set_name, number, year, brand, rarity, variant, card_type, phash, thumb, source, is_fake, fake_reasons)
  values (left(p->>'card_key', 500), p->>'game', left(p->>'name', 200), left(p->>'set_name', 200), left(p->>'number', 50),
          left(p->>'year', 10), left(p->>'brand', 100), left(p->>'rarity', 100), left(p->>'variant', 100), left(p->>'card_type', 60),
          left(p->>'phash', 64), left(p->>'thumb', 40000), left(p->>'source', 40), coalesce((p->>'is_fake')::boolean, false),
          left(p->>'fake_reasons', 2000))
  on conflict (card_key) do update
    set confirmations = catalog_cards.confirmations + 1,
        phash = coalesce(catalog_cards.phash, excluded.phash),
        thumb = coalesce(catalog_cards.thumb, excluded.thumb);
end $$;

create or replace function vault_list(p_code text) returns table (id uuid, data jsonb, created_at timestamptz)
language sql security definer set search_path = public as $$
  select id, data, created_at from vault_cards where vault_code = p_code and char_length(p_code) >= 6 order by created_at desc;
$$;

create or replace function vault_add(p_code text, p_data jsonb) returns uuid
language plpgsql security definer set search_path = public as $$
declare new_id uuid;
begin
  if char_length(p_code) < 6 then raise exception 'vault code too short'; end if;
  if pg_column_size(p_data) > 200000 then raise exception 'card too large'; end if;
  insert into vault_cards (vault_code, data) values (p_code, p_data) returning id into new_id;
  return new_id;
end $$;

create or replace function vault_update(p_code text, p_id uuid, p_data jsonb) returns void
language sql security definer set search_path = public as $$
  update vault_cards set data = p_data where id = p_id and vault_code = p_code;
$$;

create or replace function vault_delete(p_code text, p_id uuid) returns void
language sql security definer set search_path = public as $$
  delete from vault_cards where id = p_id and vault_code = p_code;
$$;

-- Portfolio value history: one point per vault per day, for the value chart.
create table if not exists vault_history (
  vault_code text not null,
  day date not null,
  value numeric not null,
  primary key (vault_code, day)
);
alter table vault_history enable row level security;

create or replace function vault_history_add(p_code text, p_day date, p_value numeric) returns void
language sql security definer set search_path = public as $$
  insert into vault_history (vault_code, day, value) values (p_code, p_day, p_value)
  on conflict (vault_code, day) do update set value = excluded.value;
$$;

create or replace function vault_history_list(p_code text) returns table (day date, value numeric)
language sql security definer set search_path = public as $$
  select day, value from vault_history where vault_code = p_code and char_length(p_code) >= 6 order by day;
$$;

grant execute on function vault_history_add(text, date, numeric), vault_history_list(text) to anon;

grant execute on function add_catalog_card(jsonb), vault_list(text), vault_add(text, jsonb), vault_update(text, uuid, jsonb), vault_delete(text, uuid) to anon;

-- Corrections: the card a person picked for a scan (photo fingerprint -> built-in catalog card), so the next scan
-- that looks the same gets the right card straight away.
create table if not exists scan_corrections (
  id uuid primary key default gen_random_uuid(),
  phash text not null check (char_length(phash) <= 64),
  catalog_key text not null check (char_length(catalog_key) <= 500),
  created_at timestamptz default now()
);
alter table scan_corrections enable row level security;
drop policy if exists "read corrections" on scan_corrections;
create policy "read corrections" on scan_corrections for select using (true);
drop policy if exists "add corrections" on scan_corrections;
create policy "add corrections" on scan_corrections for insert with check (true);
