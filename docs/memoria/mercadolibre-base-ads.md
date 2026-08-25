---
name: mercadolibre-base-ads
description: "The 'base_ads' Sheet tab -- one row per day, Costo from Facturación (real charged amount, Product+Display Ads) plus Ventas atribuidas/Impresiones/Clicks from the Ads API summed across campaigns. Rebuilt 2026-07-24 after a long investigation ruled out the original Ads-API-only design."
metadata:
  node_type: memory
  type: project
  originSessionId: 970f6866-df46-44f9-916d-e89be8e46854
  modified: 2026-07-24T17:00:50.264Z
---

Fourth tab alongside [[mercadolibre-base-ventas]], [[mercadolibre-base-envios]], [[mercadolibre-base-informativa]], [[mercadolibre-base-impositiva]] in the Deleite Sheet. **This is the second design** -- the first version (one row per campaign+day, Costo from the Ads API) was scrapped after Lucas and I spent a long back-and-forth reconciling it against Facturación. Read this whole file before touching `compute_base_ads.py` again; the reasoning matters as much as the current column list.

## Why Costo comes from Facturación, not the Ads API

Compared the Ads API's `cost` metric against Billing (marketplace `MCLICS`) across two different date windows and Facturación was higher both times, never lower. Also found Facturación includes **Display Ads** charges (`detail_sub_type: CDLIT`, transaction_detail "Cargo por campaña de publicidad de Display Ads") that the Ads API structurally cannot report at all -- confirmed by testing `GET /advertising/advertisers?product_id=DISPLAY` (and `BADS` for Brand Ads), both return `404 No permissions found` even though Facturación clearly bills for it. Ruled out several alternative explanations before concluding this:
- Not an IVA mismatch (ratios don't line up with 1.21 in either direction).
- Not percepciones/taxes bundled into the ad charge (`TAXES` is a completely separate `marketplace_info.marketplace` value on its own line items; every MCLICS entry checked was cleanly `detail_type=CHARGE`, `detail_sub_type` in {PADS, CDLIT} only, zero discount/adjustment).
- Not a simple date-shift/timezone issue (day-by-day comparison showed no consistent offset -- sometimes Facturación higher, sometimes the Ads API higher, magnitude and direction both vary).
- Genuinely two separate ML systems (real-time ad reporting vs. billing/invoicing) with different internal attribution logic that don't reconcile -- Lucas's call: use the one that's the real charged amount (pessimistic/conservative for an expense line), which is Facturación.

**Practical consequence: Facturación has no per-campaign breakdown at all** (no `campaign_id`, no name -- just a lump "Cargo por campaña de publicidad de Product Ads" per day). So once Costo moved to Facturación, campaign-level granularity had to go -- Lucas explicitly rejected a two-tier design (daily Facturación total row + per-campaign Ads-API rows below it) as too messy, and chose to drop the `Campaña` column entirely.

## Current design: one row per day

Columns: `Fecha, Costo s/IVA, Costo c/IVA, Ventas atr s/IVA, Ventas atr c/IVA, Impresiones, Clics`.

- **Costo**: Facturación, Billing API, `marketplace_info.marketplace == "MCLICS"`, group `ML`, summed by day using `charge_info.creation_date_time` -- includes BOTH Product Ads and Display Ads (no sub_type filter, since Lucas wants the real total ad expense, not just what the Ads API happens to be able to report on).
- **Ventas atribuidas / Impresiones / Clics**: Ads API (`.../product_ads/campaigns/search`, `aggregation_type=daily`, looped per campaign_id since daily aggregation without a campaign filter collapses everything into one row and daily-per-campaign is the only way to get real per-day figures), **summed across all campaigns** for that day -- Product Ads only, Display Ads has no reporting access.
- **Con/sin IVA**: same as before, straight `/1.21`, no exceptions (both Costo and Ventas atribuidas come con IVA from their sources).

## Attribution: by real date, not by billing period ("lo que es junio es junio")

Lucas's explicit instruction: a day's ad cost belongs to the calendar date it actually happened on, regardless of which billing-period invoice it eventually landed in (periods run 7th-to-6th, not calendar months -- see [[mercadolibre-pnl-pipeline]]). `compute_base_ads.py` fetches every billing period touching the requested date range and filters entries by `creation_date_time` day before summing -- never sums a whole period and labels it with the period's name.

## Open-period stability -- probably OK, but keep watching

Same theoretical risk as [[mercadolibre-base-impositiva]] (MCLICS entries have no `sales_info`, so no per-order fallback exists if a period is unstable while open). In practice, repeated fetches of the currently-open period during this session gave consistent MCLICS counts/totals every time (unlike CORE commission entries, which visibly grew across separate runs) -- so MCLICS billing seems to get written more promptly than CORE does. Not fully proven long-term; if a recent day's Costo ever looks off, re-run and compare.

## Known finding: rebuilding fully from Facturación gave noticeably different Mayo/Junio publicidad totals than what's in `pnl_data.json`

When the full mayo-julio history was recomputed with this new script (2026-07-24), calendar Mayo totaled $407,022.08 and calendar Junio totaled $412,430.51 -- both meaningfully higher than the `publicidad` figures currently sitting in `pnl_data.json` (Mayo $299,937.04, Junio $340,851.66, last refreshed 2026-07-22). Most likely explanation: those older figures were captured before some MCLICS billing entries had fully materialized (the same kind of async-generation lag documented for CORE commission entries), and this fresher fetch is more complete/authoritative. **Not yet propagated into `pnl_data.json` -- flagged to Lucas, needs his confirmation before overwriting the P&L's publicidad numbers.**

## Columns (current, with Factura added)

`Fecha, Factura, Costo s/IVA, Costo c/IVA, Ventas atr s/IVA, Ventas atr c/IVA, Impresiones, Clics`.

`Factura` = the `legal_document_number` of the ONE invoice covering that day's billing period (periods run 7th-to-6th; every charge type -- CORE, SHIPPING, MCLICS, TAXES -- in a period shares the same `document_id`/`legal_document_number`, confirmed by cross-checking a TAXES entry and an MCLICS entry from the same period). For the currently-open period (the one covering "today", computed via `billing_period_for_date(date.today())`), the value is the literal string `"pendiente fc"` -- that period hasn't been invoiced yet. Look up any single entry from a period's fetch to get its `legal_document_number`; it's uniform across the whole period so one sample is enough.

## Open question: do "closed" periods actually stay closed?

Investigating why Mayo's recomputed total ($407,022.08) was $107,085.04 higher than the figure captured just 2 days earlier (2026-07-22), checked all 72 MCLICS entries in Mayo's covering period (`2026-06-01`, closed since 2026-07-07 -- weeks before this check) and found they **all share one single invoice** (`document_id` 4797263694, `legal_document_number` "0011A04964303"), all `legal_document_status: PROCESSED` -- no sign of a separate pending/correction document. So the growth isn't visible as "a second invoice arrived" -- it looks like ML can silently add rows to an already-issued, already-processed invoice's underlying data without changing its document reference. **Not fully proven** (no snapshot from 2026-07-22 was saved to diff against), but it's the most consistent explanation available. Re-fetching the exact same query twice more (minutes apart, 2026-07-24) gave identical totals both times, so within a short window it does look stable -- the growth seems to happen over longer timescales (days), not query-to-query.

**Practical implication**: even a period whose invoice shows `PROCESSED` and has been closed for over a month should not be assumed permanently final for MCLICS. If a number here ever looks stale, recompute -- don't assume last week's fetch is still authoritative.

## Scripts

- `compute_base_ads.py <fecha_desde> <fecha_hasta>` -- rewrites `base_ads.json` fully each run (list of daily records).
- `build_base_ads_sheet.py` -- clears + rewrites the `base_ads` tab.

## Full historical build done 2026-07-24

Mayo 1 through 2026-07-24, 85 daily records, each tagged with its invoice number (or "pendiente fc" for the still-open period).
