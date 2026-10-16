"""Strict CSV preview: every source record is retained, never auto-approved."""
import csv
import io
import re
import unicodedata
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation


def amount(value):
    value = value.strip()
    if not re.fullmatch(r'-?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?', value):
        raise ValueError('Importe inválido: use formato español, por ejemplo -1.234,56')
    try:
        return Decimal(value.replace('.', '').replace(',', '.'))
    except InvalidOperation as exc:
        raise ValueError('Importe inválido') from exc


def parse_csv(text, source):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')), delimiter=';', strict=True)
    required = ['fecha', 'concepto', 'importe']
    if reader.fieldnames != required:
        raise ValueError('Cabecera requerida: fecha;concepto;importe')
    rows = []
    for number, row in enumerate(reader, 2):
        if len(rows) >= 5000:
            raise ValueError('Máximo 5.000 movimientos por archivo')
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f'{source}, registro {number}: columnas incompletas o sobrantes')
        try:
            date = datetime.strptime(row['fecha'].strip(), '%d/%m/%Y').date().isoformat()
            value = amount(row['importe'])
        except ValueError as exc:
            raise ValueError(f'{source}, registro {number}: {exc}') from exc
        if not row['concepto'].strip():
            raise ValueError(f'{source}, registro {number}: falta concepto')
        rows.append({'id': f'{source}-{number}', 'registro': number, 'fecha': date,
                     'concepto': row['concepto'], 'importe': str(value), 'original': row,
                     'estado': 'pendiente de revisión', 'candidatos': []})
    if not rows:
        raise ValueError(f'{source}: archivo sin movimientos')
    counts = Counter((r['fecha'], r['concepto'].strip().casefold(), r['importe']) for r in rows)
    for row in rows:
        row['posible_duplicado'] = counts[(row['fecha'], row['concepto'].strip().casefold(), row['importe'])] > 1
    return rows


