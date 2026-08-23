"""Parser capability discovery."""
from dataclasses import dataclass,asdict
from shutil import which
from importlib.util import find_spec
@dataclass(frozen=True)
class Capabilities:
 mineru:bool
 libreoffice:bool
 def public(self): return asdict(self)
def detect_capabilities()->Capabilities:
 return Capabilities(mineru=find_spec('mineru') is not None or which('mineru') is not None, libreoffice=which('libreoffice') is not None or which('soffice') is not None)
