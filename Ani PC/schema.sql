-- Aniriame: esquema para Postgres (Supabase). Traducido desde aniriame.db (SQLite).

create table public.entradas (
    id_registro text primary key,
    palabra_raramuri text not null,
    homonimo integer,
    clase text,
    traduccion text,
    ejemplos_y_comentarios text,
    variantes text,
    fuente text,
    pagina_inicio integer,
    pagina_fin integer,
    estado_validacion text,
    es_nota integer default 0   -- 1 si la fila es una nota y no una palabra
);

create table public.significados (
    id integer generated always as identity primary key,
    id_registro text not null references public.entradas(id_registro),
    significado_es text not null,
    significado_norm text not null   -- sin acentos ni plurales, para buscar
);

create table public.pares_traduccion (
    id integer generated always as identity primary key,
    tipo text default 'frase',          -- frase o parrafo
    texto_es text not null,
    texto_es_norm text not null,        -- para encontrar coincidencias
    texto_rar text not null,
    origen text,                        -- institucional, ceees, sistema o correccion
    documento text,
    area text,                          -- por ejemplo: convocatorias
    estado text default 'pendiente',    -- borrador, pendiente, revisado, validado, corregido, rechazado
    par_original_id integer references public.pares_traduccion(id),  -- si es una correccion
    validado_por text,
    fecha timestamptz default now()
);

create table public.revisiones (
    id integer generated always as identity primary key,
    par_id integer references public.pares_traduccion(id),
    estrellas integer check (estrellas between 0 and 5),
    correccion text,
    revisor text,
    fecha timestamptz default now()
);

create table public.metadatos (clave text primary key, valor text);

create index idx_entradas_palabra on public.entradas (lower(palabra_raramuri));
create index idx_significados_norm on public.significados (significado_norm);
create index idx_pares_norm on public.pares_traduccion (texto_es_norm, estado);
create index idx_significados_id_registro on public.significados (id_registro);
create index idx_pares_original on public.pares_traduccion (par_original_id);
create index idx_revisiones_par on public.revisiones (par_id);

create view public.referencias with (security_invoker = true) as
    select id, tipo, texto_es, texto_rar, area, documento, validado_por, fecha
    from public.pares_traduccion where estado = 'validado';

-- Solo el servidor (conexion directa de Postgres) accede a estos datos.
-- RLS activo y sin politicas: la API publica de Supabase no puede leer ni escribir nada.
alter table public.entradas enable row level security;
alter table public.significados enable row level security;
alter table public.pares_traduccion enable row level security;
alter table public.revisiones enable row level security;
alter table public.metadatos enable row level security;
