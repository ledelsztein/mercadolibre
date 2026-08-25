---
name: actualizar-tablero
description: "Actualiza TODO el tablero de Deleite (MercadoLibre): las 7 tablas base_* del Sheet (base_ventas, base_envios, base_ads, base_informativa, base_impositiva, base_full, base_adelantos), la foto diaria de stock_valorizado, el P&L (pnl_data.json), y el dashboard HTML publicado -- de punta a punta, en una sola pasada. Usar SIEMPRE que Lucas pida actualizar el tablero, el dashboard, el P&L completo, 'todo', o traer los datos hasta hoy/ayer -- no solo cuando lo pida con estas palabras exactas. Para actualizar SOLO una tabla puntual, invocar directamente su skill (actualizar-base-ventas, actualizar-base-envios, actualizar-base-ads, actualizar-base-informativa, actualizar-base-impositiva, actualizar-base-full, actualizar-base-adelantos, actualizar-stock-valorizado); esta skill es la orquestadora que las llama a todas."
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

## Paso 1 — invocar cada skill de tabla, en este orden

1. **Invocar la skill `actualizar-base-ventas`** con el rango completo calculado en el Paso 0 más 1 día de margen hacia atrás (no hace falta todo el mes -- confirmado que ningún shipment compartido cruza fechas distintas, ver esa skill para el detalle). Si el rango cruza de un mes a otro, correr por separado cada mes que toque.
2. **Invocar la skill `actualizar-base-envios`** con el mismo rango.
3. **Invocar la skill `actualizar-base-ads`** (siempre el rango completo mayo–hoy, es barata).
4. **Invocar la skill `actualizar-base-informativa`** — preguntarle a Lucas por facturas/gastos nuevos antes, nunca asumir.
5. **Invocar la skill `actualizar-base-impositiva`** — SOLO si cerró un período de Facturación nuevo desde la última corrida (corren 7-a-6, cierran el 7 del mes siguiente). Si no cerró ninguno, saltear este paso entero.
6. **Invocar la skill `actualizar-base-full`** (siempre el rango completo mayo–hoy, es barata, cachea agresivo igual que `base_ads`).
7. **Invocar la skill `actualizar-base-adelantos`** (mismo criterio que `base_full`).
8. **Invocar la skill `actualizar-stock-valorizado`** — foto de HOY (fecha real, no `hoy_real - 1`; esta tabla no sigue la convención de día cerrado porque no es un dato de ventas, es el estado actual de las publicaciones). Independiente del resto: no alimenta el P&L ni el dashboard, así que no hace falta tocar `PERIODOS` ni nada del Paso 2 por esta tabla.

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

Contarle a Lucas: cuántas órdenes nuevas entraron, si algo quedó excluido (no "paid"), si hubo algún shipment compartido prorrateado, si saltó algún paso (ej. `base_impositiva` porque no cerró período), y — sobre todo — **si algún número se movió de forma no trivial contra la corrida anterior** (ej. publicidad que creció por facturación tardía, o un mes que cambia de signo). No hay que esconder sorpresas, hay que señalarlas.

## Reglas que no hay que re-derivar (resumen — el detalle completo está en cada skill de tabla y en la memoria)

- Cargo por venta siempre **neto** (nunca bruto/descuento de Facturación) — ver `actualizar-base-ventas` / `mercadolibre-base-ventas`.
- Publicidad del P&L sale de **Facturación** (Billing, marketplace MCLICS), no de `base_ads` — ver `actualizar-base-ads` / `mercadolibre-base-ads`.
- Costo de mercadería con IVA = costo de la planilla (sin IVA) × 1.21.
- Margen Bruto/Neto = Resultado / **Ventas** (no Ingresos totales).
- Cargos Full (`base_full`) y adelanto de disponibilidad de dinero (`base_adelantos`) son Costo Variable en el punto de equilibrio — ver `actualizar-base-full` / `actualizar-base-adelantos`.
