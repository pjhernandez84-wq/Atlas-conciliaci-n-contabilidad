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

Contraseñas con Argon2; tokens de sesión aleatorios; en SQLite solo se conserva SHA-256 del token. Sesiones de 8 horas; cookies HttpOnly, SameSite=Strict y Secure por defecto. Tablas `users`, `companies`, `memberships` y `sessions`. Cada empresa y usuario debe verificarse en **cada endpoint nuevo**. Las empresas no se precargan: se introducirán con permisos explícitos en un futuro módulo de administración.

### Bloqueadores para producción

- Control CSRF de operaciones con cookie y política CORS estricta.
- Límites de intentos de acceso y auditoría.
- Administración segura de usuarios/roles y recuperación de cuentas.
- Migraciones, copias de seguridad cifradas y despliegue HTTPS.
- Pruebas de seguridad y aislamiento multiempresa.

## Conciliación contable (siguiente etapa)

Comparación banco vs mayor línea a línea: fecha, concepto, importe, signo, duplicados, cobros agrupados y saldos de apertura/cierre. Nunca marcar una conciliación como correcta basándose exclusivamente en coincidencias automáticas.
