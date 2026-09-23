---
name: actualizar-tablero
description: "Actualiza TODO el tablero de Deleite (MercadoLibre): las 7 tablas base_* del Sheet (base_ventas, base_envios, base_ads, base_informativa, base_impositiva, base_full, base_adelantos), las fotos diarias de stock_valorizado y publicaciones_recibis, balance_salida, el P&L (pnl_data.json), y el dashboard HTML publicado -- de punta a punta, en una sola pasada, incluyendo un re-chequeo de status de ordenes de los ultimos 30 dias. Usar SIEMPRE que Lucas pida actualizar el tablero, el dashboard, el P&L completo, 'todo', o traer los datos hasta hoy/ayer -- no solo cuando lo pida con estas palabras exactas. Para actualizar SOLO una tabla puntual, invocar directamente su skill (actualizar-base-ventas, actualizar-base-envios, actualizar-base-ads, actualizar-base-informativa, actualizar-base-impositiva, actualizar-base-full, actualizar-base-adelantos, actualizar-stock-valorizado, actualizar-publicaciones-recibis, actualizar-balance-salida); esta skill es la orquestadora que las llama a todas."
---

# Actualizar el tablero completo (Deleite / MercadoLibre)

Repo: `C:\Users\User\Projects\mercadolibre`. Todos los comandos se corren parados ahí.

Esta skill **no repite los pasos de cada tabla** — invoca a cada una de las 7 skills `actualizar-base-*` como sub-pasos (usar la herramienta Skill para cada una), y agrega encima lo que les falta: el chequeo de fecha real, `base_impositiva` (que solo aplica a veces), regenerar `pnl_data.json`/dashboard/Sheet, y publicar. Si algo de una tabla puntual no cierra, el detalle vive en la skill de esa tabla (o en la memoria correspondiente), no acá.

## Paso 0 — fecha real y rango a cubrir (automático, sin preguntarle a Lucas)

Cuando Lucas invoca esta skill directamente, el rango a actualizar se calcula solo, no se le pregunta:

1. Correr `date +%Y-%m-%d` **ahora mismo**, siempre — el reloj asumido derivó varias veces distintas dentro de una sola sesión larga (confirmado repetidas veces) sin que nadie lo notara hasta que algo puntual fallaba. No confiar en una fecha "hoy" que venga de más atrás en la conversación. El corte de "día cerrado" es `hoy_real - 1`.
2. Correr `python fetch_orders.py --status` para ver hasta qué fecha hay datos guardados por mes.
3. **El rango a actualizar es desde el día siguiente al último dato guardado, hasta `hoy_real - 1` inclusive** — puede ser más de un día (Lucas no la corre necesariamente todos los días, puede haber quedado un hueco de varios días sin ejecutar). No asumir que solo pasó un día.
4. Decirle a Lucas el rango que se va a actualizar (transparencia), pero **no hace falta esperar su confirmación** para arrancar — a diferencia de una corrida exploratoria/puntual, esta es la corrida de rutina que él mismo pidió poder disparar directo.

## Paso 0.5 — re-verificar status de los últimos 30 días (pedido de Lucas, 2026-09-17)

```bash
python verificar_status_reciente.py
```

Ninguna otra parte del pipeline vuelve a chequear si una orden ya guardada (de hace más de 1 día) cambió de `paid` a `cancelled`/`refunded` -- una vez procesada, queda así para siempre salvo que este script la agarre. Corre barato (solo re-pega a `/orders/search` para los últimos 30 días, no a los ~1600+ pedidos históricos desde mayo -- MercadoLibre no permite que una orden cambie de status pasado ese plazo). Si imprime "ATENCION", ya sacó las órdenes afectadas de `base_ventas.json`/`base_envios.json` -- avisarle a Lucas cuáles y por qué, y no olvidarse de correr `build_base_ventas_sheet.py`/`build_base_envios_sheet.py` para esas dos tablas antes de seguir (el Paso 2 de acá abajo ya regenera P&L/dashboard con los datos corregidos, pero el Sheet de esas dos tablas puntuales no se toca solo con eso).

