"""
Genera pnl_data.json ENTERO a partir de las tablas base_* -- reemplaza el
viejo flujo manual (compute_venta_detalle.py + compute_pnl_ml.py + carga a
mano de informativo). Ver memoria mercadolibre-pnl-pipeline para el detalle
de por que se llego a esta arquitectura. base_full/base_adelantos (2026-07-31)
son las mas nuevas -- cargos Full (envio + almacenamiento) y adelanto de
disponibilidad de dinero, ninguno capturado antes en ningun lado.

Todo el P&L queda en base CON IVA (misma base que ventas = total_amount de
la orden, que ya viene con IVA) -- logistica_flex/otros_log/otros_cargos
toman importe_con_iva de base_informativa para ser consistentes con el
resto de la suma.

Los PERIODOS (fechas, y que periodo de Facturacion usar para percepciones)
se definen a mano aca abajo -- editar cuando cambien los cortes de mes.

Uso:
    python build_pnl_data.py
"""
import json
from datetime import date

# (fecha_desde, fecha_hasta, period_key para base_impositiva -- None si el
# periodo de facturacion que le corresponde todavia esta abierto)
PERIODOS = {
    'Mayo': ('2026-05-01', '2026-05-31', '2026-06-01'),
    'Junio': ('2026-06-01', '2026-06-30', '2026-07-01'),
    'Julio': ('2026-07-01', '2026-07-31', '2026-08-01'),
    'Agosto (parcial al 23)': ('2026-08-01', '2026-08-23', None),
}

base_ventas = list(json.load(open('base_ventas.json', encoding='utf-8')).values())
base_envios = list(json.load(open('base_envios.json', encoding='utf-8')).values())
base_ads = json.load(open('base_ads.json', encoding='utf-8'))
base_informativa = json.load(open('base_informativa.json', encoding='utf-8'))
base_impositiva = json.load(open('base_impositiva.json', encoding='utf-8'))
base_full = json.load(open('base_full.json', encoding='utf-8'))
base_adelantos = json.load(open('base_adelantos.json', encoding='utf-8'))

INFORMATIVO_CATS = {
    'logistica_flex': 'Logística Flex',
    'otros_log': 'Otros cargos logísticos',
    'otros_cargos': 'Otros cargos',
    'gastos_agencia': 'Gastos de Agencia',
    'autonomos': 'Autónomos',
    'iibb': 'IIBB',
}


def en_rango(fecha, desde, hasta):
    return desde <= fecha <= hasta


pnl_out = {}
for label, (desde, hasta, imp_key) in PERIODOS.items():
    ventas_rows = [r for r in base_ventas if en_rango(r['fecha'], desde, hasta)]
    envios_rows = [r for r in base_envios if en_rango(r['fecha'], desde, hasta)]
    ads_rows = [r for r in base_ads if en_rango(r['fecha'], desde, hasta)]
    inf_rows = [r for r in base_informativa if en_rango(r['fecha'], desde, hasta)]
    full_rows = [r for r in base_full if en_rango(r['fecha'], desde, hasta)]
    adelantos_rows = [r for r in base_adelantos if en_rango(r['fecha'], desde, hasta)]

    ventas = sum(r['importe_c'] for r in ventas_rows)
    cogs = -sum(r['costo_c'] for r in ventas_rows)
    cargo_venta = -sum(r['cargo_var_c'] + r['cargo_fij_c'] for r in ventas_rows)
    envios_ingreso = sum(r['ingreso_c'] for r in envios_rows)
    egreso_envio = sum(r['costo_c'] for r in envios_rows)
    envio_pasante = sum(r['pasante_c'] for r in envios_rows)
    envios_ingreso_flex = envios_ingreso - envio_pasante
    egreso_envio_real = egreso_envio - envio_pasante
    publicidad = sum(r['costo_c'] for r in ads_rows)
    cargo_colecta_full = sum(r['deposito_full_c'] for r in full_rows)
    cargo_almacenamiento_full = sum(r['almacenamiento_full_c'] for r in full_rows)
    adelanto = sum(r['costo_c'] for r in adelantos_rows)

    informativo = {}
    for campo, cat in INFORMATIVO_CATS.items():
        informativo[campo] = sum(r['importe_con_iva'] for r in inf_rows if r['categoria'] == cat)

    if imp_key:
        percepciones = sum(r['importe'] for r in base_impositiva if r['period_key'] == imp_key)
    else:
        percepciones = None

    pnl_out[label] = {
        'ventas': round(ventas, 2), 'envios_ingreso': round(envios_ingreso, 2),
        'envios_ingreso_flex': round(envios_ingreso_flex, 2),
        'cogs': round(cogs, 2), 'cargo_venta': round(cargo_venta, 2), 'egreso_envio': round(egreso_envio, 2),
        'egreso_envio_real': round(egreso_envio_real, 2),
        'envio_pasante': round(envio_pasante, 2),
        'publicidad': round(publicidad, 2),
        'cargo_colecta_full': round(cargo_colecta_full, 2),
        'cargo_almacenamiento_full': round(cargo_almacenamiento_full, 2),
        'adelanto': round(adelanto, 2),
        'logistica_flex': round(informativo['logistica_flex'], 2),
        'otros_log': round(informativo['otros_log'], 2),
        'otros_cargos': round(informativo['otros_cargos'], 2),
        'gastos_agencia': round(informativo['gastos_agencia'], 2),
        'autonomos': round(informativo['autonomos'], 2),
        'percepciones': round(percepciones, 2) if percepciones is not None else None,
        'iibb': round(informativo['iibb'], 2),
        'cargo_neto': True,  # base_ventas siempre es neto (nunca bruto/descuento de Facturacion)
        'n_ordenes': len(ventas_rows),
    }

json.dump(pnl_out, open('pnl_data.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
print('Guardado pnl_data.json:')
for label, m in pnl_out.items():
    print(f"  {label}: {m['n_ordenes']} ordenes, ventas={m['ventas']:,.2f}, cargo_venta={m['cargo_venta']:,.2f}, "
          f"cogs={m['cogs']:,.2f}, publicidad={m['publicidad']:,.2f}, percepciones={m['percepciones']}")
