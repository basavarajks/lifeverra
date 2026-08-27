"""
Central configuration for LifeVerra, read from environment variables.

Nothing sensitive is hardcoded here. Copy `.env.example` to `.env` (or set
real environment variables in your hosting platform) before deploying.
python-dotenv is used only if it's installed and a .env file is present;
the app still runs fine from real OS environment variables without it.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# --- Core security -----------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    # Fail loudly rather than silently running with a guessable dev key in
    # anything that looks like production. In local/demo dev, this still
    # lets the app boot with a per-process random key so nothing crashes,
    # but sessions won't survive a restart - set SECRET_KEY for real use.
    import secrets
    SECRET_KEY = secrets.token_hex(32)
    print("[config] WARNING: SECRET_KEY is not set in the environment. "
          "Using a temporary random key for this process only - all "
          "sessions will be invalidated on restart. Set SECRET_KEY in "
          "your .env for production.")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
if not ADMIN_PASSWORD:
    print("[config] WARNING: ADMIN_PASSWORD is not set. The admin login "
          "endpoint will reject all logins until you set it in .env.")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./lifeverra.db")
# Some hosts (Heroku-style) hand out "postgres://" URLs, but SQLAlchemy's
# psycopg2 driver requires the "postgresql://" scheme - normalize it here
# so copy-pasting either form just works.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# --- CORS ----------------------------------------------------------------
# Comma-separated list of allowed origins in production, e.g.
# "https://lifeverra.app,https://app.lifeverra.app". Defaults to "*" for
# local development only.
_cors = os.environ.get("CORS_ORIGINS", "*")
CORS_ORIGINS = [o.strip() for o in _cors.split(",")] if _cors != "*" else ["*"]

# --- Maps / Places ---------------------------------------------------------
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# --- Google Sign-In (patient login/registration) -------------------------
# OAuth 2.0 Web Client ID from https://console.cloud.google.com/apis/credentials
# Required for the "Continue with Google" button to work; without it, the
# backend reports google sign-in as unavailable and the frontend falls
# back to email + password only (see GET /api/auth/google/config).
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
