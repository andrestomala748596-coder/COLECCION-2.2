alter function public.publicar_catalogo_series(jsonb, text) security invoker;
revoke all on function public.publicar_catalogo_series(jsonb, text) from public;
revoke execute on function public.publicar_catalogo_series(jsonb, text) from anon, authenticated;
grant execute on function public.publicar_catalogo_series(jsonb, text) to service_role;
