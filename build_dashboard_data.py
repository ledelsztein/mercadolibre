"""
Genera dashboard_data.json (a partir de pnl_data.json + base_ventas.json +
base_envios.json + cat_names.json) y arma dashboard_output.html listo para
publicar como Artifact.

base_ventas.json (generado por compute_base_ventas.py) tiene un registro por
orden con venta/costo/cargo ya resueltos (siempre neto, sin desglose de
descuentos -- ver mercadolibre-base-ventas). base_envios.json tiene el
ingreso/costo real de envio por orden (ya prorrateado si el shipment es
compartido) -- se cruzan por order_id para sacar el envio neto de cada venta.
De ahi se calculan "Rentabilidad por producto", "Por Categoria" y "Envios
por tipo" de forma consistente (mismo Resultado Neto en los tres).

Los PERIODOS (mismos rangos de fecha que build_pnl_data.py) definen que
ordenes caen en Mayo/Junio/Julio/Hoy -- mantener sincronizados los dos
scripts si cambian los cortes de mes.

Uso:
    python build_dashboard_data.py
"""
import json
import os
from datetime import date

PNL = json.load(open('pnl_data.json', encoding='utf-8'))
CAT_NAMES = json.load(open('cat_names.json', encoding='utf-8'))

# (periodo corto para dashboard_data.json, fecha_desde, fecha_hasta) -- el
# periodo corto debe ser la primera palabra en minuscula del label de PNL
PERIODOS = [
    ('mayo', '2026-05-01', '2026-05-31'),
    ('junio', '2026-06-01', '2026-06-30'),
    ('julio', '2026-07-01', '2026-07-31'),
    ('agosto', '2026-08-01', '2026-08-23'),
]

mes_key_by_label = {label.lower().split(' ')[0]: label for label in PNL}

for label, m in PNL.items():
    m['label'] = label
    m['parcial'] = '(parcial' in label.lower()
    m['total_ingresos'] = m['ventas'] + m['envios_ingreso']
    m['total_egresos'] = (m['cogs'] + m['cargo_venta'] + m['egreso_envio'] + m['publicidad']
                            + m['logistica_flex'] + m['otros_log'] + m['otros_cargos'] + m['gastos_agencia']
                            + m['cargo_colecta_full'] + m['cargo_almacenamiento_full'] + m['adelanto'])
    m['resultado_bruto'] = m['total_ingresos'] - m['total_egresos']
    m['margen_bruto'] = m['resultado_bruto'] / m['ventas'] if m['ventas'] else 0
    m['total_impuestos'] = m['autonomos'] + (m['percepciones'] or 0) + m['iibb']
    m['resultado_neto'] = m['resultado_bruto'] - m['total_impuestos'] if m['percepciones'] is not None else None
    m['margen_neto'] = (m['resultado_neto'] / m['ventas']) if (m['resultado_neto'] is not None and m['ventas']) else None

    # Punto de equilibrio: clasificacion fijo/variable pedida por Lucas
    # (impuestos -- IIBB y percepciones -- quedan afuera del calculo).
    # cargo_colecta_full/cargo_almacenamiento_full/adelanto (2026-07-31)
    # tambien son Costo Variable, per Lucas.
    m['costos_variables'] = (m['cogs'] + m['cargo_venta'] + m['egreso_envio'] + m['logistica_flex'] + m['otros_log']
                              + m['cargo_colecta_full'] + m['cargo_almacenamiento_full'] + m['adelanto'])
    m['costos_fijos'] = m['publicidad'] + m['otros_cargos'] + m['gastos_agencia'] + m['autonomos']
    m['margen_contribucion'] = m['total_ingresos'] - m['costos_variables']
    m['margen_contribucion_pct'] = m['margen_contribucion'] / m['ventas'] if m['ventas'] else 0
    m['punto_equilibrio'] = (m['costos_fijos'] / m['margen_contribucion_pct']) if m['margen_contribucion_pct'] > 0 else None
    m['pct_punto_equilibrio'] = (m['ventas'] / m['punto_equilibrio']) if m['punto_equilibrio'] else None

