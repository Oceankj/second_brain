begin;
alter table oauth_clients
  add column if not exists grant_types text[] not null
    default array['authorization_code', 'refresh_token'],
  add column if not exists scopes text[] not null default array['memory:read', 'memory:write'];
commit;
