"""Atlas accounting: minimal local authentication and company-scoping prototype."""
import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from pydantic import BaseModel

DB_PATH = os.getenv("ATLAS_DB_PATH", "atlas.db")
COOKIE_SECURE = os.getenv("ATLAS_COOKIE_SECURE", "true").lower() == "true"
SESSION_TTL = 8 * 3600
ph = PasswordHasher()
app = FastAPI(title="Atlas Contabilidad (prototipo)")


@contextmanager
def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS companies (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS memberships (user_id INTEGER NOT NULL REFERENCES users(id), company_id INTEGER NOT NULL REFERENCES companies(id), role TEXT NOT NULL CHECK(role IN ('admin','accountant','viewer')), PRIMARY KEY(user_id,company_id));
        CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires_at INTEGER NOT NULL);
        """)
        users_count = con.execute("SELECT count(*) FROM users").fetchone()[0]
        email = os.getenv("ATLAS_BOOTSTRAP_EMAIL", "").strip().lower()
        password = os.getenv("ATLAS_BOOTSTRAP_PASSWORD", "")
        if users_count == 0 and email and len(password) >= 16:
            con.execute("INSERT INTO users (email,password_hash) VALUES (?,?)", (email, ph.hash(password)))


@app.on_event("startup")
def startup():
    init_db()


class Credentials(BaseModel):
    email: str
    password: str


def token_digest(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(request: Request):
    token = request.cookies.get("atlas_session")
    if not token:
        raise HTTPException(401, "No autenticado")
    with db() as con:
        user = con.execute("""SELECT u.id,u.email FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>?""", (token_digest(token), int(time.time()))).fetchone()
    if not user:
        raise HTTPException(401, "Sesión no válida o caducada")
    return dict(user)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/login")
def login(credentials: Credentials, response: Response):
    with db() as con:
        row = con.execute("SELECT id,password_hash FROM users WHERE email=?", (credentials.email.strip().lower(),)).fetchone()
        try:
            valid = bool(row) and ph.verify(row["password_hash"], credentials.password)
        except (VerifyMismatchError, VerificationError):
            valid = False
        if not valid:
            raise HTTPException(401, "Credenciales incorrectas")
        token = secrets.token_urlsafe(48)
        con.execute("INSERT INTO sessions VALUES (?,?,?)", (token_digest(token), row["id"], int(time.time()) + SESSION_TTL))
    response.set_cookie("atlas_session", token, max_age=SESSION_TTL, httponly=True, secure=COOKIE_SECURE, samesite="strict", path="/")
    return {"message": "Sesión iniciada"}


@app.get("/auth/me")
def me(user=Depends(current_user)):
    return user


@app.post("/auth/logout")
def logout(request: Request, response: Response, user=Depends(current_user)):
    token = request.cookies.get("atlas_session")
    with db() as con:
        con.execute("DELETE FROM sessions WHERE token_hash=?", (token_digest(token),))
    response.delete_cookie("atlas_session", path="/", secure=COOKIE_SECURE, httponly=True, samesite="strict")
    return {"message": "Sesión cerrada"}


@app.get("/companies")
def companies(user=Depends(current_user)):
    with db() as con:
        rows = con.execute("""SELECT c.id,c.name,m.role FROM companies c JOIN memberships m ON m.company_id=c.id
            WHERE m.user_id=? ORDER BY c.name""", (user["id"],)).fetchall()
    return [dict(row) for row in rows]


# First reconciliation workspace. Uploaded CSV content is never persisted.
from pathlib import Path
import csv
from fastapi.responses import FileResponse
from pydantic import Field
from .reconciliation import preview


@app.get('/', include_in_schema=False)
def workspace():
    return FileResponse(Path(__file__).parent / 'static' / 'index.html')


def same_origin(request: Request):
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Origen no permitido')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Origen no permitido')


class NewCompany(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@app.post('/companies', dependencies=[Depends(same_origin)])
def create_company(data: NewCompany, user=Depends(current_user)):
    name = data.name.strip()
    if not name:
        raise HTTPException(422, 'Introduce el nombre de la empresa')
    with db() as con:
        try:
            cursor = con.execute('INSERT INTO companies (name) VALUES (?)', (name,))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Nombre de empresa no disponible')
        company_id = cursor.lastrowid
        con.execute("INSERT INTO memberships VALUES (?,?,'admin')", (user['id'], company_id))
    return {'id': company_id, 'name': name, 'role': 'admin'}


class Balances(BaseModel):
    banco_inicial: str = Field(max_length=40)
    banco_final: str = Field(max_length=40)
    mayor_inicial: str = Field(max_length=40)
    mayor_final: str = Field(max_length=40)


class PreviewInput(BaseModel):
    company_id: int = Field(gt=0)
    bank_csv: str = Field(max_length=1_000_000)
    ledger_csv: str = Field(max_length=1_000_000)
    balances: Balances


@app.post('/reconciliation/preview', dependencies=[Depends(same_origin)])
def reconciliation_preview(data: PreviewInput, user=Depends(current_user)):
    with db() as con:
        membership = con.execute('SELECT role FROM memberships WHERE user_id=? AND company_id=?',
                                 (user['id'], data.company_id)).fetchone()
    if not membership:
        raise HTTPException(403, 'Empresa no asignada')
    try:
        result = preview(data.bank_csv, data.ledger_csv, data.balances.model_dump())
    except (ValueError, csv.Error) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'company_id': data.company_id, **result}
