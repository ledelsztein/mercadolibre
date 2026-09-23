"""
Re-verifica el status de las ordenes de los ultimos 30 dias (no de todo el
historial desde mayo) para detectar ordenes que eran "paid" cuando se
guardaron/computaron y despues pasaron a cancelled/refunded -- MercadoLibre
no permite que una orden cambie de status pasado ese plazo (pedido de Lucas,
2026-09-17), asi que no hace falta ni conviene (por costo de API) revisar
mas atras.

fetch_orders.fetch_and_merge() ya re-aplica el filtro de validez cuando se
re-pide un rango de fechas -- lo que faltaba era: (a) hacer eso de rutina
para los ultimos 30 dias en cada corrida, y (b) sacar de base_ventas.json /
base_envios.json las ordenes que ese refresh detecta como ya no validas
(antes solo se sacaban si justo volvian a pasarse como argumento explicito a
compute_base_ventas.py/compute_base_envios.py).

Uso:
    python verificar_status_reciente.py
"""
import json
from datetime import date, timedelta

from fetch_orders import fetch_and_merge

DIAS_ATRAS = 30
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
          'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']


def ultimo_dia_mes(d):
    if d.month == 12:
        return d.replace(day=31)
    return d.replace(month=d.month + 1, day=1) - timedelta(days=1)


def rangos_por_mes(desde, hasta):
    """Parte [desde, hasta] en sub-rangos que no cruzan un mes calendario."""
    rangos = []
    d = desde
    while d <= hasta:
        fin_mes = min(ultimo_dia_mes(d), hasta)
        rangos.append((MESES[d.month - 1], d.isoformat(), fin_mes.isoformat()))
        d = fin_mes + timedelta(days=1)
    return rangos


def main():
    hoy = date.today()
    desde = hoy - timedelta(days=DIAS_ATRAS)
    hasta = hoy - timedelta(days=1)  # dia cerrado, misma convencion que el resto del pipeline

    validos = set()
    for mes, f_desde, f_hasta in rangos_por_mes(desde, hasta):
        print(f'Re-verificando {mes} ({f_desde}..{f_hasta})...')
        fetch_and_merge(mes, f_desde, f_hasta)
        orders = json.load(open(f'ordenes_{mes}.json', encoding='utf-8'))
        # misma regla que compute_base_ventas.py: solo status == 'paid'. El cache
        # (fetch_orders.is_valid) deja pasar partially_refunded -- con eso se
        # escapo una orden paid -> partially_refunded durante 2 semanas (2026-09-23,
        # orden 2000018342622744).
        validos.update(o['id'] for o in orders if o['status'] == 'paid')

    cambios = {}
    for path in ('base_ventas.json', 'base_envios.json'):
        base = json.load(open(path, encoding='utf-8'))
        eliminadas = []
        for oid_str in list(base.keys()):
            fecha = base[oid_str]['fecha']
            if desde.isoformat() <= fecha <= hasta.isoformat() and int(oid_str) not in validos:
                eliminadas.append(oid_str)
                del base[oid_str]
        if eliminadas:
            json.dump(base, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
            cambios[path] = eliminadas

    if cambios:
        print('ATENCION -- ordenes que cambiaron de status (dejaron de ser "paid") y se sacaron:')
        for path, eliminadas in cambios.items():
            print(f'  {path}: {eliminadas}')
        print('Hay que correr build_base_ventas_sheet.py/build_base_envios_sheet.py y '
              'regenerar pnl_data.json/dashboard/Sheet.')
    else:
        print(f'Sin cambios de status en los ultimos {DIAS_ATRAS} dias ({desde.isoformat()}..{hasta.isoformat()}).')


if __name__ == '__main__':
    main()
