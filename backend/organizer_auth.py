
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing
from getpass import getpass
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

router = APIRouter(tags=["Organizer Authentication"])

from db_config import DB_PATH
COOKIE_NAME = "eventmesh_organizer_session"
SESSION_SECONDS = 12 * 60 * 60


def connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize_auth():
    with closing(connect()) as conn, conn as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS organizer_accounts (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS organizer_sessions (
                token_hash TEXT PRIMARY KEY,
                organizer_id TEXT NOT NULL
                    REFERENCES organizer_accounts(id),
                expires_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_organizer_sessions_expiry
            ON organizer_sessions(expires_at);
        """)

        # Preserve existing accounts while supporting display names.
        columns = {
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(organizer_accounts)"
            )
        }

        if "display_name" not in columns:
            db.execute(
                "ALTER TABLE organizer_accounts "
                "ADD COLUMN display_name TEXT NOT NULL DEFAULT ''"
            )


def hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=16384,
        r=8,
        p=1,
        dklen=32,
    )


def validate_email(email: str) -> str:
    normalized = email.strip().lower()

    if (
        not normalized
        or len(normalized) > 254
        or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            normalized,
        )
    ):
        raise ValueError("Enter a valid organizer email")

    return normalized


def validate_password(password: str):
    if not 12 <= len(password) <= 128:
        raise ValueError(
            "Password must contain 12 to 128 characters"
        )


def create_first_organizer(email: str, password: str):
    normalized = validate_email(email)
    validate_password(password)

    salt = secrets.token_bytes(16)
    password_hash = hash_password(password, salt)

    with closing(connect()) as conn, conn as db:
        db.execute("BEGIN IMMEDIATE")

        existing = db.execute(
            "SELECT COUNT(*) FROM organizer_accounts"
        ).fetchone()[0]

        if existing:
            raise ValueError(
                "Initial organizer already exists. "
                "Additional accounts require an invitation "
                "or demo registration."
            )

        db.execute("""
            INSERT INTO organizer_accounts (
                id,
                email,
                password_salt,
                password_hash,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            secrets.token_hex(16),
            normalized,
            salt,
            password_hash,
            int(time.time()),
        ))


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    confirm_password: str


def registration_enabled() -> bool:
    return os.environ.get(
        "EVENTMESH_ENABLE_REGISTRATION", ""
    ).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@router.post(
    "/auth/organizer/register",
    status_code=201,
)
def organizer_register(payload: RegisterRequest):
    # Registration is opt-in for the local hackathon demo.
    if not registration_enabled():
        raise HTTPException(
            403,
            "Organizer registration is disabled",
        )

    name = payload.name.strip()

    if not 2 <= len(name) <= 80:
        raise HTTPException(
            422,
            "Name must contain 2 to 80 characters",
        )

    try:
        email = validate_email(payload.email)
        validate_password(payload.password)
    except ValueError as exc:
        raise HTTPException(
            422,
            str(exc),
        ) from exc

    if payload.password != payload.confirm_password:
        raise HTTPException(
            422,
            "Passwords do not match",
        )

    salt = secrets.token_bytes(16)
    password_hash = hash_password(
        payload.password,
        salt,
    )

    try:
        with closing(connect()) as conn, conn as db:
            db.execute("""
                INSERT INTO organizer_accounts (
                    id,
                    email,
                    display_name,
                    password_salt,
                    password_hash,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                secrets.token_hex(16),
                email,
                name,
                salt,
                password_hash,
                int(time.time()),
            ))

    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            409,
            "An organizer with this email already exists",
        ) from exc

    return {
        "created": True,
        "email": email,
    }


@router.post("/auth/organizer/login")
def organizer_login(
    payload: LoginRequest,
    response: Response,
    request: Request,
):
    email = payload.email.strip().lower()

    with closing(connect()) as conn, conn as db:
        account = db.execute("""
            SELECT
                id,
                email,
                password_salt,
                password_hash
            FROM organizer_accounts
            WHERE email = ?
        """, (email,)).fetchone()

        if not account:
            raise HTTPException(
                401,
                "Invalid credentials",
            )

        if not hmac.compare_digest(
            hash_password(
                payload.password,
                account["password_salt"],
            ),
            account["password_hash"],
        ):
            raise HTTPException(
                401,
                "Invalid credentials",
            )

        token = secrets.token_urlsafe(32)

        token_hash = hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

        db.execute("""
            INSERT INTO organizer_sessions (
                token_hash,
                organizer_id,
                expires_at
            )
            VALUES (?, ?, ?)
        """, (
            token_hash,
            account["id"],
            int(time.time()) + SESSION_SECONDS,
        ))

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=SESSION_SECONDS,
        path="/",
    )

    return {
        "authenticated": True,
        "email": account["email"],
    }


def authenticated_organizer(request: Request):
    token = request.cookies.get(COOKIE_NAME)

    if not token:
        raise HTTPException(
            401,
            "Authentication required",
        )

    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    with closing(connect()) as conn, conn as db:
        account = db.execute("""
            SELECT a.id, a.email
            FROM organizer_sessions s
            JOIN organizer_accounts a
              ON a.id = s.organizer_id
            WHERE s.token_hash = ?
              AND s.expires_at > ?
        """, (
            token_hash,
            int(time.time()),
        )).fetchone()

    if not account:
        raise HTTPException(
            401,
            "Session invalid or expired",
        )

    return {
        "id": account["id"],
        "email": account["email"],
    }


@router.get("/auth/organizer/me")
def organizer_me(request: Request):
    return authenticated_organizer(request)


@router.post("/auth/organizer/logout")
def organizer_logout(
    request: Request,
    response: Response,
):
    token = request.cookies.get(COOKIE_NAME)

    if token:
        token_hash = hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

        with closing(connect()) as conn, conn as db:
            db.execute(
                "DELETE FROM organizer_sessions "
                "WHERE token_hash = ?",
                (token_hash,),
            )

    response.delete_cookie(
        COOKIE_NAME,
        path="/",
    )

    return {"authenticated": False}


def bootstrap_demo_organizer():
    """Create one organizer on a NEW database using private server variables.

    Does not overwrite or change an existing account. Safe to rerun at startup.
    Public registration remains separately disabled by default.
    """
    email = os.environ.get("EVENTMESH_BOOTSTRAP_ORGANIZER_EMAIL", "").strip()
    password = os.environ.get("EVENTMESH_BOOTSTRAP_ORGANIZER_PASSWORD", "")
    if not email and not password:
        return
    if not email or not password:
        raise RuntimeError(
            "Both EVENTMESH_BOOTSTRAP_ORGANIZER_EMAIL and "
            "EVENTMESH_BOOTSTRAP_ORGANIZER_PASSWORD are required"
        )
    with closing(connect()) as db:
        count = db.execute(
            "SELECT COUNT(*) FROM organizer_accounts"
        ).fetchone()[0]
    if count:
        return
    try:
        create_first_organizer(email, password)
    except ValueError as exc:
        raise RuntimeError("Invalid demo organizer bootstrap settings") from exc


initialize_auth()
bootstrap_demo_organizer()


if __name__ == "__main__":
    print("EventMesh AI - Initial Organizer Setup")

    email = input("Organizer email: ").strip()
    password = getpass(
        "Create password (12+ characters): "
    )
    confirm = getpass("Confirm password: ")

    if password != confirm:
        raise SystemExit(
            "Passwords do not match"
        )

    try:
        create_first_organizer(
            email,
            password,
        )
        print(
            "Initial organizer account created."
        )
    except ValueError as exc:
        raise SystemExit(str(exc))
