"""Load the empty defaults, then the ignored local credentials."""
from runpy import run_path
from types import SimpleNamespace

from project_paths import ROOT


def _load_config():
    folder = ROOT / "config"
    values = run_path(str(folder / "config.example.py"))
    local = folder / "config.py"
    if local.is_file():
        values.update(run_path(str(local)))
    return SimpleNamespace(**{name: value for name, value in values.items()
                              if name.isupper()})


config = _load_config()
