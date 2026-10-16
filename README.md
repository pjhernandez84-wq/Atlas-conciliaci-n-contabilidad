# Atlas Contabilidad — primera base

API de autenticación local y separación por empresas. **Prototipo, no listo para producción.** No almacenes datos contables reales todavía.

## Instalación

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Configura variables de entorno `ATLAS_BOOTSTRAP_EMAIL` y `ATLAS_BOOTSTRAP_PASSWORD` (16 caracteres o más) antes del primer inicio. Para pruebas locales HTTP configura `ATLAS_COOKIE_SECURE=false`; en producción debe ser `true` y usarse HTTPS. No subas tus contraseñas a GitHub. Luego:

```bash
uvicorn app.main:app --reload
```

Documentación interactiva local: `http://127.0.0.1:8000/docs`.

## API

- `POST /auth/login` con JSON `{"email":"...", "password":"..."}`. Devuelve una cookie HttpOnly de sesión.
- `GET /auth/me` valida la sesión.
- `POST /auth/logout` revoca la sesión.
- `GET /companies` muestra únicamente empresas asignadas.
- `GET /health` comprueba el servicio.

## Diseño y seguridad

Contraseñas con Argon2; tokens de sesión aleatorios; en SQLite solo se conserva SHA-256 del token. Sesiones de 8 horas; cookies HttpOnly, SameSite=Strict y Secure por defecto. Tablas `users`, `companies`, `memberships` y `sessions`. Cada empresa y usuario debe verificarse en **cada endpoint nuevo**. Las empresas no se precargan. La pantalla permite crear empresas de prueba y asigna al creador como administrador.

### Bloqueadores para producción

- Control CSRF de operaciones con cookie y política CORS estricta.
- Límites de intentos de acceso y auditoría.
- Administración segura de usuarios/roles y recuperación de cuentas.
- Migraciones, copias de seguridad cifradas y despliegue HTTPS.
- Pruebas de seguridad y aislamiento multiempresa.

## Conciliación contable (siguiente etapa)

Comparación banco vs mayor línea a línea: fecha, concepto, importe, signo, duplicados, cobros agrupados y saldos de apertura/cierre. Nunca marcar una conciliación como correcta basándose exclusivamente en coincidencias automáticas.

## Pantalla de contraste CSV

En la rama `feature/conciliacion-csv`, abre `http://127.0.0.1:8000/` tras iniciar Uvicorn.
Inicia sesión con el usuario de arranque y crea una empresa de prueba: su creador
recibe el rol admin; otros usuarios no reciben acceso automáticamente.
No es una administración completa de usuarios o empresas.

Para Windows PowerShell, antes de iniciar por primera vez:

```powershell
$env:ATLAS_BOOTSTRAP_EMAIL = Read-Host 'Correo de acceso'
$secret = Read-Host 'Contraseña de prueba (mínimo 16 caracteres)' -AsSecureString
$env:ATLAS_BOOTSTRAP_PASSWORD = [System.Net.NetworkCredential]::new('', $secret).Password
$env:ATLAS_COOKIE_SECURE = 'false'
uvicorn app.main:app --reload --host 127.0.0.1
```

`.env.example` es una referencia: la aplicación no carga archivos `.env` automáticamente.

Carga dos CSV UTF-8 (máximo 1 MB y 5.000 movimientos por archivo), de la misma
cuenta y periodo, con cabecera exacta `fecha;concepto;importe`. Por ejemplo:

```csv
fecha;concepto;importe
01/01/2026;Ingreso de cliente;1.000,00
02/01/2026;Pago de proveedor;-250,00
```

Banco y mayor deben expresar entradas positivas y salidas negativas.
Introduce los saldos inicial y final de ambos documentos. La pantalla muestra
el control inicial + movimientos - final de cada documento y la diferencia
entre los saldos de banco y mayor.

Cada registro conserva los campos originales, identificador de origen y número
de registro CSV (no necesariamente línea física si hay conceptos multilínea).
Las coincidencias se proponen solo por fecha, concepto e importe con signo;
no aprueban ninguna partida. Los duplicados se conservan y se señalan. Los
cobros agrupados permanecen sin pareja y requieren revisión manual. Un registro
inválido rechaza todo el archivo con un error; no se descartan filas erróneas.

Los archivos y resultados no se guardan: la vista se pierde al recargar.
Todavía no hay Excel/PDF, aprobación manual persistente, exportación ni
conciliación definitiva. Los endpoints nuevos comprueban la pertenencia a la
empresa y rechazan orígenes web ajenos; siguen pendientes los bloqueadores
de producción indicados arriba.

Pruebas del motor (sin dependencias adicionales):

```bash
python -m unittest discover -s tests -v
```
