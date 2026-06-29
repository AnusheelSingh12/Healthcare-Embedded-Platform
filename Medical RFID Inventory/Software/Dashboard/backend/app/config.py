from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"
DATABASE_URL = "sqlite:///./rfid_inventory.db"
ALLOWED_ORIGINS = ["*"]
SERIAL_BAUDRATE = 9600
SERIAL_TIMEOUT = 1.0
