import os
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
os.environ["GEMINI_API_KEY"] = "chiave-di-prova"
os.environ["DB_ACQUE_FILE"] = str(RADICE / "fixtures" / "catalogo.json")
os.environ["CATALOGO_INTEGRAZIONI"] = str(RADICE / "fixtures" / "senza_integrazioni.json")
os.environ["DB_ENCICLOPEDIA_FILE"] = str(RADICE / "fixtures" / "enciclopedia.json")
sys.path.insert(0, str(RADICE / "app"))
