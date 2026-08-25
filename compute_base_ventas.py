"""
Arma la tabla "base_ventas": una fila por ORDEN (no por pack -- un pack con
2 items da 2 filas), con el desglose completo Precio/Importe/Cargos/
Impuestos/Costo/Resultado Neto, cada monto en dos versiones (con IVA y sin
IVA), mas el tipo de envio y -- solo para Flex -- el Resultado/Margen Neto
sin contar el ingreso Flex.

Decisiones ya validadas con Lucas (ver mercadolibre-pnl-pipeline en memoria):
- Cargos variables/fijos = charges_details del pago (meli_percentage_fee,
  flat_fee), SIEMPRE netos -- no se separa bruto/descuento porque esa
  info solo existe en Facturacion y no esta disponible para ventas
  recientes (se probo a fondo: no esta ni en /orders ni en /payments).
- Impuestos de la operacion = charges_details type=="tax" (percepcion/
  retencion, ej. IIBB), tambien del pago, sin version con/sin IVA (no
  esta gravado).
- Costo de mercaderia: la planilla de Lucas ya viene sin IVA. Version
  "sin IVA" = tal cual: version "con IVA" = costo_sin_iva * 1.21.
- Envio: cargo real = charges_details type=="shipping" (solo aparece
  cuando es un costo real, ej. Colecta). Ingreso Flex = solo si
  logistic_type=="self_service", desde /shipments/{id}/costs
  (receiver.cost -> senders[0].save -> gross_amount). Full normalmente
  lava a $0 en ambos lados.
- "Importe recibido" es la CASCADA (Importe - cargos + descuentos -
  cargo envio + ingreso envio - impuestos), no necesariamente igual al
  net_received_amount de la orden cuando hay Flex de por medio (el
  ingreso Flex se liquida aparte, no dentro del pago de esa orden).
- Todo se divide por 1.21 para la version "sin IVA" excepto Impuestos de
  la operacion y Costo de mercaderia (que ya nace sin IVA).

Uso:
    python compute_base_ventas.py <order_id> [<order_id> ...]

Escribe/actualiza base_ventas.json (dict order_id -> fila) y no pisa filas
de otras ordenes ya calculadas.
"""
import json
import os
import sys
import time
from datetime import date

import openpyxl
import requests
from dotenv import load_dotenv

load_dotenv()
IVA = 1.21

SHIP_TYPE_NAMES = {
    'self_service': 'Flex',
    'fulfillment': 'Full',
    'xd_drop_off': 'Colecta/Cross-docking',
    'sin_tipo': 'Sin tipo',
}


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


def get(url, params=None):
    global TOKEN, HEADERS
    for _ in range(5):
        r = requests.get(url, headers=HEADERS, params=params)
        if r.status_code == 429:
            time.sleep(5)
            continue
        if r.status_code == 401:
            TOKEN = refresh_token()
            HEADERS = {'Authorization': f'Bearer {TOKEN}'}
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f'too many retries: {url}')


def get_mp(url, params=None):
    return get(url, params)


# ---------- costos (sin IVA) ----------
# Vive en el repo (data/Costos.xlsx), no en Descargas -- asi el pipeline es
# portable entre maquinas (2026-08-25, pedido de Lucas). Antes buscaba el
# archivo mas reciente en ~/Downloads/Costos*.xlsx; si esto vuelve a fallar
# por una edicion manual guardada en Descargas, mover ese archivo a
# data/Costos.xlsx a mano.
COSTS_FILE = 'data/Costos.xlsx'
wb = openpyxl.load_workbook(COSTS_FILE, data_only=True)
ws = wb.active
costs_by_item = {}
for row in ws.iter_rows(min_row=2, values_only=True):
    if row[0] is None:
        continue
    sku, item_id, producto, costo, fecha = row
    d = fecha.date() if hasattr(fecha, 'date') else fecha
    costs_by_item.setdefault(item_id, []).append((d, costo, producto))
