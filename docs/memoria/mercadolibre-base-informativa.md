---
name: mercadolibre-base-informativa
description: "The 'base_informativa' Sheet tab -- a manually-fed ledger for data Lucas provides that isn't derivable from the MercadoLibre/MercadoPago API (invoices, logistics costs, taxes). How to add entries and when to ask Lucas for missing data."
metadata:
  node_type: memory
  type: project
  originSessionId: 970f6866-df46-44f9-916d-e89be8e46854
  modified: 2026-07-24T14:28:46.393Z
---

Companion tab to [[mercadolibre-base-ventas]] and [[mercadolibre-base-envios]] in the same Sheet, but the opposite data source: those two are 100% API-derived; `base_informativa` is 100% what Lucas tells us -- invoices, "otros cargos", logística flex, autónomos, IIBB, and anything else that isn't in an order/payment/shipment object.

**Why:** "Que ahí vayas volcando toda la información que te voy pasando como las facturas, gastos adicionales, etc... Si hay datos que no tenes, siempre debes pedirlos en esta hoja." -- this replaces the old ad-hoc "ask Lucas for the informativo fields each time" step in [[mercadolibre-pnl-pipeline]] with a persistent, itemized record instead of just a monthly lump sum in `pnl_data.json`.

## How it works

- `base_informativa.json` -- plain list of records: `{"fecha", "categoria", "detalle", "importe_sin_iva", "importe_con_iva"}`. No API calls, no script computes this -- it's populated by hand (via Edit/Write) whenever Lucas gives new data in conversation.
- `build_base_informativa_sheet.py` -- pushes the JSON to the `base_informativa` tab (same clear-then-write pattern as base_ventas/base_envios).
- Columns in the Sheet: `Fecha, Categoría, Detalle, Importe s/IVA, Importe c/IVA`.

## Rule: always ask, never fabricate

When building the P&L (or anything else) and a needed field isn't in `base_informativa.json` yet, **ask Lucas for it and add it as a new entry here** -- don't estimate, don't carry forward a prior month's figure, don't leave it silently at 0. This mirrors the "no asumas nada" rule already established for the rest of the pipeline.

## Con IVA vs sin IVA per category

- **Real invoiced expenses** (logística Flex, otros cargos logísticos, otros cargos/facturas varias) -- these DO have an IVA component. `importe_con_iva = importe_sin_iva * 1.21`.
- **Tax payments themselves** (Autónomos, IIBB) -- these are NOT subject to IVA (same treatment as "Impuestos de la operación" in `base_ventas`). Convention chosen: `importe_con_iva == importe_sin_iva` (same value in both columns, since there's genuinely no IVA to add) rather than leaving one blank. **This was my own call, not explicitly confirmed by Lucas -- flag it and double check if it ever looks off.**
- `Percepciones` is NOT tracked here -- it comes from the Billing API (TAXES marketplace, needs the period closed), not from Lucas manually, so it stays in `pnl_data.json` only.

## Backfill done 2026-07-23

Migrated the monthly aggregate totals already in `pnl_data.json` (Mayo, Junio, Julio parcial al 21) into one row per category per month here, explicitly labeled in `Detalle` as "(backfill, no desglosado por factura)" since we only have the monthly total, not the itemized invoices. Lucas chose this over leaving the tab empty. If he later provides the actual itemized invoices for these months, replace the corresponding backfill row(s) rather than leaving both.

## Still open

`pnl_data.json`'s informativo fields (`logistica_flex`, `otros_log`, `otros_cargos`, `autonomos`, `iibb`) and this tab are currently **two separate places holding the same numbers** for historical months -- not yet wired together. Worth asking Lucas whether `build_dashboard_data.py`/`build_sheet.py` should eventually sum `base_informativa.json` by month/category to derive those `pnl_data.json` fields automatically, instead of both being maintained by hand in parallel.
