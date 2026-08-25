---
name: actualizar-base-adelantos
description: "Actualiza la pestaña 'base_adelantos' del Google Sheet de Deleite (MercadoLibre) -- una fila por día con el 'Cargo por adelanto de disponibilidad de dinero en cuenta', con y sin IVA. Usar SIEMPRE que Lucas pida actualizar, completar o correr base_adelantos, o pida 'el adelanto de dinero', 'el cargo de adelanto' -- incluso si no menciona el nombre exacto de la pestaña."
---

# Actualizar base_adelantos (Deleite / MercadoLibre)

Repo: `C:\Users\User\Projects\mercadolibre`. Todos los comandos se corren parados ahí.

Tabla nueva (2026-07-31, pedido de Lucas): el "Cargo por adelanto de disponibilidad de dinero en cuenta" que MercadoPago cobra, no capturado en ningún otro lado del pipeline. Igual que `base_ads`/`base_full`, **no necesita order_ids** -- siempre se llama con el rango completo mayo-hoy, y el script (`compute_base_adelantos.py`) cachea agresivamente (mismo patrón, ver `actualizar-base-ads`).

## Paso único -- recalcular y subir

```bash
python compute_base_adelantos.py 2026-05-01 <fecha_hasta_hoy>
python build_base_adelantos_sheet.py
```

**Antes de definir `<fecha_hasta_hoy>`, correr `date +%Y-%m-%d` para confirmar la fecha real del sistema.**

## Reglas de metodología -- no re-derivar

- **Fuente: Facturación (Billing API), grupo `MP`** (¡no `ML`! -- distinto del resto de las tablas de este pipeline salvo por el hecho de que es el mismo endpoint), marketplace `MP`, `detail_sub_type` `CRIA` ("Cargo por adelanto de disponibilidad de dinero en cuenta").
- **Tratado como Costo Variable** en el punto de equilibrio del P&L (pedido explícito de Lucas, 2026-07-31) -- se suma en `build_pnl_data.py`/`build_dashboard_data.py`/`build_sheet.py` a `costos_variables` y a `total_egresos`.
- **Con IVA vs sin IVA**: los montos de Facturación vienen CON IVA -- división directa por 1,21 para sin IVA, sin excepciones.
- **Cache agresivo**: un período se marca "cerrado" en cuanto deja de ser el período abierto de "hoy" y nunca se vuelve a pedir (cache en `base_adelantos_cache_state.json`). Un período cerrado se cachea SIEMPRE, incluso sin ninguna entrada `CRIA` ese período -- **el grupo `MP` puede tener 0 entradas TOTALES en un período** (confirmado: mayo/junio 2026 tuvieron 0 entradas de cualquier tipo en el grupo MP, a diferencia del grupo `ML` que siempre tiene algo), así que no hay ninguna factura que descubrir ese período. Si el cache dependiera de encontrar una factura real, esos períodos nunca se cachearían y se volverían a pedir para siempre (bug real encontrado y corregido 2026-07-31, mismo bug latente corregido también en `compute_base_ads.py`/`compute_base_full.py` por las dudas). Si algún número de un período ya cacheado resulta estar mal, borrar esa entrada de `periodos_cerrados` a mano para forzar un refetch.

Ver memoria `mercadolibre-pnl-pipeline` (sección "base_full / base_adelantos") para el contexto completo de por qué se armó esta tabla.
