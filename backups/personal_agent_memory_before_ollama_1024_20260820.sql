--
-- PostgreSQL database dump
--

\restrict pp3dgTLdZRUNbDKslFVCWdVEJLUb8jHQTiyyZKiiHhNMlwJctJzeySorXd2oEcy

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg12+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg12+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: memory_item_event_type; Type: TYPE; Schema: public; Owner: admin_jim
--

CREATE TYPE public.memory_item_event_type AS ENUM (
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


ALTER TYPE public.memory_item_event_type OWNER TO admin_jim;

--
-- Name: memory_item_status; Type: TYPE; Schema: public; Owner: admin_jim
--

CREATE TYPE public.memory_item_status AS ENUM (
    'candidate',
    'active',
    'archived'
);


ALTER TYPE public.memory_item_status OWNER TO admin_jim;

--
-- Name: memory_item_type; Type: TYPE; Schema: public; Owner: admin_jim
--

CREATE TYPE public.memory_item_type AS ENUM (
    'note',
    'diary',
    'profile_memory'
);


ALTER TYPE public.memory_item_type OWNER TO admin_jim;

--
-- Name: memory_link_type; Type: TYPE; Schema: public; Owner: admin_jim
--

CREATE TYPE public.memory_link_type AS ENUM (
    'references',
    'expands',
    'derived_from',
    'same_topic',
    'contradicts',
    'supersedes'
);


ALTER TYPE public.memory_link_type OWNER TO admin_jim;

--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: admin_jim
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
begin
  new.updated_at = now();
  return new;
end;
$$;


ALTER FUNCTION public.set_updated_at() OWNER TO admin_jim;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: memory_chunks; Type: TABLE; Schema: public; Owner: admin_jim
--

CREATE TABLE public.memory_chunks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    memory_item_id uuid NOT NULL,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    embedding public.vector(1536) NOT NULL,
    token_count integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.memory_chunks OWNER TO admin_jim;

--
-- Name: memory_item_events; Type: TABLE; Schema: public; Owner: admin_jim
--

CREATE TABLE public.memory_item_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    memory_item_id uuid NOT NULL,
    event_type public.memory_item_event_type NOT NULL,
    source text,
    session_id text,
    metadata jsonb,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.memory_item_events OWNER TO admin_jim;

--
-- Name: memory_item_tags; Type: TABLE; Schema: public; Owner: admin_jim
--

CREATE TABLE public.memory_item_tags (
    memory_item_id uuid NOT NULL,
    tag_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.memory_item_tags OWNER TO admin_jim;

--
-- Name: memory_items; Type: TABLE; Schema: public; Owner: admin_jim
--

CREATE TABLE public.memory_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    type public.memory_item_type NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    status public.memory_item_status DEFAULT 'candidate'::public.memory_item_status NOT NULL,
    event_date date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.memory_items OWNER TO admin_jim;

--
-- Name: memory_links; Type: TABLE; Schema: public; Owner: admin_jim
--

CREATE TABLE public.memory_links (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_id uuid NOT NULL,
    target_id uuid NOT NULL,
    link_type public.memory_link_type DEFAULT 'references'::public.memory_link_type NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT memory_links_check CHECK ((source_id <> target_id))
);


ALTER TABLE public.memory_links OWNER TO admin_jim;

--
-- Name: tags; Type: TABLE; Schema: public; Owner: admin_jim
--

CREATE TABLE public.tags (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.tags OWNER TO admin_jim;

--
-- Data for Name: memory_chunks; Type: TABLE DATA; Schema: public; Owner: admin_jim
--

COPY public.memory_chunks (id, memory_item_id, chunk_index, content, embedding, token_count, created_at, updated_at) FROM stdin;
dcdc82a8-3bda-42fc-9fe3-2479e2e94a2e	602b5e4b-781b-40aa-a910-934c37880ed8	0	User:\nSmoke test memory source 2030739e9e08\n\nAssistant:\nSmoke test assistant output for Personal Agent Memory MCP.	[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.20412415,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.40824828,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.40824828,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.40824828,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.40824828,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]	28	2026-08-20 07:12:12.238421+00	2026-08-20 07:12:12.238421+00
04fb2ef3-62d7-4634-97b6-84732a155f6b	b0cc5dc1-cd82-41f3-b7d0-be87e4203855	0	User:\nSmoke test memory source bb0fcca97c4d\n\nAssistant:\nSmoke test assistant output for Personal Agent Memory MCP.	[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.20412415,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.40824828,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.40824828,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.40824828,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.40824828,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]	28	2026-08-20 07:13:40.236986+00	2026-08-20 07:13:40.236986+00
9a964224-6798-4889-9679-d5d2c8256110	685fc0b2-2b87-4ee9-81fd-daebccd38b4d	0	User:\nSmoke test memory source 97f59e93c012\n\nAssistant:\nSmoke test assistant output for Personal Agent Memory MCP.	[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.20412415,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.40824828,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0.40824828,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.20412415,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.40824828,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,-0.40824828,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]	28	2026-08-20 07:17:16.836041+00	2026-08-20 07:17:16.836041+00
\.


--
-- Data for Name: memory_item_events; Type: TABLE DATA; Schema: public; Owner: admin_jim
--

COPY public.memory_item_events (id, memory_item_id, event_type, source, session_id, metadata, occurred_at) FROM stdin;
61c0b4c7-8a8f-4f0d-9035-3374307deda6	602b5e4b-781b-40aa-a910-934c37880ed8	created	smoke_test	smoke-2030739e9e08	{"app": "scripts/smoke_test.py", "tags": ["smoke-test", "mcp"], "source": "smoke_test", "user_id": "smoke-user", "timestamp": "2026-08-20T07:12:12.193582Z", "session_id": "smoke-2030739e9e08", "conversation_id": null}	2026-08-20 07:12:12.295879+00
645c423a-9782-46ac-be1f-c6668b5c63a7	602b5e4b-781b-40aa-a910-934c37880ed8	retrieved	personal-agent-memory	smoke-2030739e9e08	{"query": "Find the smoke test memory source 2030739e9e08", "user_id": "smoke-user"}	2026-08-20 07:12:12.320678+00
6cba2d60-09c4-4693-b59b-bb43f5383f4e	b0cc5dc1-cd82-41f3-b7d0-be87e4203855	created	smoke_test	smoke-bb0fcca97c4d	{"app": "scripts/smoke_test.py", "tags": ["smoke-test", "mcp"], "source": "smoke_test", "user_id": "smoke-user", "timestamp": "2026-08-20T07:13:40.197855Z", "session_id": "smoke-bb0fcca97c4d", "conversation_id": null}	2026-08-20 07:13:40.289339+00
5ebba76f-89bb-4ccf-8ef8-1646afaa8f78	b0cc5dc1-cd82-41f3-b7d0-be87e4203855	retrieved	personal-agent-memory	smoke-bb0fcca97c4d	{"query": "Find the smoke test memory source bb0fcca97c4d", "user_id": "smoke-user"}	2026-08-20 07:13:40.313613+00
068bde81-c2a4-444b-a22d-e51ba17a60c3	602b5e4b-781b-40aa-a910-934c37880ed8	retrieved	personal-agent-memory	smoke-bb0fcca97c4d	{"query": "Find the smoke test memory source bb0fcca97c4d", "user_id": "smoke-user"}	2026-08-20 07:13:40.322048+00
afb57e27-4619-45da-a253-10ad21acd4c8	685fc0b2-2b87-4ee9-81fd-daebccd38b4d	created	smoke_test	smoke-97f59e93c012	{"app": "scripts/smoke_test.py", "tags": ["smoke-test", "mcp"], "source": "smoke_test", "user_id": "smoke-user", "timestamp": "2026-08-20T07:17:16.796380Z", "session_id": "smoke-97f59e93c012", "conversation_id": null}	2026-08-20 07:17:16.889669+00
ed21d07c-f9c0-4043-8f59-251e8b6ce6a2	685fc0b2-2b87-4ee9-81fd-daebccd38b4d	retrieved	personal-agent-memory	smoke-97f59e93c012	{"query": "Find the smoke test memory source 97f59e93c012", "user_id": "smoke-user"}	2026-08-20 07:17:16.914283+00
6c85aa43-f71c-4915-9b22-388a252690d8	602b5e4b-781b-40aa-a910-934c37880ed8	retrieved	personal-agent-memory	smoke-97f59e93c012	{"query": "Find the smoke test memory source 97f59e93c012", "user_id": "smoke-user"}	2026-08-20 07:17:16.923483+00
97296c4e-8695-4062-aeb0-cdceca9bf905	b0cc5dc1-cd82-41f3-b7d0-be87e4203855	retrieved	personal-agent-memory	smoke-97f59e93c012	{"query": "Find the smoke test memory source 97f59e93c012", "user_id": "smoke-user"}	2026-08-20 07:17:16.932132+00
\.


--
-- Data for Name: memory_item_tags; Type: TABLE DATA; Schema: public; Owner: admin_jim
--

COPY public.memory_item_tags (memory_item_id, tag_id, created_at) FROM stdin;
602b5e4b-781b-40aa-a910-934c37880ed8	6a720f3c-fc85-407f-a4ce-67de3b67c900	2026-08-20 07:12:12.269059+00
602b5e4b-781b-40aa-a910-934c37880ed8	18700821-96d0-4e10-aba2-99c8f1f78a4f	2026-08-20 07:12:12.287106+00
b0cc5dc1-cd82-41f3-b7d0-be87e4203855	6a720f3c-fc85-407f-a4ce-67de3b67c900	2026-08-20 07:13:40.264024+00
b0cc5dc1-cd82-41f3-b7d0-be87e4203855	18700821-96d0-4e10-aba2-99c8f1f78a4f	2026-08-20 07:13:40.281235+00
685fc0b2-2b87-4ee9-81fd-daebccd38b4d	6a720f3c-fc85-407f-a4ce-67de3b67c900	2026-08-20 07:17:16.863758+00
685fc0b2-2b87-4ee9-81fd-daebccd38b4d	18700821-96d0-4e10-aba2-99c8f1f78a4f	2026-08-20 07:17:16.881047+00
\.


--
-- Data for Name: memory_items; Type: TABLE DATA; Schema: public; Owner: admin_jim
--

COPY public.memory_items (id, type, title, body, status, event_date, created_at, updated_at) FROM stdin;
602b5e4b-781b-40aa-a910-934c37880ed8	note	Smoke test memory source 2030739e9e08	User:\nSmoke test memory source 2030739e9e08\n\nAssistant:\nSmoke test assistant output for Personal Agent Memory MCP.	candidate	\N	2026-08-20 07:12:12.216283+00	2026-08-20 07:12:12.216283+00
b0cc5dc1-cd82-41f3-b7d0-be87e4203855	note	Smoke test memory source bb0fcca97c4d	User:\nSmoke test memory source bb0fcca97c4d\n\nAssistant:\nSmoke test assistant output for Personal Agent Memory MCP.	candidate	\N	2026-08-20 07:13:40.219836+00	2026-08-20 07:13:40.219836+00
685fc0b2-2b87-4ee9-81fd-daebccd38b4d	note	Smoke test memory source 97f59e93c012	User:\nSmoke test memory source 97f59e93c012\n\nAssistant:\nSmoke test assistant output for Personal Agent Memory MCP.	candidate	\N	2026-08-20 07:17:16.819383+00	2026-08-20 07:17:16.819383+00
c1ae8f53-23f5-40a0-9f18-988c5561b9d7	note	Smoke test memory source 083237bdcfbe	User:\nSmoke test memory source 083237bdcfbe\n\nAssistant:\nSmoke test assistant output for Personal Agent Memory MCP.	candidate	\N	2026-08-20 07:40:12.399511+00	2026-08-20 07:40:12.399511+00
8c4d6571-d6a7-4926-bad0-77e37b479046	note	Smoke test memory source 79072ba04398	User:\nSmoke test memory source 79072ba04398\n\nAssistant:\nSmoke test assistant output for Personal Agent Memory MCP.	candidate	\N	2026-08-20 07:40:55.134974+00	2026-08-20 07:40:55.134974+00
abc33c8f-1f0a-4bf8-b115-09c05edf210d	note	Smoke test memory source 95589a693dae	User:\nSmoke test memory source 95589a693dae\n\nAssistant:\nSmoke test assistant output for Personal Agent Memory MCP.	candidate	\N	2026-08-20 07:42:54.957475+00	2026-08-20 07:42:54.957475+00
\.


--
-- Data for Name: memory_links; Type: TABLE DATA; Schema: public; Owner: admin_jim
--

COPY public.memory_links (id, source_id, target_id, link_type, created_at) FROM stdin;
\.


--
-- Data for Name: tags; Type: TABLE DATA; Schema: public; Owner: admin_jim
--

COPY public.tags (id, name, description, created_at, updated_at) FROM stdin;
6a720f3c-fc85-407f-a4ce-67de3b67c900	smoke-test	\N	2026-08-20 07:12:12.258205+00	2026-08-20 07:17:16.851855+00
18700821-96d0-4e10-aba2-99c8f1f78a4f	mcp	\N	2026-08-20 07:12:12.278615+00	2026-08-20 07:17:16.872411+00
\.


--
-- Name: memory_chunks memory_chunks_memory_item_id_chunk_index_key; Type: CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.memory_chunks
    ADD CONSTRAINT memory_chunks_memory_item_id_chunk_index_key UNIQUE (memory_item_id, chunk_index);


--
-- Name: memory_chunks memory_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.memory_chunks
    ADD CONSTRAINT memory_chunks_pkey PRIMARY KEY (id);


--
-- Name: memory_item_events memory_item_events_pkey; Type: CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.memory_item_events
    ADD CONSTRAINT memory_item_events_pkey PRIMARY KEY (id);


--
-- Name: memory_item_tags memory_item_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.memory_item_tags
    ADD CONSTRAINT memory_item_tags_pkey PRIMARY KEY (memory_item_id, tag_id);


--
-- Name: memory_items memory_items_pkey; Type: CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.memory_items
    ADD CONSTRAINT memory_items_pkey PRIMARY KEY (id);


--
-- Name: memory_links memory_links_pkey; Type: CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.memory_links
    ADD CONSTRAINT memory_links_pkey PRIMARY KEY (id);


--
-- Name: memory_links memory_links_source_id_target_id_link_type_key; Type: CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.memory_links
    ADD CONSTRAINT memory_links_source_id_target_id_link_type_key UNIQUE (source_id, target_id, link_type);


--
-- Name: tags tags_name_key; Type: CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_name_key UNIQUE (name);


--
-- Name: tags tags_pkey; Type: CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_pkey PRIMARY KEY (id);


--
-- Name: memory_chunks_embedding_idx; Type: INDEX; Schema: public; Owner: admin_jim
--

CREATE INDEX memory_chunks_embedding_idx ON public.memory_chunks USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: memory_chunks_item_idx; Type: INDEX; Schema: public; Owner: admin_jim
--

CREATE INDEX memory_chunks_item_idx ON public.memory_chunks USING btree (memory_item_id);


--
-- Name: memory_item_events_item_idx; Type: INDEX; Schema: public; Owner: admin_jim
--

CREATE INDEX memory_item_events_item_idx ON public.memory_item_events USING btree (memory_item_id);


--
-- Name: memory_item_events_occurred_at_idx; Type: INDEX; Schema: public; Owner: admin_jim
--

CREATE INDEX memory_item_events_occurred_at_idx ON public.memory_item_events USING btree (occurred_at);


--
-- Name: memory_item_events_type_idx; Type: INDEX; Schema: public; Owner: admin_jim
--

CREATE INDEX memory_item_events_type_idx ON public.memory_item_events USING btree (event_type);


--
-- Name: memory_item_tags_tag_idx; Type: INDEX; Schema: public; Owner: admin_jim
--

CREATE INDEX memory_item_tags_tag_idx ON public.memory_item_tags USING btree (tag_id);


--
-- Name: memory_items_event_date_idx; Type: INDEX; Schema: public; Owner: admin_jim
--

CREATE INDEX memory_items_event_date_idx ON public.memory_items USING btree (event_date);


--
-- Name: memory_items_status_idx; Type: INDEX; Schema: public; Owner: admin_jim
--

CREATE INDEX memory_items_status_idx ON public.memory_items USING btree (status);


--
-- Name: memory_items_type_idx; Type: INDEX; Schema: public; Owner: admin_jim
--

CREATE INDEX memory_items_type_idx ON public.memory_items USING btree (type);


--
-- Name: memory_links_source_idx; Type: INDEX; Schema: public; Owner: admin_jim
--

CREATE INDEX memory_links_source_idx ON public.memory_links USING btree (source_id);


--
-- Name: memory_links_target_idx; Type: INDEX; Schema: public; Owner: admin_jim
--

CREATE INDEX memory_links_target_idx ON public.memory_links USING btree (target_id);


--
-- Name: memory_chunks memory_chunks_set_updated_at; Type: TRIGGER; Schema: public; Owner: admin_jim
--

CREATE TRIGGER memory_chunks_set_updated_at BEFORE UPDATE ON public.memory_chunks FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: memory_items memory_items_set_updated_at; Type: TRIGGER; Schema: public; Owner: admin_jim
--

CREATE TRIGGER memory_items_set_updated_at BEFORE UPDATE ON public.memory_items FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: tags tags_set_updated_at; Type: TRIGGER; Schema: public; Owner: admin_jim
--

CREATE TRIGGER tags_set_updated_at BEFORE UPDATE ON public.tags FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: memory_chunks memory_chunks_memory_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.memory_chunks
    ADD CONSTRAINT memory_chunks_memory_item_id_fkey FOREIGN KEY (memory_item_id) REFERENCES public.memory_items(id) ON DELETE CASCADE;


--
-- Name: memory_item_events memory_item_events_memory_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.memory_item_events
    ADD CONSTRAINT memory_item_events_memory_item_id_fkey FOREIGN KEY (memory_item_id) REFERENCES public.memory_items(id) ON DELETE CASCADE;


--
-- Name: memory_item_tags memory_item_tags_memory_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.memory_item_tags
    ADD CONSTRAINT memory_item_tags_memory_item_id_fkey FOREIGN KEY (memory_item_id) REFERENCES public.memory_items(id) ON DELETE CASCADE;


--
-- Name: memory_item_tags memory_item_tags_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.memory_item_tags
    ADD CONSTRAINT memory_item_tags_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.tags(id) ON DELETE CASCADE;


--
-- Name: memory_links memory_links_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.memory_links
    ADD CONSTRAINT memory_links_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.memory_items(id) ON DELETE CASCADE;


--
-- Name: memory_links memory_links_target_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin_jim
--

ALTER TABLE ONLY public.memory_links
    ADD CONSTRAINT memory_links_target_id_fkey FOREIGN KEY (target_id) REFERENCES public.memory_items(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict pp3dgTLdZRUNbDKslFVCWdVEJLUb8jHQTiyyZKiiHhNMlwJctJzeySorXd2oEcy