for item_id in costs_by_item:
    costs_by_item[item_id].sort(key=lambda x: x[0])


def costo_vigente_sin_iva(item_id, fecha_venta):
    entries = costs_by_item.get(item_id)
    if not entries:
        return None
    candidato = None
    for d, costo, _ in entries:
        if d <= fecha_venta:
            candidato = (d, costo)
        else:
            if candidato is None:
                return costo
            break
    return candidato[1] if candidato else entries[0][1]


def fetch_order_base(order_id):
    """Datos que son 100% propios de la orden (no dependen de si comparte
    shipment con otra orden del mismo pack). Devuelve None si la orden no
    esta 'paid' (ej. partially_refunded) -- base_ventas solo contempla
    ordenes pagas y completas, sin devoluciones parciales de por medio."""
    o = get(f'https://api.mercadolibre.com/orders/{order_id}')
    if o['status'] != 'paid':
        print(f'  orden {order_id}: status={o["status"]!r}, no es "paid" -- se excluye')
        return None
    if len(o.get('order_items', [])) != 1:
        print(f'ADVERTENCIA: orden {order_id} tiene != 1 item distinto, revisar a mano.')
    item = o['order_items'][0]['item']
    qty = o['order_items'][0]['quantity']
    unit_price = o['order_items'][0]['unit_price']
    fecha_venta = date.fromisoformat(o['date_created'][:10])
    importe = o['total_amount']

    # una orden puede tener mas de un payment (reintento rechazado + uno
    # aprobado, o pago partido en dos medios de pago distintos, ambos
    # aprobados) -- los cargos hay que sumarlos de TODOS los aprobados, nunca
    # asumir que estan en payments[0] (confirmado con casos reales de ambos
    # tipos, ver mercadolibre-base-ventas)
    cargo_var = cargo_fij = envio_cargo_propio = impuestos = 0.0
    for pago in o['payments']:
        if pago.get('status') != 'approved':
            continue
        p = get_mp(f'https://api.mercadopago.com/v1/payments/{pago["id"]}')
        for c in p.get('charges_details', []):
            amt = c['amounts']['original']
            if c.get('type') == 'fee' and c.get('name') == 'meli_percentage_fee':
                cargo_var += amt
            elif c.get('type') == 'fee' and c.get('name') == 'flat_fee':
                cargo_fij += amt
            elif c.get('type') == 'fee':
                cargo_var += amt  # fee de nombre no reconocido -- lo sumamos a variable, no se pierde
            elif c.get('type') == 'shipping':
                envio_cargo_propio += amt
            elif c.get('type') == 'tax':
                impuestos += amt

    costo_s = (costo_vigente_sin_iva(item['id'], fecha_venta) or 0) * qty

    return {
        'order_id': o['id'], 'pack_id': o.get('pack_id'), 'fecha': o['date_created'][:10],
        'item_id': item['id'], 'sku': item.get('seller_sku') or '', 'title': item['title'], 'qty': qty,
        'cat_id': item['category_id'],
        'unit_price': unit_price, 'importe': importe, 'cargo_var': cargo_var, 'cargo_fij': cargo_fij,
        'impuestos': impuestos, 'envio_cargo_propio': envio_cargo_propio, 'costo_s': costo_s,
        'shipment_id': o.get('shipping', {}).get('id'),
    }


