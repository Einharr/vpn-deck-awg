"""VPN Deck AWG core modules."""

from .binary_manager import BinaryManager
from .config_manager_ext import ConfigManager
from .diagnostics import Diagnostics
from .protocol import analyse_config, detect_protocol
from .service_manager_ext import ServiceManager
from .settings_manager import SettingsManager

__all__ = [
    "BinaryManager",
    "ConfigManager",
    "Diagnostics",
    "ServiceManager",
    "SettingsManager",
    "analyse_config",
    "detect_protocol",
]
