from dataclasses import dataclass
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
VERSIONS_ROOT = ROOT / "versions"
DEFAULT_VERSION = "19.0"
SHARED_ADDONS = ROOT / "custom_addons"
DEFAULT_CHROME = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
DEFAULT_POSTGRES_SERVICE = "postgresql-x64-18"


@dataclass(frozen=True)
class OdooPaths:
    version: str
    root: Path
    venv_python: Path
    odoo_server: Path
    odoo_bin: Path
    config: Path
    core_addons: Path
    shared_addons: Path
    version_addons: Path
    data_dir: Path
    browser_profile: Path


def normalize_version(version):
    value = str(version or DEFAULT_VERSION).strip()
    if value.isdigit():
        return f"{value}.0"
    return value


def available_versions():
    if not VERSIONS_ROOT.exists():
        return []
    return sorted(
        path.name
        for path in VERSIONS_ROOT.iterdir()
        if path.is_dir() and (path / "odoo-server" / "odoo-bin").exists()
    )


def get_paths(version=DEFAULT_VERSION):
    version = normalize_version(version)
    version_root = VERSIONS_ROOT / version
    return OdooPaths(
        version=version,
        root=version_root,
        venv_python=version_root / "venv" / "Scripts" / "python.exe",
        odoo_server=version_root / "odoo-server",
        odoo_bin=version_root / "odoo-server" / "odoo-bin",
        config=version_root / "odoo.conf",
        core_addons=version_root / "odoo-server" / "addons",
        shared_addons=SHARED_ADDONS,
        version_addons=version_root / "custom_addons",
        data_dir=version_root / "data",
        browser_profile=version_root / ".browser_debug_profile",
    )


def addons_path(paths):
    return ",".join(str(path) for path in addons_paths(paths))


def addons_paths(paths):
    paths_to_use = []
    for path in [paths.core_addons]:
        if path.exists():
            paths_to_use.append(path)
    if paths.version_addons.exists() and any(paths.version_addons.iterdir()):
        paths_to_use.append(paths.version_addons)
    if paths.shared_addons.exists():
        paths_to_use.append(paths.shared_addons)
    return paths_to_use


def add_odoo_to_path(paths):
    sys.path.insert(0, str(paths.odoo_server))
