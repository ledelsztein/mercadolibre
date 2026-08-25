"""
Calcula los campos de ML del P&L (ventas, cargo por venta, descuentos, egreso
de envio real, ingreso de envio Flex, publicidad) para un conjunto de ordenes
ya guardado en ordenes_<archivo>.json, restringido a un rango de fechas.

No calcula percepciones/retenciones (eso depende del cierre del periodo de
facturacion de MercadoLibre, no de un rango de dias arbitrario) ni los
campos informativos (logistica flex, otros cargos, autonomos, IIBB) -- esos
siguen viniendo de Lucas.

Uso:
    python compute_pnl_ml.py <archivo_ordenes> <fecha_desde> <fecha_hasta>
    python compute_pnl_ml.py julio 2026-07-01 2026-07-20
    python compute_pnl_ml.py julio 2026-07-21 2026-07-21   # un solo dia (hoy)

Imprime los valores para pegar a mano en pnl_data.json (ver
mercadolibre-pnl-pipeline en memoria para el resto del campo a completar).
"""
import json
import os
import sys
import time
from collections import defaultdict

import requests
from dotenv import load_dotenv

load_dotenv()
SELLER_ID = 42206571


def get_token():
    token_data = json.load(open('token.json'))
    headers = {'Authorization': f'Bearer {token_data["access_token"]}'}
    r = requests.get('https://api.mercadolibre.com/users/me', headers=headers)
    if r.status_code == 401:
        r = requests.post('https://api.mercadolibre.com/oauth/token', data={
            'grant_type': 'refresh_token',
            'client_id': os.environ['ML_CLIENT_ID'],
            'client_secret': os.environ['ML_CLIENT_SECRET'],
            'refresh_token': token_data['refresh_token'],
        })
        r.raise_for_status()
        token_data = r.json()
        json.dump(token_data, open('token.json', 'w'), indent=2)
    return token_data['access_token']


TOKEN = get_token()
HEADERS = {'Authorization': f'Bearer {TOKEN}'}


def get_payment(payment_id):
    for _ in range(5):
        r = requests.get(f'https://api.mercadopago.com/v1/payments/{payment_id}', headers=HEADERS)
        if r.status_code == 429:
            time.sleep(5)
            continue
        return r.json()
    raise RuntimeError('too many retries')


def get_shipment(sid):
    for _ in range(5):
        r = requests.get(f'https://api.mercadolibre.com/shipments/{sid}', headers=HEADERS)
        if r.status_code == 429:
            time.sleep(5)
            continue
        return r.json()
    raise RuntimeError('too many retries')


def get_shipment_costs(sid):
    for _ in range(5):
        r = requests.get(f'https://api.mercadolibre.com/shipments/{sid}/costs', headers=HEADERS)
        if r.status_code == 429:
            time.sleep(5)
            continue
        return r.json()
    raise RuntimeError('too many retries')


def fetch_billing_once(period_key, group):
    """Un intento de traer TODO el periodo, dedupeado por detail_id. Se
    valida al final contra el 'total' que informa la propia API -- si no
    coincide, se devuelve None para que el caller reintente desde cero
    (la API confirmadamente devuelve paginas parciales/inconsistentes de
    forma intermitente, no solo con 429 -- confirmado 2026-07-22 corriendo
    la misma consulta 3 veces seguidas y obteniendo 3 totales distintos)."""
    by_id = {}
    last_id = 0
    reported_total = None
    while True:
        params = {'document_type': 'BILL', 'limit': 150}
        if last_id:
            params['from_id'] = last_id
        r = None
        for _ in range(6):
            r = requests.get(f'https://api.mercadolibre.com/billing/integration/periods/key/{period_key}/group/{group}/details',
                headers=HEADERS, params=params)
            if r.status_code == 200:
                break
            time.sleep(5)
        else:
            return None
        d = r.json()
        if reported_total is None:
            reported_total = d.get('total', 0)
        page = d.get('results', [])
        for e in page:
            did = e.get('charge_info', {}).get('detail_id')
            if did is not None:
                by_id[did] = e
        nl = d.get('last_id', 0)
        if not nl or nl == last_id or len(page) < 150:
            break
        last_id = nl
        time.sleep(0.3)
    if reported_total and len(by_id) < reported_total:
        return None
    return list(by_id.values())


def fetch_billing(period_key, group):
    """Solo para consultas SIN order_ids (ej. publicidad/MCLICS, que no esta
    atada a una orden puntual y necesita el periodo completo si o si).
    Reintenta el fetch completo hasta 4 veces si la cuenta no cierra contra
    el 'total' reportado (la API confirmadamente da paginas inconsistentes
    de forma intermitente mientras el periodo sigue abierto)."""
    results = None
    for attempt in range(4):
        results = fetch_billing_once(period_key, group)
        if results is not None:
            break
        print(f'  (billing {period_key}/{group}: conteo inconsistente, reintentando fetch completo...)')
    if results is None:
        raise RuntimeError(f'No se pudo traer un conteo consistente de billing para {period_key}/{group}')
    return results


