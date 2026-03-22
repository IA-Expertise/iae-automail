import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DADOS_DIR = BASE_DIR / "dados"
DEFAULT_BLACKLIST = DADOS_DIR / "blacklist.csv"
EMAIL_ASSETS_DIR = DADOS_DIR / "email_assets"
ANEXOS_DIR = DADOS_DIR / "anexos"

SMTP_HOST = os.getenv("SMTP_HOST", "mail.iaesmartguide.com.br")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("AI_INTEGRATIONS_GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

IAE_DOMAIN = "iaesmartguide.com.br"
