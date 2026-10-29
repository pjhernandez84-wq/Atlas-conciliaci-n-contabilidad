import unittest
from app.control_600 import comprobar, importe


def row(id='1', **kwargs):
    return dict(id=id, empresa='Jabardo', fecha='2024-04-10', cuenta='6000001',
                proveedor='Proveedor A', asiento='10', concepto='Compra', debe='100', haber='0', **kwargs)


class ControlTest(unittest.TestCase):
    def test_credit_reduces_net_and_keeps_original(self):
        a, b = row(), row('2')
        b.update(debe='0', haber='20', concepto='Rectificativa')
        result = comprobar([a, b], 'Jabardo', '2024-04')
        self.assertEqual(result['totales'], {'debe': '100', 'haber': '20', 'neto': '80'})
        self.assertEqual(result['incidencias'][0]['estado'], 'pendiente_revision')
        self.assertEqual(b['haber'], '20')

    def test_company_month_and_account_filters(self):
        rows = [row(str(i)) for i in range(4)]
        rows[1]['empresa'] = 'Otra'
        rows[2]['fecha'] = '2024-05-01'
        rows[3]['cuenta'] = '4000001'
        self.assertEqual(comprobar(rows, 'Jabardo', '2024-04')['apuntes_600'], 1)

    def test_negative_debit_and_both_sides_flagged(self):
        a = row()
        a.update(debe='-10', haber='5')
        result = comprobar([a], 'Jabardo', '2024-04')
        self.assertEqual(len(result['incidencias'][0]['motivos']), 3)
        self.assertEqual(result['totales']['neto'], '-15')

    def test_duplicates_and_invalid_amounts_stop_processing(self):
        with self.assertRaises(ValueError):
            comprobar([row(), row()], 'Jabardo', '2024-04')
        for invalid in ['NaN', '1,234.56', '1.2345', 'texto']:
            with self.assertRaises(ValueError):
                importe(invalid)
        self.assertEqual(importe('1.234,56'), importe('1234.56'))

    def test_no_data_is_not_successful_reconciliation(self):
        self.assertEqual(comprobar([], 'Jabardo', '2024-04')['estado'], 'sin_datos')


if __name__ == '__main__':
    unittest.main()
