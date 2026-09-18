import hashlib
import secrets
import time

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..core.errors import AppError
from ..models.identity import AuthSession, User, UserPreference

password_hasher = PasswordHash.recommended()
dummy_hash = password_hasher.hash("solomeal-dummy-password-for-timing")


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def register(db, credentials):
    hashed = password_hasher.hash(credentials.password)
    try:
        with db.begin():
            user = User(username=credentials.username, password_hash=hashed)
            db.add(user)
            db.flush()
            db.add(UserPreference(user_id=user.id))
        return user
    except IntegrityError as exc:
        raise AppError(409, "USERNAME_TAKEN", "Username is already registered") from exc


def login(db, credentials, ttl):
    with db.begin():
        user = db.scalar(select(User).where(User.username == credentials.username))
        valid = password_hasher.verify(
            credentials.password, user.password_hash if user else dummy_hash
        )
        if user is None or not valid:
            raise AppError(401, "INVALID_CREDENTIALS", "Invalid username or password")
        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + ttl
        db.add(AuthSession(token_hash=digest_token(token), user_id=user.id, expires_at=expires_at))
    return {"access_token": token, "expires_at": expires_at}


def authenticate(db, token):
    auth = db.get(AuthSession, digest_token(token))
    if auth is None or auth.expires_at <= int(time.time()):
        raise AppError(401, "UNAUTHENTICATED", "A valid session is required")
    user = db.get(User, auth.user_id)
    if user is None:
        raise AppError(401, "UNAUTHENTICATED", "A valid session is required")
    return user, auth


def get_preferences(db, user_id):
    preferences = db.get(UserPreference, user_id)
    if preferences is None:
        raise AppError(404, "NOT_FOUND", "Preferences not found")
    return preferences


def update_preferences(db, user_id, values):
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    db.expire_all()
    preferences = get_preferences(db, user_id)
    for key, value in values.model_dump().items():
        setattr(preferences, key, value)
    db.commit()
    return preferences
