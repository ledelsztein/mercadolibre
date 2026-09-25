"""
Nombres de categoria para los dashboards/Sheet (cat_names.json).

cat_names.json es un mapa cat_id -> nombre corto, curado a mano (ej. todas
las variantes de toalla agrupadas como "Toallones"). Antes, si aparecia una
venta de una categoria nueva que no estaba en el mapa, el dashboard mostraba
el ID crudo (ej. "MLA416552") sin que nadie se enterara (pasó 2026-09-25).

load_cat_names(cat_ids) completa los que falten con el nombre oficial de
MercadoLibre (GET publico /categories/{id}, solo lectura), los guarda en
cat_names.json para la proxima y avisa por consola -- si el nombre oficial no
sirve para agrupar (ej. otra variante de toalla), corregirlo a mano en el JSON.
"""
import json

import requests

CAT_FILE = 'cat_names.json'


def load_cat_names(cat_ids=()):
    names = json.load(open(CAT_FILE, encoding='utf-8'))
    faltantes = sorted({c for c in cat_ids if c and c not in names})
    for cat_id in faltantes:
        try:
            r = requests.get(f'https://api.mercadolibre.com/categories/{cat_id}', timeout=20)
            r.raise_for_status()
            names[cat_id] = r.json()['name']
            print(f'  Categoria nueva {cat_id} -> "{names[cat_id]}" (agregada a {CAT_FILE}; '
                  'renombrar a mano si hay que agruparla con otra)')
        except Exception as exc:
            print(f'  ADVERTENCIA: no se pudo resolver el nombre de la categoria {cat_id} ({exc}) -- queda el ID')
    if faltantes:
        with open(CAT_FILE, 'w', encoding='utf-8') as f:
            json.dump(names, f, ensure_ascii=False, indent=2)
    return names