base_ventas_all = list(json.load(open('base_ventas.json', encoding='utf-8')).values())
base_envios_all = list(json.load(open('base_envios.json', encoding='utf-8')).values())
envio_neto_by_order = {r['order_id']: r['costo_c'] - r['ingreso_c'] for r in base_envios_all}

pnl_out = {}
for periodo, _, _ in PERIODOS:
    if periodo in mes_key_by_label:
        pnl_out[periodo] = PNL[mes_key_by_label[periodo]]

productos = {}
categorias = {}
envios_tipo = {}
for periodo, desde, hasta in PERIODOS:
    registros = [r for r in base_ventas_all if desde <= r['fecha'] <= hasta]
    if not registros:
        continue

    by_item = {}
    by_tipo = {}
    for r in registros:
        venta = r['importe_c']
        costo = -r['costo_c']
        cargo = -(r['cargo_var_c'] + r['cargo_fij_c'])
        envio = envio_neto_by_order.get(r['order_id'], 0.0)

        item = by_item.setdefault(r['item_id'], {
            'sku': r['sku'], 'title': r['title'], 'cat_id': r.get('cat_id'), 'qty': 0,
            'venta': 0.0, 'costo': 0.0, 'cargo': 0.0, 'envio': 0.0,
        })
        item['qty'] += r['qty']
        item['venta'] += venta
        item['costo'] += costo
        item['cargo'] += cargo
        item['envio'] += envio

        t = by_tipo.setdefault(r['tipo_envio'], {'shipments': 0, 'venta': 0.0, 'costo': 0.0, 'cargo': 0.0, 'envio': 0.0})
        t['shipments'] += 1
        t['venta'] += venta
        t['costo'] += costo
        t['cargo'] += cargo
        t['envio'] += envio

    plist = []
    for item_id, d in by_item.items():
        resultado_neto = d['venta'] - d['cargo'] - d['envio'] - d['costo']
        margen_pct = resultado_neto / d['venta'] if d['venta'] else 0
        plist.append({
            'sku': d['sku'], 'item_id': item_id, 'title': d['title'], 'cat': CAT_NAMES.get(d['cat_id'], d['cat_id']),
            'qty': d['qty'], 'ventas': round(d['venta'], 2), 'costo': round(d['costo'], 2),
            'cargo': round(d['cargo'], 2), 'descuento': 0.0, 'envio': round(d['envio'], 2),
            'margen': round(resultado_neto, 2), 'margen_pct': round(margen_pct, 4),
        })
    plist.sort(key=lambda x: -x['margen'])
    productos[periodo] = plist

    by_cat = {}
    for p in plist:
        c = by_cat.setdefault(p['cat'], {'qty': 0, 'venta': 0.0, 'costo': 0.0, 'margen': 0.0})
        c['qty'] += p['qty']
        c['venta'] += p['ventas']
        c['costo'] += p['costo']
        c['margen'] += p['margen']
    clist = []
    for cat_name, c in by_cat.items():
        margen_pct = c['margen'] / c['venta'] if c['venta'] else 0
        clist.append({
            'cat': cat_name, 'qty': c['qty'], 'ventas': round(c['venta'], 2), 'costo': round(c['costo'], 2),
            'margen': round(c['margen'], 2), 'margen_pct': round(margen_pct, 4),
        })
    clist.sort(key=lambda x: -x['ventas'])
    categorias[periodo] = clist

    tlist = []
    for tipo, t in sorted(by_tipo.items(), key=lambda x: -x[1]['venta']):
        egreso_total = t['cargo'] + t['costo'] + t['envio']
        tlist.append({
            'tipo': tipo, 'tipo_key': tipo,
            'shipments': t['shipments'], 'ingreso': round(t['venta'], 2),
            'egreso': round(egreso_total, 2),
        })
    envios_tipo[periodo] = tlist

