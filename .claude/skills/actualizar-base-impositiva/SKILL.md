---
name: actualizar-base-impositiva
description: "Actualiza la pestaña 'base_impositiva' del Google Sheet de Deleite (MercadoLibre) -- percepciones y retenciones itemizadas (Facturación, marketplace TAXES, grupos ML y MP) por jurisdicción/impuesto. Usar SIEMPRE que Lucas pida actualizar, completar o correr base_impositiva, o pregunte cuánto está pagando de percepciones/retenciones por mes -- incluso si no menciona el nombre exacto de la pestaña."
---

# Actualizar base_impositiva (Deleite / MercadoLibre)

Repo: `C:\Users\User\Projects\mercadolibre`. Todos los comandos se corren parados ahí.

Esta tabla **solo se puede actualizar cuando cierra un período de Facturación nuevo** (los períodos corren del 7 de un mes al 6 del siguiente, y cierran/facturan el 7 del mes que sigue). Antes de correr nada, chequear si desde la última corrida cerró un período que todavía no está cargado.

## Paso único -- recalcular y subir

```bash
python compute_base_impositiva.py <period_key_1> <period_key_2> ...
python build_base_impositiva_sheet.py
```

`period_key` tiene formato `YYYY-MM-01` y es el mes SIGUIENTE al que cierra ese período (ej. las percepciones de ventas de junio están en el período `2026-07-01`, porque ese período cubre del 7/6 al 6/7 y se factura el 7/7).

**Si el período todavía está abierto, el script va a fallar el chequeo de consistencia (a propósito) en vez de dar un número que después va a cambiar** -- no hay atajo por-orden para este dato (las entradas de `TAXES` no tienen `sales_info`, se facturan todas juntas el día que cierra el período). Si eso pasa, avisarle a Lucas que hay que esperar a que cierre y no forzar un número.

## Reglas de metodología -- no re-derivar

- **Sumar SIEMPRE los dos grupos**, `ML` y `MP` -- cada uno tiene una parte real de las percepciones (ML es la mayoría, MP un extra más chico de los mismos impuestos del lado de MercadoPago). Olvidarse de uno de los dos subcuenta.
- **"Fecha" de cada fila es la fecha de facturación del período** (todas las entradas de un período comparten la misma, es el día que cerró), no una fecha de venta puntual -- estas percepciones no están atadas a una orden individual.
- Sin columna de con/sin IVA -- son impuestos en sí, no están gravados.
- **No confundir el corte del período (7-a-6) con el mes calendario** -- un período puede cubrir mayormente un mes con solo unos días del siguiente. Para saber a qué mes calendario del P&L corresponde cada `period_key`, cruzar contra `pnl_data.json`/`build_pnl_data.py` (ej. período `2026-07-01` = percepciones de Junio).

Ver memoria `mercadolibre-base-impositiva` para el detalle completo (por qué no hay fallback por orden, ejemplos reales de jurisdicciones).
