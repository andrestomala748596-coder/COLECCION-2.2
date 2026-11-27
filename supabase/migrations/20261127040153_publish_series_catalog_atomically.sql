create or replace function public.publicar_catalogo_series(
  p_series jsonb,
  p_commit_sha text default null
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_version_id uuid;
  v_total integer;
begin
  if jsonb_typeof(p_series) <> 'array' then
    raise exception 'p_series debe ser un array JSON';
  end if;
  if jsonb_array_length(p_series) = 0 then
    raise exception 'Se rechazó publicar un catálogo de series vacío';
  end if;

  insert into public.series_catalogo_versiones (estado, commit_sha, total_series)
  values ('preparando', p_commit_sha, 0)
  returning id into v_version_id;

  delete from public.series;

  insert into public.series (
    id_video, plataforma, titulo, fecha, portada, backdrop, genero,
    rating, duracion, frase_promocional, sinopsis, actores, director,
    trailer, urls, metodo, urls_directas, url_directa, extracted_by_url,
    version_id, categoria
  )
  select
    nullif(x->>'id_video', ''),
    nullif(x->>'plataforma', ''),
    coalesce(nullif(x->>'titulo', ''), 'Sin título'),
    nullif(x->>'fecha', '')::date,
    nullif(x->>'portada', ''),
    nullif(x->>'backdrop', ''),
    nullif(x->>'genero', ''),
    nullif(x->>'rating', '')::numeric,
    nullif(x->>'duracion', '')::integer,
    nullif(x->>'frase_promocional', ''),
    nullif(x->>'sinopsis', ''),
    nullif(x->>'actores', ''),
    nullif(x->>'director', ''),
    nullif(x->>'trailer', ''),
    case when jsonb_typeof(x->'urls') = 'array'
      then array(select jsonb_array_elements_text(x->'urls')) else '{}'::text[] end,
    nullif(x->>'metodo', ''),
    case when jsonb_typeof(x->'urls_directas') = 'array'
      then array(select jsonb_array_elements_text(x->'urls_directas')) else '{}'::text[] end,
    nullif(x->>'url_directa', ''),
    case when jsonb_typeof(x->'extracted_by_url') = 'object'
      then x->'extracted_by_url' else '{}'::jsonb end,
    v_version_id,
    coalesce(nullif(x->>'categoria', ''), 'GENERAL')
  from jsonb_array_elements(p_series) as t(x);

  get diagnostics v_total = row_count;

  update public.series_catalogo_versiones
  set estado = 'anterior'
  where id <> v_version_id and estado = 'publicado';

  update public.series_catalogo_versiones
  set estado = 'publicado', total_series = v_total, publicado_en = now()
  where id = v_version_id;

  update public.series_catalogo_estado
  set version_id = v_version_id, actualizado_en = now()
  where singleton = true;

  return jsonb_build_object(
    'ok', true,
    'version_id', v_version_id,
    'total_series', v_total,
    'commit_sha', p_commit_sha
  );
end;
$$;

revoke all on function public.publicar_catalogo_series(jsonb, text) from public;
revoke all on function public.publicar_catalogo_series(jsonb, text) from anon, authenticated;
grant execute on function public.publicar_catalogo_series(jsonb, text) to service_role;
