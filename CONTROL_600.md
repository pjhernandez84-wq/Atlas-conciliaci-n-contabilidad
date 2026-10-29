# Control de movimientos de la 600 en el haber

Control ejecutable independiente dentro de Atlas Contabilidad. No está integrado todavía en la API ni en un cruce automático con almacén. No modifica ni importa datos en la base de datos.

## Ejecutar

Desde la raíz del repositorio, con Python (sin dependencias adicionales):

```bash
python -m app.control_600 extracto.csv --empresa Jabardo --mes 2024-04
python -m unittest discover -s tests -v
```

CSV UTF-8 separado por coma o punto y coma. Cabeceras obligatorias:

```csv
id;empresa;fecha;cuenta;proveedor;asiento;concepto;debe;haber
1;Jabardo;2024-04-10;6000001;Proveedor A;10;Compra;100,00;0
2;Jabardo;2024-04-12;6000001;Proveedor A;12;Rectificativa;0;20,00
```

Las filas del ejemplo son ficticias. Fechas ISO YYYY-MM-DD; cuentas como texto sin puntos ni separadores. ID estable del apunte, único por empresa en el archivo. Importes vacíos equivalen a cero; formatos admitidos 1234.56 y 1.234,56. Valores ambiguos o malformados detienen el control sin emitir un resultado parcial.

## Resultado JSON

- Selecciona la empresa y el mes exactos y las cuentas que empiezan por 600. No incluye 601, 602, 606, 608 ni 609.
- Lista todo movimiento de haber distinto de cero, con referencia de origen, fecha, subcuenta, proveedor, asiento, concepto, debe, haber y neto.
- También avisa de importes negativos, debe y haber simultáneos y proveedores sin identificar. No elimina ni compensa apuntes duplicados: un ID repetido detiene el proceso para revisar el origen.
- Presenta debe, haber y neto (debe menos haber) por subcuenta y proveedor y totales del periodo. Mantiene importes decimales exactos.
- Marca las alertas como pendientes de revisión. No deduce por el concepto si un movimiento es una devolución, rectificación, regularización de cierre o error: debe contrastarse con el asiento completo y su documento.
- Una ejecución sin alertas de signo no certifica la conciliación ni el tratamiento contable correcto. Un periodo sin apuntes devuelve sin_datos.

Antes de usar el neto en el cruce con almacén, revisar los movimientos señalados, su periodo y su documento; identificar cierres/regularizaciones y asegurar la misma base de valoración e impuestos. No convertir el haber en compra positiva ni excluirlo silenciosamente.

## Abril de 2024

El PDF de doble conciliación solo contiene agregados. El control no se ha ejecutado sobre sus 78 apuntes: requiere el extracto original con debe y haber separados. El módulo no reconstruye esos apuntes desde los totales del PDF.
