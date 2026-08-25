# Memoria del proyecto Deleite/MercadoLibre

Volcado de las memorias que Claude fue acumulando sobre este proyecto durante
la sesión de trabajo original. No es el sistema de memoria automática de
Claude Code (eso es local a una máquina) — son los mismos contenidos, pasados
a markdown plano para que cualquier sesión que abra este repo tenga el mismo
contexto, sin importar desde qué computadora se abra.

- [mercadolibre-project-setup.md](mercadolibre-project-setup.md) — ubicación del repo, OAuth/PKCE, credenciales, setup de la máquina.
- [mercadolibre-pnl-pipeline.md](mercadolibre-pnl-pipeline.md) — cómo se arma el Sheet + dashboard recurrente, scripts, qué inputs informativos preguntar.
- [mercadolibre-base-ventas.md](mercadolibre-base-ventas.md) — tab `base_ventas`: columnas, regla con/sin IVA, prorrateo de envío, filtro solo-pagas.
- [mercadolibre-base-envios.md](mercadolibre-base-envios.md) — tab `base_envios`: ingreso/costo de envío por orden, con/sin IVA.
- [mercadolibre-base-informativa.md](mercadolibre-base-informativa.md) — libro a mano de facturas/gastos que pasa Lucas; siempre preguntar por datos faltantes.
- [mercadolibre-base-ads.md](mercadolibre-base-ads.md) — gasto/ventas de campañas por día desde la API de Product Ads, con/sin IVA.
- [mercadolibre-base-impositiva.md](mercadolibre-base-impositiva.md) — percepciones/retenciones itemizadas (Facturación TAXES, grupos ML+MP), solo períodos cerrados.
- [mercadolibre-sale-breakdown-methodology.md](mercadolibre-sale-breakdown-methodology.md) — regla de cascada de comisión + envío, confirmada contra la pantalla real de Lucas.

**Nota**: estos archivos son observaciones puntuales en el tiempo, no estado
en vivo — antes de confiar en un dato puntual (nombre de función, columna,
flag), verificar contra el código actual del repo.
