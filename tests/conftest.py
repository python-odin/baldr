import sys
from pathlib import Path

HERE = Path(__file__).parent
SRC_PATH = HERE.parent.parent / "src"

sys.path.insert(0, SRC_PATH.as_posix())