## Paso 1 — invocar cada skill de tabla, en este orden

**`actualizar-base-informativa` NO se invoca acá** -- pedido de Lucas (2026-09-18): la pregunta por facturas/gastos nuevos se manda recién al final (Paso 5), para no bloquear el resto del pipeline en el medio esperando su respuesta. Este Paso 1 corre entero con los datos de `base_informativa` que ya estén cargados (Autónomos/IIBB más recientes, etc.) tal como están.

1. **Invocar la skill `actualizar-base-ventas`** con el rango completo calculado en el Paso 0 más 1 día de margen hacia atrás (no hace falta todo el mes -- confirmado que ningún shipment compartido cruza fechas distintas, ver esa skill para el detalle). Si el rango cruza de un mes a otro, correr por separado cada mes que toque.
2. **Invocar la skill `actualizar-base-envios`** con el mismo rango.
3. **Invocar la skill `actualizar-base-ads`** (siempre el rango completo mayo–hoy, es barata).
4. **Invocar la skill `actualizar-base-impositiva`** — SOLO si cerró un período de Facturación nuevo desde la última corrida (corren 7-a-6, cierran el 7 del mes siguiente). Si no cerró ninguno, saltear este paso entero.
5. **Invocar la skill `actualizar-base-full`** (siempre el rango completo mayo–hoy, es barata, cachea agresivo igual que `base_ads`).
6. **Invocar la skill `actualizar-base-adelantos`** (mismo criterio que `base_full`).
7. **Invocar la skill `actualizar-stock-valorizado`** — foto de HOY (fecha real, no `hoy_real - 1`; esta tabla no sigue la convención de día cerrado porque no es un dato de ventas, es el estado actual de las publicaciones). Independiente del P&L/dashboard del Paso 2, pero SÍ la necesita el Paso 9 (`balance_salida`) como referencia.
7.5. **Correr `python check_productos_sin_costo.py`** (pedido de Lucas, 2026-09-22) — usa la foto de `stock_valorizado` recién tomada en el paso anterior, no pega de nuevo a la API. Chequea qué publicaciones activas no tienen ningún costo cargado en `data/Costos.xlsx` (o lo tienen en 0) -- si compute_base_ventas.py calcula una venta de esos productos, el costo sale $0 y el margen queda inflado sin que se note. Guardar la lista para el Paso 4 (reportarla a Lucas), no hace falta bloquear el resto del pipeline por esto.
8. **Invocar la skill `actualizar-publicaciones-recibis`** — también foto de HOY, mismo criterio que `stock_valorizado`.
9. **Invocar la skill `actualizar-balance-salida`** — depende de los dos pasos anteriores (`stock_valorizado` y `publicaciones_recibis`) ya corridos hoy, además de `base_informativa` (Autónomos/IIBB) y `base_impositiva` (Percepciones) frescos -- con los valores ya cargados hasta ahora, no con lo que Lucas conteste en el Paso 5. Correr último dentro de este Paso 1.

## Paso 2 — regenerar P&L, dashboard y Sheet

```bash
python build_pnl_data.py
```

**Antes de correrlo, revisar el diccionario `PERIODOS` adentro de `build_pnl_data.py`** (y el mismo diccionario duplicado en `build_dashboard_data.py` y `build_sheet.py` — tres copias, ninguna de las skills de tabla las toca, hay que actualizarlas a mano acá si el corte de "mes parcial" avanzó o si cerró un mes y hay que agregar el siguiente como parcial nuevo).

```bash
python build_dashboard_data.py
python build_sheet.py
```

## Paso 3 — publicar el dashboard

