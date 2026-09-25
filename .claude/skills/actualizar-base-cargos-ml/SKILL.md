---
name: actualizar-base-cargos-ml
description: "Actualiza la pestaña 'base_cargos_ml' del Google Sheet de Deleite (MercadoLibre) -- una fila por día con cargos de Facturación que no aparecen en ninguna otra tabla: mantenimiento de Mi página y cargos por devoluciones, con y sin IVA. Usar SIEMPRE que Lucas pida actualizar, completar o correr base_cargos_ml, o pregunte por el cargo de Mi página o por las devoluciones -- incluso si no menciona el nombre exacto de la pestaña."
---

# Actualizar base_cargos_ml (Deleite / MercadoLibre)

Repo: raíz del checkout de `ledelsztein/mercadolibre`. Todos los comandos se corren parados ahí.

Tabla nueva (2026-09-25, pedido de Lucas): revisando toda la Facturación aparecieron dos cargos
reales que no estaban en ninguna línea del P&L. Igual que `base_full`, **no necesita order_ids**
-- siempre se llama con el rango completo mayo-hoy, y el script cachea agresivamente (mismo patrón
que `base_ads`/`base_full`, cache en `base_cargos_ml_cache_state.json`).

## Paso único -- recalcular y subir

```bash
python compute_base_cargos_ml.py 2026-05-01 <fecha_hasta>
python build_base_cargos_ml_sheet.py
```

**Antes de definir `<fecha_hasta>`, correr `date +%Y-%m-%d`** (mismo criterio de día cerrado que el
resto del tablero: `hoy - 1`).

## Reglas de metodología -- no re-derivar

- **Fuente: Facturación (Billing API), grupo `ML`.**
- **Mantenimiento de Mi página** = marketplace `ESHOP`, `detail_sub_type` `CESM` + `BESM`
  (anulación). Entre mayo y julio 2026 ML lo cobró y lo anuló cada mes (neto $0); desde el 14/07 se
  cobra de verdad (~$13-16K por mes). **Costo Fijo** en el punto de equilibrio.
- **Devoluciones** = marketplace `SHIPPING`, `detail_sub_type` `CDSD` + `BDSD` (anulación, si
  aparece). **Costo Variable** en el punto de equilibrio.
- Las dos suman a Total Egresos (`mi_pagina`, `devoluciones` en `pnl_data.json`).
- **Entradas `detail_type == "BONUS"` (anulaciones) restan.**
- **Con IVA vs sin IVA**: Facturación viene CON IVA -- división directa por 1,21.
- Cada cargo se atribuye por su fecha real (`creation_date_time`), no por el período de Facturación.
- Si algún número de un período ya cacheado resulta estar mal, borrar esa entrada de
  `periodos_cerrados` a mano para forzar un refetch.
