begin;

alter table users
  add column if not exists username text,
  add column if not exists password_hash text,
  add column if not exists is_active boolean not null default true;

-- Normalize direct SQL writes as well as application writes.
create or replace function normalize_user_username()
returns trigger language plpgsql as $$
begin
  new.username := lower(new.username);
  if new.username is not null and new.username !~ '[^[:space:]]' then
    raise exception 'username must not be blank' using errcode = '23514';
  end if;
  return new;
end;
$$;

create or replace trigger users_normalize_username
before insert or update of username on users
for each row execute function normalize_user_username();

update users set username = lower(username)
where username is distinct from lower(username);

create unique index if not exists users_username_idx on users(username);

-- Keep existing IDs, passwords and custom usernames on subsequent runs.
update users set username = 'admin', updated_at = now()
where id = '0' and username is null;

commit;
