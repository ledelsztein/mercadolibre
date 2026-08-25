---
name: actualizar-base-ads
description: "Actualiza la pestaña 'base_ads' del Google Sheet de Deleite (MercadoLibre) -- una fila por día con Factura, Costo y Ventas atribuidas de publicidad (Facturación + API de Ads), con y sin IVA. Usar SIEMPRE que Lucas pida actualizar, completar o correr base_ads, o pida 'la tabla de publicidad', 'el gasto de ads' -- incluso si no menciona el nombre exacto de la pestaña."
---

# Actualizar base_ads (Deleite / MercadoLibre)

Repo: `C:\Users\User\Projects\mercadolibre`. Todos los comandos se corren parados ahí.

A diferencia de `base_ventas`/`base_envios`, esta tabla **no necesita order_ids** -- siempre se llama con el rango completo mayo-hoy, pero el script (`compute_base_ads.py`) ya cachea agresivamente (2026-07-31, pedido de Lucas) así que no vuelve a pegarle a la API por nada que ya esté confirmado cerrado: cachea por separado los períodos de Facturación ya cerrados y hasta qué día ya se chequeó la API de Ads (`base_ads_cache_state.json`). Pasarle siempre mayo-hoy es seguro y barato, el script decide solo qué pedir de nuevo.

## Paso único -- recalcular y subir

```bash
python compute_base_ads.py 2026-05-01 <fecha_hasta_hoy>
python build_base_ads_sheet.py
```

**Antes de definir `<fecha_hasta_hoy>`, correr `date +%Y-%m-%d` para confirmar la fecha real del sistema** -- no asumir ni arrastrar una fecha de más atrás en la conversación (esto derivó mal varias veces en el pasado).

**Ojo con el límite de 90 días de la API de Ads** (no de Facturación) -- `compute_base_ads.py` ya parte el rango en bloques de ≤90 días automáticamente, no hace falta acortar el rango a mano.

## Reglas de metodología -- no re-derivar

- **Costo sale de Facturación** (Billing API, marketplace `MCLICS`, grupo `ML`), sumado por día real de `creation_date_time` -- NO de la API de Ads. Se probó a fondo: Facturación siempre dio igual o más alto que la API de Ads, y además incluye Display Ads (que la API de Ads no puede reportar bajo ningún ángulo con los permisos actuales). Ver memoria `mercadolibre-base-ads` para toda la investigación que llevó a esta decisión.
- **Ventas atribuidas / Impresiones / Clics** sí salen de la API de Ads (`product_ads/campaigns/search`, `aggregation_type=daily`), sumadas entre todas las campañas del día -- ya no se desglosa por campaña en esta tabla (Lucas lo pidió así para no repetir info; si hace falta ver rendimiento por campaña puntual, consultar la API de Ads directo, no está en el Sheet).
- **"Lo que es un mes, es de ese mes"**: cada día se atribuye por su fecha real, sin importar en qué período de Facturación (que corren 7-a-6, no calendario) haya caído esa entrada -- el script ya recorre todos los períodos que tocan el rango pedido y filtra por fecha real.
- **Columna Factura**: el número de comprobante del período de Facturación que cubre ese día (una sola factura por período, compartida por todos los tipos de cargo). Si el período todavía está abierto (el que cubre "hoy"), la columna dice `"pendiente fc"`.
- **Con IVA vs sin IVA**: división directa por 1,21 en ambas columnas (Costo y Ventas atribuidas), sin excepciones.
- **Ojo con el drift**: incluso un período YA CERRADO puede seguir sumando entradas nuevas días después (confirmado una vez: la misma consulta a Facturación dio $107K más dos días después, con el período cerrado hace más de un mes). Por eso el cache agresivo (ver arriba) es una apuesta consciente de Lucas (2026-07-31) -- si algún número de un período ya cacheado resulta estar mal, borrar esa entrada de `periodos_cerrados` en `base_ads_cache_state.json` a mano para forzar un refetch, no hay otra forma de invalidar el cache.

Ver memoria `mercadolibre-base-ads` para el detalle completo de la investigación (por qué se descartó la API de Ads como fuente de costo, Display Ads, etc.).
