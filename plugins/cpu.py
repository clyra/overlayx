# -*- coding: utf-8 -*-
"""
OverlayX - CPU Plugin
========================
Plugin que exibe o uso de CPU do sistema.

Autor: OverlayX
"""

import time
import psutil
from typing import Optional, Dict, Any
from PIL import Image, ImageDraw, ImageFont

from .base import Plugin


class CPUPlugin(Plugin):
    """Plugin que exibe uso de CPU"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("cpu", config)
        self.cpu_usage = "CPU: 0%"
        self.last_check = 0
        self.update_interval = 2.0
        self.show = True
        self.font = None
        self.position = (40, 35)
        self.font_size = 18
    
    def initialize(self, app_config) -> bool:
        super().initialize(app_config)
        
        self.update_interval = self.config.get('update_interval', 2.0)
        
        # Usa posição da própria config do plugin, se disponível
        # Caso contrário, usa as configurações globais (para compatibilidade)
        if 'position' in self.config:
            self.position = tuple(self.config['position'])
        elif hasattr(app_config, 'cpu_position'):
            self.position = app_config.cpu_position
        
        if 'font_size' in self.config:
            self.font_size = self.config['font_size']
        elif hasattr(app_config, 'info_font_size'):
            self.font_size = app_config.info_font_size
        
        if 'show' in self.config:
            self.show = self.config['show']
        elif 'show_by_default' in self.config:
            self.show = self.config['show_by_default']
        elif hasattr(app_config, 'show_cpu'):
            self.show = app_config.show_cpu
        else:
            self.show = True  # Default visibility
        
        self.show_system = self.config.get('show_system', True)
        
        # Carrega fonte - primeiro tenta usar configuração do plugin, depois assets
        self.font = self._load_font(app_config)
        
        return True
    
    def _load_font(self, app_config) -> ImageFont.ImageFont:
        """Carrega fonte a partir da configuração do plugin ou assets"""
        font = None
        
        # 1. Tenta carregar de caminho direto especificado no plugin config
        if 'font_path' in self.config:
            try:
                font = ImageFont.truetype(self.config['font_path'], self.font_size)
                return font
            except:
                pass
        
        # 2. Tenta encontrar por nome nos assets
        if 'font' in self.config and hasattr(app_config, 'assets'):
            font_name = self.config['font']
            fonts_list = app_config.assets.get('fonts', [])
            for f in fonts_list:
                if f.get('name') == font_name:
                    try:
                        font = ImageFont.truetype(f.get('path'), self.font_size)
                        return font
                    except:
                        pass
        
        # 3. Fallback para fonte padrão do sistema
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", self.font_size)
        except:
            try:
                font = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", self.font_size)
            except:
                font = ImageFont.load_default()
        
        return font
    
    def process_frame(self, frame: Image.Image, draw: ImageDraw.Draw) -> Image.Image:
        if not self.show:
            return frame
        
        # Atualiza CPU
        if time.time() - self.last_check > self.update_interval:
            cpu = psutil.cpu_percent()
            self.cpu_usage = f"CPU: {int(cpu)}%"
            self.last_check = time.time()
        
        draw.text(self.position, self.cpu_usage, font=self.font, fill=(0, 255, 0, 200))
        
        return frame
    
    def handle_shortcut(self, action: str) -> bool:
        """Manipula ações de atalho do plugin."""
        if action == 'toggle':
            self.show = not self.show
            return True
        return False
    
    def on_keypress(self, key: str) -> bool:
        """Manipula teclas pressionadas - delega para o sistema de atalhos do plugin."""
        return super().on_keypress(key)
