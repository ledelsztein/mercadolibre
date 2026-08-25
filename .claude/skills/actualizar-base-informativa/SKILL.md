---
name: actualizar-base-informativa
description: "Agrega/actualiza registros en la pestaña 'base_informativa' del Google Sheet de Deleite (MercadoLibre) -- el libro a mano de facturas y gastos que Lucas pasa (logística Flex, otros cargos logísticos, otros cargos, autónomos, IIBB). Usar SIEMPRE que Lucas pase una factura, un gasto, o diga cosas como 'sumá esto como...', 'cargá este gasto', o cuando el pipeline de P&L necesite un dato informativo que todavía no está cargado -- ahí hay que PEDÍRSELO explícitamente, nunca asumir $0 ni copiar el mes anterior."
---

# Actualizar base_informativa (Deleite / MercadoLibre)

Repo: `C:\Users\User\Projects\mercadolibre`. Todos los comandos se corren parados ahí.

A diferencia de las otras `base_*`, esta tabla **no sale de ninguna API** -- es 100% lo que Lucas pasa a mano (facturas, gastos de logística, autónomos, IIBB). No hay script `compute_*` para esta, `base_informativa.json` se edita directamente.

## Cómo agregar un registro nuevo

1. Leer `base_informativa.json` para ver el formato y no duplicar una entrada ya cargada.
2. Agregar un registro con `{"fecha", "categoria", "detalle", "importe_sin_iva", "importe_con_iva"}`. Categorías usadas hasta ahora: `Logística Flex`, `Otros cargos logísticos` (proveedores vistos: Alan Jalef, Speed Business/Lappiel, Nogal Suplementos Envío), `Otros cargos`, `Autónomos`, `IIBB`.
3. Calcular `importe_con_iva`:
   - **Facturas/gastos reales** (Logística Flex, Otros cargos logísticos, Otros cargos): `importe_con_iva = importe_sin_iva * 1.21`.
   - **Pagos de impuestos** (Autónomos, IIBB): no tienen IVA -- `importe_con_iva = importe_sin_iva` (mismo valor en las dos columnas).
   - **Excepción dentro de "gastos reales": proveedor monotributista** -- si Lucas aclara que el proveedor es monotributista (confirmado con Alan Jalef, 2026-08-07), tampoco aplica el ×1,21 aunque la categoría sea "Otros cargos logísticos" -- `importe_con_iva = importe_sin_iva`. **Siempre preguntar** si el importe que pasa Lucas es con o sin IVA, y si el proveedor es monotributista, antes de asumir el ×1,21 por defecto.
4. Subir al Sheet:

```bash
python build_base_informativa_sheet.py
```

## Regla clave: siempre preguntar, nunca asumir

Si en algún momento (armando el P&L, actualizando el tablero) falta un dato de esta tabla para un período nuevo o extendido, **preguntarle a Lucas explícitamente** -- no copiar el valor del mes anterior, no asumir $0, no inventar. Si él confirma "sin cambios" respecto de un valor ya cargado, se puede reetiquetar la fecha del registro existente (ver ejemplo real: "Julio parcial al 21" pasó a "al 23" con el mismo importe, marcado en el `detalle` como "sin cambios").

`Percepciones` **no** se carga acá -- esa sale de Facturación vía `base_impositiva` (ver esa skill/memoria), porque no es un dato que Lucas pase a mano.

Ver memoria `mercadolibre-base-informativa` para más contexto.
