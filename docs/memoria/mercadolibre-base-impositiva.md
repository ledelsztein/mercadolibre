---
name: mercadolibre-base-impositiva
description: "The 'base_impositiva' Sheet tab -- one row per individual percepción/retención (Billing API, marketplace TAXES, groups ML+MP), so Lucas can see month-to-month what he's paying by jurisdiction/tax type."
metadata:
  node_type: memory
  type: project
  originSessionId: 970f6866-df46-44f9-916d-e89be8e46854
  modified: 2026-07-24T15:55:32.532Z
---

Fifth tab alongside [[mercadolibre-base-ventas]], [[mercadolibre-base-envios]], [[mercadolibre-base-informativa]], [[mercadolibre-base-ads]] in the Deleite Sheet. This is the itemized version of the `percepciones` lump-sum field already in `pnl_data.json` (see [[mercadolibre-pnl-pipeline]]).

**Why:** "Necesito entender bien, mes a mes qué estoy pagando a nivel percepciones y retenciones."

## Source: Billing API, marketplace `TAXES`, BOTH groups ML and MP

Same endpoint used for CORE (commission) entries elsewhere in the pipeline, filtered to `marketplace_info.marketplace == "TAXES"`. **Must query both the `ML` group and the `MP` group and combine them** -- ML has the bulk (mostly IIBB per province: Buenos Aires, CABA, Corrientes, Catamarca, Neuquén, Salta, La Pampa, plus IVA percepciones like "Percepción especial de IVA RG5319/2023", plus two Mercado-Envíos-specific IIBB entries), MP has a smaller parallel set of the same tax types charged on MercadoPago's side. Missing either group undercounts.

**Verified exact match against existing `pnl_data.json` figures** (2026-07-23): billing period `2026-06-01` totals $132,970.14 = Mayo's `percepciones` field exactly; period `2026-07-01` totals $324,014.47 = Junio's exactly. Confirms this is the right source and the existing monthly aggregate was already correct.

## No per-order fallback exists for TAXES entries

Unlike CORE entries (commission), these `TAXES` entries have `sales_info: null` -- they are **not tied to individual orders at all**. They get invoiced in one lump batch on the day the billing period closes (the 7th of the following month) -- every entry in a period shares the same `creation_date_time`. This means:
- **`base_impositiva` can only be built from CLOSED periods.** There is no per-order workaround like the `--neto` mode used for `base_ventas`/`compute_pnl_ml.py` when a period is still open -- if the whole-period scan comes back with an inconsistent count (the same open-period instability documented in [[mercadolibre-pnl-pipeline]]), there's nothing to fall back to. `compute_base_impositiva.py` will just raise an error in that case rather than silently guessing.
- "Fecha" in this table is the **invoice/closing date of the billing period**, not any particular sale date -- percepciones don't have per-sale dates, only per-period ones.

## Billing periods run 7th-to-6th, not calendar months

Period key `2026-06-01` covers ~May 7 to June 6; `2026-07-01` covers ~June 7 to July 6, etc. So a period key doesn't line up with a calendar month, and a calendar month's percepciones can legitimately span two period keys at the edges. For the mayo-julio P&L, the periods that matter are `2026-05-01` (mostly April, only May 1-6 -- **not currently reflected in any monthly total, it's outside the tracked range**), `2026-06-01` (= Mayo's number), `2026-07-01` (= Junio's number). July's own period (`2026-08-01`) won't be usable until it closes 2026-08-07.

## Columns

`Fecha, Grupo (ML/MP), Categoría, Detalle, Importe` -- Categoría is the API's own `transaction_detail` text (already descriptive, e.g. "Percepción impuesto IIBB Buenos Aires"), Detalle holds the `document_id` for traceability. No con/sin-IVA split (these are the tax itself, not subject to IVA -- same treatment as `Impuestos de la operación` in `base_ventas`).

## Scripts

- `compute_base_impositiva.py <period_key> [<period_key> ...]` -- pass explicit CLOSED period keys (e.g. `2026-05-01 2026-06-01 2026-07-01`). Rewrites `base_impositiva.json` fully each run (closed periods don't change, so no need to merge).
- `build_base_impositiva_sheet.py` -- clears + rewrites the tab, same pattern as the other base_* tabs.

## Full historical build done 2026-07-23

37 registros across the 3 closed periods (2026-05-01, 2026-06-01, 2026-07-01).