# ---------- vistas pivotadas (todos los meses en columnas, sin repetir filas -- mismo criterio que el Sheet) ----------
periodos_presentes = [p for p, _, _ in PERIODOS if p in productos]
meses_pivot = [{'key': p, 'label': pnl_out[p]['label']} for p in periodos_presentes if p in pnl_out]

categorias_pivot = {}
productos_pivot = {}
for p in periodos_presentes:
    for c in categorias[p]:
        cp = categorias_pivot.setdefault(c['cat'], {'cat': c['cat'], 'meses': {}})
        cp['meses'][p] = {'venta': c['ventas'], 'costo': c['costo'], 'margen': c['margen']}
    for pr in productos[p]:
        pp = productos_pivot.setdefault(pr['item_id'], {'item_id': pr['item_id'], 'sku': pr['sku'], 'title': pr['title'], 'cat': pr['cat'], 'meses': {}})
        pp['meses'][p] = {'venta': pr['ventas'], 'costo': pr['costo'], 'margen': pr['margen']}

for cp in categorias_pivot.values():
    cp['total'] = {
        'venta': round(sum(v['venta'] for v in cp['meses'].values()), 2),
        'costo': round(sum(v['costo'] for v in cp['meses'].values()), 2),
        'margen': round(sum(v['margen'] for v in cp['meses'].values()), 2),
    }
for pp in productos_pivot.values():
    pp['total'] = {
        'venta': round(sum(v['venta'] for v in pp['meses'].values()), 2),
        'costo': round(sum(v['costo'] for v in pp['meses'].values()), 2),
        'margen': round(sum(v['margen'] for v in pp['meses'].values()), 2),
    }

categorias_pivot_list = sorted(categorias_pivot.values(), key=lambda c: -c['total']['margen'])
productos_pivot_list = sorted(productos_pivot.values(), key=lambda p: -p['total']['margen'])

venta_total_mes = {p: sum(t['ingreso'] for t in envios_tipo[p]) for p in periodos_presentes}
envios_pivot = {}
for p in periodos_presentes:
    for t in envios_tipo[p]:
        ep = envios_pivot.setdefault(t['tipo'], {'tipo': t['tipo'], 'meses': {}})
        ep['meses'][p] = t['ingreso']
tot_venta_todos_meses = sum(venta_total_mes.values())
for ep in envios_pivot.values():
    ep['total'] = round(sum(ep['meses'].values()), 2)
    ep['total_pct'] = round(ep['total'] / tot_venta_todos_meses, 4) if tot_venta_todos_meses else 0
    ep['meses_pct'] = {p: round(v / venta_total_mes[p], 4) if venta_total_mes.get(p) else 0 for p, v in ep['meses'].items()}
envios_pivot_list = sorted(envios_pivot.values(), key=lambda e: -e['total'])

# ---------- listado de ordenes individuales (para el filtro Fecha/Order_ID del dashboard) ----------
ordenes = []
for r in base_ventas_all:
    venta = r['importe_c']
    costo = -r['costo_c']
    cargo = -(r['cargo_var_c'] + r['cargo_fij_c'])
    envio = envio_neto_by_order.get(r['order_id'], 0.0)
    resultado_neto = venta - cargo - envio - costo
    ordenes.append({
        'order_id': str(r['order_id']), 'pack_id': str(r['pack_id']) if r.get('pack_id') else '',
        'fecha': r['fecha'], 'item_id': r['item_id'], 'sku': r['sku'], 'title': r['title'],
        'cat': CAT_NAMES.get(r.get('cat_id'), r.get('cat_id')), 'tipo_envio': r['tipo_envio'], 'qty': r['qty'],
        'venta': round(venta, 2), 'costo': round(costo, 2), 'cargo': round(cargo, 2), 'envio': round(envio, 2),
        'margen': round(resultado_neto, 2), 'margen_pct': round(resultado_neto / venta, 4) if venta else 0,
    })
ordenes.sort(key=lambda o: o['fecha'], reverse=True)

# ---------- ventas moviles de 7 dias (suma de cada dia + los 6 anteriores) ----------
daily_ventas = {}
for r in base_ventas_all:
    daily_ventas[r['fecha']] = daily_ventas.get(r['fecha'], 0.0) + r['importe_c']

