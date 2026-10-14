import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "15001"))
MODBUS_HOST = os.getenv("MODBUS_HOST", "0.0.0.0")
MODBUS_PORT = int(os.getenv("MODBUS_PORT", "5020"))
DATA_DIR = os.path.abspath(os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data")))
UI_DIST = os.path.join(BASE_DIR, "ui", "dist")
LOGLEVEL = os.getenv("LOGLEVEL", "INFO").upper()

# Max registers per auto-generated batch (Modbus limit is 125 for FC03/04)
MAX_BATCH = int(os.getenv("MAX_BATCH", "100"))