def compute_row(base, envio_cargo, envio_ingreso, envio_pasante, logistic_type):
    """base = dict de fetch_order_base(); envio_cargo/envio_ingreso/envio_pasante
    ya prorrateados por importe si el shipment es compartido (ver main).
    envio_pasante es la porcion de envio_cargo/envio_ingreso que es un pasante
    financiado por el comprador (se cancela neto a $0, ver el comentario en
    __main__) -- se guarda aparte para poder mostrarla separada del ingreso
    Flex real en el P&L/dashboard."""
    importe = base['importe']
    cargo_var = base['cargo_var']
    cargo_fij = base['cargo_fij']
    impuestos = base['impuestos']
    unit_price = base['unit_price']
    costo_s = base['costo_s']
    costo_c = costo_s * IVA

    importe_recibido_c = importe - cargo_var - cargo_fij - envio_cargo + envio_ingreso - impuestos
    resultado_neto_c = importe_recibido_c - costo_c
    margen_c = resultado_neto_c / importe if importe else 0

    unit_price_s = unit_price / IVA
    importe_s = importe / IVA
    cargo_var_s = cargo_var / IVA
    cargo_fij_s = cargo_fij / IVA
    envio_cargo_s = envio_cargo / IVA
    envio_ingreso_s = envio_ingreso / IVA
    importe_recibido_s = importe_s - cargo_var_s - cargo_fij_s - envio_cargo_s + envio_ingreso_s - impuestos
    resultado_neto_s = importe_recibido_s - costo_s
    margen_s = resultado_neto_s / importe_s if importe_s else 0

    row = {
        'order_id': base['order_id'], 'pack_id': base['pack_id'], 'fecha': base['fecha'],
        'item_id': base['item_id'], 'sku': base['sku'], 'title': base['title'], 'cat_id': base['cat_id'],
        'qty': base['qty'], 'tipo_envio': SHIP_TYPE_NAMES.get(logistic_type, logistic_type),
        'precio_c': round(unit_price, 2), 'importe_c': round(importe, 2),
        'cargo_var_c': round(-cargo_var, 2), 'cargo_fij_c': round(-cargo_fij, 2),
        'envio_cargo_c': round(-envio_cargo, 2), 'envio_ingreso_c': round(envio_ingreso, 2),
        'envio_pasante_c': round(envio_pasante, 2),
        'impuestos': round(-impuestos, 2),
        'importe_recibido_c': round(importe_recibido_c, 2), 'costo_c': round(-costo_c, 2),
        'resultado_neto_c': round(resultado_neto_c, 2), 'margen_c': margen_c,
        'precio_s': round(unit_price_s, 2), 'importe_s': round(importe_s, 2),
        'cargo_var_s': round(-cargo_var_s, 2), 'cargo_fij_s': round(-cargo_fij_s, 2),
        'envio_cargo_s': round(-envio_cargo_s, 2), 'envio_ingreso_s': round(envio_ingreso_s, 2),
        'envio_pasante_s': round(envio_pasante / IVA, 2),
        'importe_recibido_s': round(importe_recibido_s, 2), 'costo_s': round(-costo_s, 2),
        'resultado_neto_s': round(resultado_neto_s, 2), 'margen_s': margen_s,
    }
    if logistic_type == 'self_service':
        rn_sinflex_c = resultado_neto_c - envio_ingreso
        rn_sinflex_s = resultado_neto_s - envio_ingreso_s
        row['resultado_neto_sinflex_c'] = round(rn_sinflex_c, 2)
        row['margen_sinflex_c'] = rn_sinflex_c / importe if importe else 0
        row['resultado_neto_sinflex_s'] = round(rn_sinflex_s, 2)
        row['margen_sinflex_s'] = rn_sinflex_s / importe_s if importe_s else 0
    else:
        row['resultado_neto_sinflex_c'] = None
        row['margen_sinflex_c'] = None
        row['resultado_neto_sinflex_s'] = None
        row['margen_sinflex_s'] = None
    return row