Copiar `dashboard_output.html` al scratchpad y llamar a la herramienta Artifact sobre esa ruta (la misma ruta mantiene la misma URL: `https://claude.ai/code/artifact/acc4defe-62ef-46c0-8991-9ee404d96590`).

## Paso 4 — reportar, no solo decir "listo"

Contarle a Lucas: cuántas órdenes nuevas entraron, si algo quedó excluido (no "paid"), si el Paso 0.5 encontró alguna orden que cambió de status (cuál, y a qué pasó), si hubo algún shipment compartido prorrateado, si saltó algún paso (ej. `base_impositiva` porque no cerró período), si el Paso 7.5 encontró publicaciones activas sin costo cargado (cuáles, para que Lucas los pase), y — sobre todo — **si algún número se movió de forma no trivial contra la corrida anterior** (ej. publicidad que creció por facturación tardía, o un mes que cambia de signo). No hay que esconder sorpresas, hay que señalarlas.

**Siempre mandar los dos links al final** (pedido de Lucas, 2026-09-18) -- el del Google Sheet de Deleite (P&L/todas las tablas) y el del Artifact del dashboard (`https://claude.ai/code/artifact/acc4defe-62ef-46c0-8991-9ee404d96590`). No dar por sobreentendido que ya los tiene de antes.

## Paso 5 — preguntar por `base_informativa` (al final, para no bloquear el resto)

Recién acá invocar la skill `actualizar-base-informativa` para preguntarle a Lucas por facturas/gastos nuevos en cada categoría (Logística Flex, Otros cargos logísticos, Otros cargos, Autónomos, IIBB) -- **usar `AskUserQuestion`** (formulario clickeable), no texto plano, pedido explícito de Lucas.

- **Si no hay nada nuevo**: listo, no hace falta re-correr nada más.
- **Si trae datos nuevos**: cargarlos en `base_informativa.json`, correr `python build_base_informativa_sheet.py`, y evaluar qué más depende de eso:
  - Si tocó `Autónomos` o `IIBB`, volver a correr `actualizar-balance-salida` (esos valores alimentan el cálculo).
  - Volver a correr el Paso 2 completo (`build_pnl_data.py` / `build_dashboard_data.py` / `build_sheet.py`) y el Paso 3 (publicar el dashboard de nuevo) para que el P&L y el dashboard reflejen el dato nuevo.
  - Avisarle a Lucas que se actualizó por el dato nuevo y qué cambió.

## Paso 6 — commitear y pushear a `origin/main` (siempre, sin preguntar)

Pedido de Lucas (2026-09-23): al terminar (después del Paso 5, y de re-correr lo que haga falta si trajo datos nuevos), **commitear todos los cambios y pushear a `origin/main` sin preguntarle** — así otras sesiones arrancan desde la base al día (ver CLAUDE.md, sección de sincronizar). Antes del push, `git fetch origin` y verificar que no haya commits nuevos en `origin/main`; si los hay, integrarlos (sin pisar datos, mismo criterio que CLAUDE.md) antes de pushear. Mensaje tipo `Actualizar tablero completo hasta DD/MM` con un resumen corto de qué se actualizó/salteó.

## Reglas que no hay que re-derivar (resumen — el detalle completo está en cada skill de tabla y en la memoria)

- Cargo por venta siempre **neto** (nunca bruto/descuento de Facturación) — ver `actualizar-base-ventas` / `mercadolibre-base-ventas`.
- Publicidad del P&L sale de **Facturación** (Billing, marketplace MCLICS), no de `base_ads` — ver `actualizar-base-ads` / `mercadolibre-base-ads`.
- Costo de mercadería con IVA = costo de la planilla (sin IVA) × 1.21.
- Margen Bruto/Neto = Resultado / **Ventas** (no Ingresos totales).
- Cargos Full (`base_full`) y adelanto de disponibilidad de dinero (`base_adelantos`) son Costo Variable en el punto de equilibrio — ver `actualizar-base-full` / `actualizar-base-adelantos`.