def fetch_billing_for_order(period_key, order_id):
    """Cargos CORE de UNA sola orden. El parametro order_ids de esta API
    esta roto para mas de un id (con 2+ ids siempre da total:0 aunque los
    datos existan). Incluso con 1 solo id, ocasionalmente devuelve 0
    resultados de forma transitoria para una orden que si tiene datos (no
    solo con status != 200) -- por eso reintentamos tambien cuando la
    respuesta viene vacia, no solo cuando falla el request."""
    last_empty = None
    for attempt in range(6):
        r = requests.get(f'https://api.mercadolibre.com/billing/integration/periods/key/{period_key}/group/ML/details',
            headers=HEADERS, params={'document_type': 'BILL', 'order_ids': order_id})
        if r.status_code != 200:
            time.sleep(5)
            continue
        results = r.json().get('results', [])
        if results:
            return results
        last_empty = results
        time.sleep(1.5)
    return last_empty or []


def billing_period_for_date(d):
    """Los periodos de facturacion de ML corren del dia 7 de un mes al 6 del
    siguiente. Devuelve el 'key' (formato YYYY-MM-01, el mes SIGUIENTE al de
    cierre) que contiene esa fecha."""
    from datetime import date
    dd = date.fromisoformat(d)
    if dd.day >= 7:
        y, m = dd.year, dd.month + 1
    else:
        y, m = dd.year, dd.month
    if m > 12:
        y, m = y + 1, m - 12
    return f'{y}-{m:02d}-01'


def compute(orders, start_local, end_local, neto=False):
    ventas = sum(o['total_amount'] for o in orders)

    comision = 0.0
    egreso_envio_real = 0.0
    for i, o in enumerate(orders):
        pid = o['payments'][0]['id']
        p = get_payment(pid)
        for c in p.get('charges_details', []):
            if c.get('type') == 'fee':
                comision += c['amounts']['original']
            elif c.get('type') == 'shipping':
                egreso_envio_real += c['amounts']['original']
        if (i + 1) % 20 == 0:
            time.sleep(1)

    shipment_ids = {o['shipping']['id'] for o in orders if o.get('shipping', {}).get('id')}
    envios_ingreso = 0.0
    logistic_dist = defaultdict(int)
    for i, sid in enumerate(shipment_ids):
        s = get_shipment(sid)
        ltype = s.get('logistic_type')
        logistic_dist[ltype] += 1
        if ltype == 'self_service':
            c = get_shipment_costs(sid)
            receiver_cost = c.get('receiver', {}).get('cost', 0) or 0
            senders_save = c.get('senders', [{}])[0].get('save', 0) or 0
            gross = c.get('gross_amount', 0) or 0
            envios_ingreso += receiver_cost or senders_save or gross
        if (i + 1) % 20 == 0:
            time.sleep(1)

    # billing CORE (cargo por venta bruto + descuentos), orden por orden.
    # Si el periodo sigue ABIERTO este desglose no es confiable (crece entre
    # corridas incluso con reintentos, porque ML todavia no genero el
    # registro CORE de ordenes recientes) -- con neto=True nos salteamos
    # Billing y usamos directamente el cargo NETO ya cobrado (variable
    # `comision`, de MercadoPago), dejando descuentos en 0 porque ya esta
    # neteado ahi adentro.
    periods_needed = sorted({billing_period_for_date(o['date_created'][:10]) for o in orders})
    if neto:
        print('  modo --neto: cargo_venta = comision neta de MercadoPago, sin desglose bruto/descuento')
        cargo_venta_bruto = comision
        descuentos = 0.0
    else:
        cargo_venta_bruto = 0.0
        descuentos = 0.0
        for i, o in enumerate(orders):
            pk = billing_period_for_date(o['date_created'][:10])
            entries = fetch_billing_for_order(pk, str(o['id']))
            for e in entries:
                if e['marketplace_info']['marketplace'] != 'CORE':
                    continue
                disc = e['discount_info']['discount_amount'] or 0.0
                gross = e['discount_info']['charge_amount_without_discount']
                if gross is None:
                    gross = e['charge_info']['detail_amount'] + disc
                cargo_venta_bruto += gross
                descuentos += disc
            if (i + 1) % 20 == 0:
                time.sleep(1)
                print(f'  facturacion: {i + 1}/{len(orders)} ordenes consultadas')

    # publicidad (MCLICS), agrupado por dia, sumado sobre el rango pedido
    ads_entries = []
    for pk in periods_needed:
        ads_entries += fetch_billing(pk, 'ML')  # sin order_ids: trae TODO el periodo
    by_day = defaultdict(float)
    for e in ads_entries:
        if e['marketplace_info']['marketplace'] != 'MCLICS':
            continue
        day = e['charge_info']['creation_date_time'][:10]
        amt = e['charge_info']['detail_amount']
        if e['charge_info']['transaction_detail'].startswith('Anulaci'):
            amt = -amt
        by_day[day] += amt
    publicidad = sum(v for d, v in by_day.items() if start_local <= d <= end_local)

    return {
        'ventas': round(ventas, 2),
        'cargo_venta': round(cargo_venta_bruto, 2),
        'descuentos': round(descuentos, 2),
        'egreso_envio': round(egreso_envio_real, 2),
        'envios_ingreso': round(envios_ingreso, 2),
        'publicidad': round(publicidad, 2),
        'logistic_dist': dict(logistic_dist),
    }


if __name__ == '__main__':
    archivo, start_local, end_local = sys.argv[1], sys.argv[2], sys.argv[3]
    neto = '--neto' in sys.argv[4:]
    all_orders = json.load(open(f'ordenes_{archivo}.json', encoding='utf-8'))
    orders = [o for o in all_orders if start_local <= o['date_created'][:10] <= end_local]
    print(f'{len(orders)} ordenes en {start_local}..{end_local}')
    result = compute(orders, start_local, end_local, neto=neto)
    print(json.dumps(result, indent=2, ensure_ascii=False))