def preview(bank_text, ledger_text, balances):
    bank, ledger = parse_csv(bank_text, 'banco'), parse_csv(ledger_text, 'mayor')
    # Same-month signed-amount candidates are suggestions, never approvals.
    # Keep every edge, including weak evidence and competing claims in both directions.
    stopwords = set('transferencia ingreso pago recibo factura fra favor concepto entrega documentos para su compensacion banco dia de del la el en por a y sl sa slu asiento apunte'.split())
    def tokens(text):
        text = re.sub(r'\[Asiento/apunte:.*?\]', '', text, flags=re.I)
        text = ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))
        return {t for t in re.findall(r'[a-z0-9]+', text) if len(t) >= 4 and t not in stopwords}
    for source, other in [(bank, ledger), (ledger, bank)]:
        index = {}
        for row in other:
            index.setdefault((row['fecha'][:7], Decimal(row['importe'])), []).append(row)
        for row in source:
            details = []
            for candidate in index.get((row['fecha'][:7], Decimal(row['importe'])), []):
                shared = sorted(tokens(row['concepto']) & tokens(candidate['concepto']))
                same_date = row['fecha'] == candidate['fecha']
                exact = row['concepto'].strip().casefold() == candidate['concepto'].strip().casefold()
                evidence = 'concepto exacto' if exact else ('términos comunes: ' + ', '.join(shared) if shared else 'sin evidencia de concepto; solo importe y signo')
                details.append({'id': candidate['id'], 'fecha': candidate['fecha'],
                                'concepto': candidate['concepto'], 'importe': candidate['importe'],
                                'motivo': ('misma fecha; ' if same_date else 'fecha distinta; ') + evidence,
                                'evidencia_concepto': bool(exact or shared)})
            row['detalle_candidatos'] = details
            row['candidatos'] = [d['id'] for d in details]
    # Nearby unique amount anchors are context, not proof of correspondence.
    for source, other in [(bank, ledger), (ledger, bank)]:
        positions = {r['id']: i for i, r in enumerate(other)}
        source_counts = Counter((r['fecha'][:7], Decimal(r['importe'])) for r in source)
        other_counts = Counter((r['fecha'][:7], Decimal(r['importe'])) for r in other)
        for i, row in enumerate(source):
            for detail in row['detalle_candidatos']:
                j = positions[detail['id']]
                anchors = []
                for k in range(max(0, i - 3), min(len(source), i + 4)):
                    neighbor = source[k]
                    key = (neighbor['fecha'][:7], Decimal(neighbor['importe']))
                    if k == i or source_counts[key] != 1 or other_counts[key] != 1:
                        continue
                    matches = neighbor['candidatos']
                    if len(matches) == 1 and 0 < abs(positions[matches[0]] - j) <= 3:
                        anchors.append({'origen': neighbor['id'], 'destino': matches[0],
                                        'sentido': 'mismo' if (k-i)*(positions[matches[0]]-j) > 0 else 'inverso'})
                detail['contexto_orden'] = anchors
                if anchors:
                    detail['motivo'] += '; orden cercano: ' + ', '.join(
                        f"{x['origen']} ↔ {x['destino']} ({x['sentido']})" for x in anchors)
                else:
                    detail['motivo'] += '; sin apoyo de orden cercano'
    by_id = {r['id']: r for r in bank + ledger}
    for row in bank + ledger:
        ids = row['candidatos']
        conflict = (row['posible_duplicado'] or len(ids) > 1 or
                    any(by_id[i]['posible_duplicado'] or len(by_id[i]['candidatos']) > 1 for i in ids))
        row['estado'] = ('ambigua' if ids and conflict else
                         'propuesta pendiente de revisión' if ids and row['detalle_candidatos'][0]['evidencia_concepto'] else
                         'solo importe: revisar concepto' if ids else 'sin candidato individual')
    # Pair sums are arithmetic leads only; never consume or approve any row.
    for source, other in [(bank, ledger), (ledger, bank)]:
        pools = {}
        for candidate in other:
            value = Decimal(candidate['importe'])
            if value:
                pools.setdefault((candidate['fecha'][:7], value > 0), []).append(candidate)
        for row in source:
            target = Decimal(row['importe'])
            pool = pools.get((row['fecha'][:7], target > 0), []) if target else []
            row['grupos_candidatos'] = []
            row['aviso_grupos'] = 'Solo se buscan grupos de dos apuntes del mismo signo y mes; no acredita correspondencia documental.'
            if len(pool) > 500:
                row['aviso_grupos'] += ' Búsqueda omitida: más de 500 apuntes candidatos.'
                continue
            seen = {}
            count = 0
            for candidate in pool:
                value = Decimal(candidate['importe'])
                for previous in seen.get(target - value, []):
                    count += 1
                    if count <= 20:
                        row['grupos_candidatos'].append({
                            'miembros': [{k: item[k] for k in ('id', 'fecha', 'concepto', 'importe')}
                                         for item in (previous, candidate)],
                            'suma': str(target),
                            'estado': 'suma coincidente: pendiente de justificar',
                        })
                seen.setdefault(value, []).append(candidate)
            row['total_grupos_dos'] = count
            if count > 20:
                row['aviso_grupos'] += f' Se muestran 20 de {count} combinaciones; búsqueda no resuelta.'
    controls = {}
    for name, rows in [('banco', bank), ('mayor', ledger)]:
        opening, closing = amount(balances[name + '_inicial']), amount(balances[name + '_final'])
        total = sum((Decimal(r['importe']) for r in rows), Decimal(0))
        controls[name] = {'movimientos': len(rows), 'inicial': str(opening), 'final': str(closing),
                          'suma': str(total), 'descuadre': str(opening + total - closing)}
    controls['diferencia_inicial'] = str(amount(balances['banco_inicial']) - amount(balances['mayor_inicial']))
    controls['diferencia_final'] = str(amount(balances['banco_final']) - amount(balances['mayor_final']))
    return {'banco': bank, 'mayor': ledger, 'controles': controls, 'definitiva': False,
            'aviso': 'Revisión pendiente de todos los movimientos, duplicados y cobros agrupados. Ninguna propuesta queda conciliada automáticamente.'}