fechas_presentes = sorted(daily_ventas)
if fechas_presentes:
    d0 = date.fromisoformat(fechas_presentes[0])
    d1 = date.fromisoformat(fechas_presentes[-1])
    todas_las_fechas = []
    d = d0
    while d <= d1:
        todas_las_fechas.append(d.isoformat())
        d = date.fromordinal(d.toordinal() + 1)
else:
    todas_las_fechas = []

ventas_moviles_7d = []
for i, f in enumerate(todas_las_fechas):
    ventana = todas_las_fechas[max(0, i - 6):i + 1]
    suma_movil = sum(daily_ventas.get(x, 0.0) for x in ventana)
    ventas_moviles_7d.append({
        'fecha': f, 'venta_dia': round(daily_ventas.get(f, 0.0), 2), 'movil_7d': round(suma_movil, 2),
    })

visitas = []
if os.path.exists('base_visitas.json'):
    visitas = [
        {'fecha': r['fecha'], 'visitas': r['visitas'], 'compras': r['compras'], 'cvr': r['cvr']}
        for r in json.load(open('base_visitas.json', encoding='utf-8'))
    ]
    visitas.sort(key=lambda r: r['fecha'])

output = {
    'pnl': pnl_out, 'productos': productos, 'categorias': categorias, 'envios_tipo': envios_tipo,
    'meses_pivot': meses_pivot, 'categorias_pivot': categorias_pivot_list, 'productos_pivot': productos_pivot_list,
    'envios_pivot': envios_pivot_list, 'ordenes': ordenes, 'ventas_moviles_7d': ventas_moviles_7d,
    'visitas': visitas,
}
with open('dashboard_data.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, separators=(',', ':'))
print('Guardado dashboard_data.json (', len(json.dumps(output)), 'bytes )')

# ---------- notas dinamicas ----------
notes = []
for periodo, m in pnl_out.items():
    if m['parcial']:
        notes.append(f"<li><b>{m['label']}</b> está parcial — todavía no incluye el resto del mes.</li>")
    if m['percepciones'] is None:
        notes.append(f"<li><b>Percepciones y Retenciones</b> de {m['label']} recién se conocen cuando MercadoLibre cierra el período de facturación.</li>")
notes.append("<li>Todo el P&L (Ventas, Cargos, Costos, Envíos, Publicidad, Informativo) sale ahora de las tablas <b>base_ventas / base_envios / base_ads / base_informativa / base_impositiva</b> del Sheet — ya no hay carga manual de estos números.</li>")
notes.append("<li>En \"Rentabilidad por producto\", \"Por categoría\" y \"Envíos por tipo\", el <b>Resultado Neto</b> es Venta − Cargo por venta − Envío − Costo de producto (ya no hay línea de Descuentos: el cargo por venta viene siempre neto, ver base_ventas).</li>")
notes.append("<li>El <b>Costo de producto</b> (COGS) se toma de la planilla de costos, que viene sin IVA, y se le suma 21% para quedar en la misma base que la Venta (que sí incluye IVA) — sin este ajuste el resultado quedaba inflado.</li>")
notes.append("<li>La <b>Publicidad</b> sale de Facturación (lo que Mercado Libre realmente cobra, incluye Product Ads y Display Ads) — la tabla base_ads con el detalle de campaña/clicks/impresiones es informativa y no necesariamente suma igual.</li>")

template = open('dashboard_template.html', encoding='utf-8').read()
template = template.replace('__DATA_JSON__', json.dumps(output, ensure_ascii=False))
template = template.replace('__FECHA_ACTUALIZACION__', f'Actualizado {date.today().strftime("%d %b %Y")}')
template = template.replace('<ul id="notes-extra"></ul>', '<ul id="notes-extra">' + ''.join(notes) + '</ul>')

with open('dashboard_output.html', 'w', encoding='utf-8') as f:
    f.write(template)
print('Guardado dashboard_output.html -- listo para publicar con la herramienta Artifact')
