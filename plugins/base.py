# -*- coding: utf-8 -*-
"""
OverlayX - Base Plugin
===========================
Classe base abstrata para todos os plugins.

Autor: OverlayX
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from PIL import Image, ImageDraw


class Plugin(ABC):
    """Classe base para todos os plugins"""
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}
        # show_by_default: if True, plugin starts visible; if False, starts hidden
        self.enabled = config.get('show_by_default', True) if config else True
        self.app_config = None
        self.shortcuts = config.get('shortcuts', {}) if config else {}
    
    @abstractmethod
    def initialize(self, app_config) -> bool:
        """Inicializa o plugin. Retorna True se bem-sucedido."""
        self.app_config = app_config
        return True
    
    @abstractmethod
    def process_frame(self, frame: Image.Image, draw: ImageDraw.Draw) -> Image.Image:
        """Processa um frame e retorna o frame modificado"""
        pass
    
    def on_keypress(self, key: str) -> bool:
        """Manipula teclas pressionadas. Retorna True se a tecla foi manipulada."""
        # Verifica se a tecla corresponde a alguma ação de atalho do plugin
        if self.shortcuts:
            for action, shortcut_key in self.shortcuts.items():
                if key == shortcut_key:
                    return self.handle_shortcut(action)
        return False
    
    def handle_shortcut(self, action: str) -> bool:
        """
        Manipula ações de atalho do plugin.
        
        Args:
            action: Nome da ação (ex: 'toggle', 'increase', 'decrease')
            
        Returns:
            True se a ação foi manipulada, False caso contrário
        """
        # Ação padrão: toggle (mostrar/esconder)
        if action == 'toggle':
            self.enabled = not self.enabled
            return True
        return False
    
    def update(self, delta_time: float):
        """Atualiza o estado do plugin (chamado a cada frame)"""
        pass
    
    def cleanup(self):
        """Limpa recursos do plugin"""
        pass
    
    def get_info(self) -> Dict[str, Any]:
        """Retorna informações do plugin para debugging"""
        return {"name": self.name, "enabled": self.enabled, "shortcuts": self.shortcuts}
