import os
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
os.environ["GEMINI_API_KEY"] = "chiave-di-prova"
# I test di sempre provano un motore solo; le riserve si accendono nei test che le riguardano.
os.environ["GEMINI_MODELLI_RISERVA"] = ""
os.environ["LLM_RISERVA_KEY"] = ""
os.environ["DB_ACQUE_FILE"] = str(RADICE / "fixtures" / "catalogo.json")
os.environ["CATALOGO_INTEGRAZIONI"] = str(RADICE / "fixtures" / "senza_integrazioni.json")
os.environ["DB_ENCICLOPEDIA_FILE"] = str(RADICE / "fixtures" / "enciclopedia.json")
sys.path.insert(0, str(RADICE / "app"))