if __name__ == '__main__':
    from collections import defaultdict

    order_ids = [int(x) for x in sys.argv[1:]]
    if not order_ids:
        print('Uso: python compute_base_ventas.py <order_id> [<order_id> ...]')
        sys.exit(1)

    print('Trayendo datos de cada orden...')
    order_base = {}
    excluidas = []
    for oid in order_ids:
        b = fetch_order_base(oid)
        if b is not None:
            order_base[oid] = b
        else:
            excluidas.append(oid)

    # agrupar por shipment_id -- si dos ordenes de este lote comparten envio,
    # el cargo/ingreso real del shipment se prorratea entre ellas por su
    # peso en el importe total del shipment (pedido explicito de Lucas).
    shipment_orders = defaultdict(list)
    for oid, b in order_base.items():
        if b['shipment_id']:
            shipment_orders[b['shipment_id']].append(oid)

    envio_cargo_final = {}
    envio_ingreso_final = {}
    envio_pasante_final = {}
    tipo_final = {}
    for sid, oids in shipment_orders.items():
        s = get(f'https://api.mercadolibre.com/shipments/{sid}')
        ltype = s.get('logistic_type') or 'sin_tipo'
        total_egreso = sum(order_base[o]['envio_cargo_propio'] for o in oids)
        total_ingreso = 0.0
        es_pasante = False
        if ltype == 'self_service':
            costs = get(f'https://api.mercadolibre.com/shipments/{sid}/costs')
            receiver_cost = costs.get('receiver', {}).get('cost', 0) or 0
            senders_save = costs.get('senders', [{}])[0].get('save', 0) or 0
            gross = costs.get('gross_amount', 0) or 0
            total_ingreso = receiver_cost or senders_save or gross
        elif total_egreso > 0:
            # Full/Colecta con un cargo de envio real en charges_details --
            # puede ser un cargo genuino (senders[0].cost > 0, Lucas lo paga)
            # o un pasante financiado por el comprador (senders[0].cost == 0,
            # receiver.cost > 0) que en la pantalla de Lucas se ve como dos
            # lineas que se cancelan ("Pago de Mercado Envios" + "Cargo por
            # Envios de ML", ambas "a cargo del comprador") -- verificado
            # contra net_received_amount en casos reales. Si es pasante, se
            # carga el mismo monto como ingreso para que se cancele, en vez
            # de contarlo como costo real. Se guarda aparte en
            # envio_pasante_final para poder separarlo en el P&L/dashboard
            # (pedido de Lucas 2026-08-18, le generaba ruido ver "ingreso
            # Flex" mezclado con este lavado contable de Full/Colecta).
            costs = get(f'https://api.mercadolibre.com/shipments/{sid}/costs')
            senders_cost = costs.get('senders', [{}])[0].get('cost', 0) or 0
            if senders_cost == 0:
                total_ingreso = total_egreso
                es_pasante = True
        total_importe = sum(order_base[o]['importe'] for o in oids) or 1
        for o in oids:
            share = order_base[o]['importe'] / total_importe
            envio_cargo_final[o] = total_egreso * share
            envio_ingreso_final[o] = total_ingreso * share
            envio_pasante_final[o] = (total_egreso * share) if es_pasante else 0.0
            tipo_final[o] = ltype
        if len(oids) > 1:
            print(f'  shipment {sid} compartido por {len(oids)} ordenes -> prorrateado por importe')

    for oid, b in order_base.items():
        if not b['shipment_id']:
            envio_cargo_final[oid] = 0.0
            envio_ingreso_final[oid] = 0.0
            envio_pasante_final[oid] = 0.0
            tipo_final[oid] = 'sin_tipo'

    base = {}
    if os.path.exists('base_ventas.json'):
        base = json.load(open('base_ventas.json', encoding='utf-8'))

    # una orden que estaba guardada (paid en su momento) puede pasar a
    # cancelled/refunded despues -- si eso paso, hay que sacarla del archivo,
    # no dejarla con los datos viejos de cuando todavia era paid.
    for oid in excluidas:
        if str(oid) in base:
            print(f'  orden {oid} ya no es "paid" -- se elimina de base_ventas.json (tenia datos guardados de cuando si lo era)')
            del base[str(oid)]

    for oid in order_base:
        row = compute_row(order_base[oid], envio_cargo_final[oid], envio_ingreso_final[oid], envio_pasante_final[oid], tipo_final[oid])
        base[str(oid)] = row

    json.dump(base, open('base_ventas.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'Guardado base_ventas.json ({len(base)} ordenes en total)')
