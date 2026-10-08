alter table memory_items
  add column if not exists record_kind text not null default 'unknown',
  add column if not exists role text,
  add column if not exists source text,
  add column if not exists session_id text,
  add column if not exists source_message_id text,
  add column if not exists sequence bigint,
  add column if not exists source_timestamp timestamptz,
  add column if not exists content_kinds text[] not null default '{}',
  add column if not exists ingest_fingerprint text;

-- No guessing or destructive splitting of legacy bodies.
update memory_items set record_kind = 'derived'
where record_kind = 'unknown' and (type = 'diary' or exists (
  select 1 from memory_item_events e where e.memory_item_id = memory_items.id
  and e.event_type = 'created' and e.source = 'candidate_review'));

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'memory_source_shape'
                 and conrelid = 'memory_items'::regclass) then
    alter table memory_items add constraint memory_source_shape check (
      record_kind in ('source', 'derived', 'unknown')
      and (role is null or role in ('user', 'assistant', 'mixed', 'unknown'))
      and (record_kind <> 'derived' or role is null)
      and (record_kind <> 'source' or role is not null)
      and (sequence is null or sequence >= 0)
      and content_kinds <@ array['event', 'thought', 'intention']::text[]
      and (source_message_id is null or (record_kind = 'source'
        and source is not null and session_id is not null))
    );
  end if;
end $$;
create unique index if not exists memory_source_identity_idx
  on memory_items(user_id, source, session_id, source_message_id)
  where source_message_id is not null;
create index if not exists memory_source_session_idx
  on memory_items(user_id, source, session_id, sequence);

create or replace function validate_memory_relation() returns trigger as $$
declare a memory_items; b memory_items;
begin
  select * into a from memory_items where id = new.source_id;
  select * into b from memory_items where id = new.target_id;
  if a.user_id is distinct from b.user_id then
    raise exception 'Memory relations cannot cross users';
  end if;
  if new.link_type::text = 'replies_to' then
    if a.record_kind <> 'source' or b.record_kind <> 'source'
      or a.source is null or a.session_id is null
      or a.source is distinct from b.source or a.session_id is distinct from b.session_id then
      raise exception 'Replies require sources in the same conversation';
    end if;
    if a.sequence is not null and b.sequence is not null and a.sequence <= b.sequence then
      raise exception 'Reply sequence must follow its target';
    end if;
    if exists (with recursive ancestors(id) as (
      select new.target_id union
      select ml.target_id from memory_links ml join ancestors x on ml.source_id = x.id
      where ml.link_type::text = 'replies_to'
    ) select 1 from ancestors where id = new.source_id) then
      raise exception 'Reply cycle';
    end if;
  end if;
  if new.link_type::text = 'derived_from' and a.record_kind <> 'derived' then
    raise exception 'Only derived items have derivation links';
  end if;
  return new;
end $$ language plpgsql;
drop trigger if exists memory_relation_guard on memory_links;
create trigger memory_relation_guard before insert or update on memory_links
  for each row execute function validate_memory_relation();
