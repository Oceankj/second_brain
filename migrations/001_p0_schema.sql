\if :{?embedding_dimension}
\else
\set embedding_dimension 1024
\endif

\echo Using embedding_dimension=:embedding_dimension

create extension if not exists pgcrypto;
create extension if not exists vector;

create table if not exists users (
  id text primary key,
  display_name text,
  api_token_hash text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into users (id, display_name)
values ('0', 'Default User')
on conflict (id) do nothing;

do $$
begin
  create type memory_item_type as enum (
    'note',
    'diary',
    'profile_memory'
  );
exception
  when duplicate_object then null;
end $$;

do $$
begin
  create type memory_item_status as enum (
    'candidate',
    'active',
    'archived'
  );
exception
  when duplicate_object then null;
end $$;

do $$
begin
  create type memory_link_type as enum (
    'references'
  );
exception
  when duplicate_object then null;
end $$;

do $$
begin
  create type memory_item_event_type as enum (
    'created',
    'retrieved',
    'shown',
    'used_in_answer',
    'linked_from_new_note',
    'mentioned_in_diary',
    'manually_pinned',
    'manually_demoted',
    'archived',
    'restored'
  );
exception
  when duplicate_object then null;
end $$;

create table if not exists memory_items (
  id uuid primary key default gen_random_uuid(),
  user_id text not null default '0' references users(id),
  type memory_item_type not null,
  ingest_reason text,
  title text not null,
  body text not null,
  status memory_item_status not null default 'candidate',
  event_date date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table if exists memory_items
add column if not exists ingest_reason text;

alter table if exists users
add column if not exists api_token_hash text;

alter table if exists memory_items
add column if not exists user_id text;

update memory_items
set user_id = '0'
where user_id is null;

alter table if exists memory_items
alter column user_id set default '0';

alter table if exists memory_items
alter column user_id set not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'memory_items_user_id_fkey'
  ) then
    alter table memory_items
    add constraint memory_items_user_id_fkey foreign key (user_id) references users(id);
  end if;
end $$;

create table if not exists memory_chunks (
  id uuid primary key default gen_random_uuid(),
  memory_item_id uuid not null references memory_items(id) on delete cascade,
  chunk_index integer not null,
  content text not null,
  embedding vector(:embedding_dimension) not null,
  token_count integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (memory_item_id, chunk_index)
);

create table if not exists memory_links (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references memory_items(id) on delete cascade,
  target_id uuid not null references memory_items(id) on delete cascade,
  link_type memory_link_type not null default 'references',
  created_at timestamptz not null default now(),
  unique (source_id, target_id, link_type),
  check (source_id <> target_id)
);

create table if not exists tags (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  description text,
  embedding vector(:embedding_dimension),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table if exists tags
add column if not exists embedding vector(:embedding_dimension);

create table if not exists memory_item_tags (
  memory_item_id uuid not null references memory_items(id) on delete cascade,
  tag_id uuid not null references tags(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (memory_item_id, tag_id)
);

create table if not exists memory_item_events (
  id uuid primary key default gen_random_uuid(),
  memory_item_id uuid not null references memory_items(id) on delete cascade,
  event_type memory_item_event_type not null,
  source text,
  session_id text,
  metadata jsonb,
  occurred_at timestamptz not null default now()
);

create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists memory_items_set_updated_at on memory_items;
create trigger memory_items_set_updated_at
before update on memory_items
for each row execute function set_updated_at();

drop trigger if exists memory_chunks_set_updated_at on memory_chunks;
create trigger memory_chunks_set_updated_at
before update on memory_chunks
for each row execute function set_updated_at();

drop trigger if exists tags_set_updated_at on tags;
create trigger tags_set_updated_at
before update on tags
for each row execute function set_updated_at();

drop trigger if exists users_set_updated_at on users;
create trigger users_set_updated_at
before update on users
for each row execute function set_updated_at();

create index if not exists memory_items_type_idx on memory_items(type);
create index if not exists memory_items_status_idx on memory_items(status);
create index if not exists memory_items_event_date_idx on memory_items(event_date);
create index if not exists memory_items_ingest_reason_idx on memory_items(ingest_reason);
create index if not exists memory_items_created_at_idx on memory_items(created_at);
create index if not exists memory_items_user_status_idx on memory_items(user_id, status);
create unique index if not exists users_api_token_hash_idx
on users(api_token_hash)
where api_token_hash is not null;

create index if not exists memory_chunks_item_idx on memory_chunks(memory_item_id);
create index if not exists memory_links_source_idx on memory_links(source_id);
create index if not exists memory_links_target_idx on memory_links(target_id);
create index if not exists memory_item_tags_tag_idx on memory_item_tags(tag_id);
create index if not exists memory_item_events_item_idx on memory_item_events(memory_item_id);
create index if not exists memory_item_events_type_idx on memory_item_events(event_type);
create index if not exists memory_item_events_occurred_at_idx on memory_item_events(occurred_at);

create index if not exists memory_chunks_embedding_idx
on memory_chunks
using hnsw (embedding vector_cosine_ops);
