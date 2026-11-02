import os
import sys
from pathlib import Path

os.environ.setdefault("GETLIYO_WEB_SOURCE", "1")  # testler karartılmış web-dist yerine kaynak dosyaları kullanır

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
