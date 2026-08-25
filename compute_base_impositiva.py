"""
Arma la tabla "base_impositiva": una fila por percepcion/retencion individual
(Facturacion, marketplace TAXES, grupos ML y MP), para poder ver mes a mes
que se esta pagando por jurisdiccion/impuesto.

Las percepciones se facturan TODAS JUNTAS el dia que cierra cada periodo de
Facturacion (corre del 7 de un mes al 6 del siguiente, se factura el 7 del
mes que sigue) -- no hay una fecha por venta, la "Fecha" de cada fila es la
fecha de esa facturacion. Por eso esta tabla solo tiene sentido para
PERIODOS CERRADOS -- mientras un periodo sigue abierto, un scan completo del
mismo es inestable (ver mercadolibre-pnl-pipeline en memoria) y no hay
alternativa por-orden como con CORE (estas entradas no tienen sales_info).

Uso:
    python compute_base_impositiva.py <period_key> [<period_key> ...]
    python compute_base_impositiva.py 2026-05-01 2026-06-01 2026-07-01

Escribe base_impositiva.json (lista de registros; se reescribe entera cada
corrida, ya que los periodos cerrados no cambian).
"""
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()


def refresh_token():
    token_data = json.load(open('token.json'))
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


def get_token():
    token_data = json.load(open('token.json'))
    headers = {'Authorization': f'Bearer {token_data["access_token"]}'}
    r = requests.get('https://api.mercadolibre.com/users/me', headers=headers)
    if r.status_code == 401:
        return refresh_token()
    return token_data['access_token']


TOKEN = get_token()
HEADERS = {'Authorization': f'Bearer {TOKEN}'}


def fetch_billing_once(period_key, group):
    """Un intento de traer TODO el periodo, dedupeado por detail_id. Si no
    coincide contra el 'total' reportado, devuelve None para reintentar
    (paginas parciales intermitentes -- ver mercadolibre-pnl-pipeline)."""
    global TOKEN, HEADERS
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
            if r.status_code == 401:
                TOKEN = refresh_token()
                HEADERS = {'Authorization': f'Bearer {TOKEN}'}
                continue
            if r.status_code == 200:
                break
            time.sleep(5)
        else:
            return None, None
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
        return None, None
    return by_id, reported_total


def fetch_billing(period_key, group):
    for attempt in range(4):
        by_id, total = fetch_billing_once(period_key, group)
        if by_id is not None:
            return by_id
        print(f'  (billing {period_key}/{group}: conteo inconsistente, reintentando -- '
              f'normal si el periodo sigue abierto)')
    raise RuntimeError(f'No se pudo traer un conteo consistente de billing para {period_key}/{group} '
                        f'-- probablemente el periodo todavia esta abierto, no se puede usar para base_impositiva')


if __name__ == '__main__':
    period_keys = sys.argv[1:]
    if not period_keys:
        print('Uso: python compute_base_impositiva.py <period_key> [<period_key> ...]')
        print('  (solo periodos CERRADOS -- un periodo abierto va a fallar el chequeo de consistencia)')
        sys.exit(1)

    nuevos = []
    for pk in period_keys:
        for group in ['ML', 'MP']:
            print(f'Trayendo {pk}/{group}...')
            entries = fetch_billing(pk, group)
            tax_entries = [e for e in entries.values() if e['marketplace_info']['marketplace'] == 'TAXES']
            print(f'  {len(tax_entries)} percepciones/retenciones encontradas')
            for e in tax_entries:
                ci = e['charge_info']
                nuevos.append({
                    'fecha': ci['creation_date_time'][:10],
                    'grupo': group,
                    'categoria': ci['transaction_detail'].strip(),
                    'detalle': f"doc {e['document_info']['document_id']}" if e.get('document_info') else '',
                    'importe': ci['detail_amount'],
                    'period_key': pk,
                })

    # merge: se reemplazan solo los periodos pedidos en esta corrida, se
    # conservan intactos los que ya estaban guardados de corridas anteriores
    # (antes esto SOBREESCRIBIA todo el archivo -- si se pasaba un solo
    # period_key nuevo se perdian los periodos ya cargados).
    registros = []
    if os.path.exists('base_impositiva.json'):
        registros = json.load(open('base_impositiva.json', encoding='utf-8'))
    registros = [r for r in registros if r['period_key'] not in period_keys] + nuevos

    json.dump(registros, open('base_impositiva.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'Guardado base_impositiva.json ({len(registros)} registros)')
