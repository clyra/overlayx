# -*- coding: utf-8 -*-
"""
OverlayX - Plugins
=======================
Sistema de plugins para a aplicação VirtualCamPro.

Cada plugin deve herdar da classe Plugin definida em base.py
e implementar os métodos abstratos required.

Uso:
    from plugins import PluginManager
    from plugins.clock import ClockPlugin
    from plugins.cpu import CPUPlugin
    from plugins.overlay import OverlayPlugin
    from plugins.crop import CropPlugin
"""

from .base import Plugin
from .clock import ClockPlugin
from .cpu import CPUPlugin
from .overlay import OverlayPlugin
from .crop import CropPlugin
from .tlp import TLPPlugin
from .tail import TailPlugin

__all__ = [
    'Plugin',
    'ClockPlugin',
    'CPUPlugin',
    'OverlayPlugin',
    'CropPlugin',
    'TLPPlugin',
    'TailPlugin',
]
