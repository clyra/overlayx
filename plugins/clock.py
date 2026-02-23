# -*- coding: utf-8 -*-
"""
OverlayX - Clock Plugin
===========================
Plugin que exibe um relógio em tempo real sobre o vídeo.

Autor: OverlayX
"""

import os
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

from .base import Plugin


class ClockPlugin(Plugin):
    """Plugin que exibe um relógio"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("clock", config)
        self.format_str = "%H:%M:%S"
        self.font = None
        self.position = (1080, 20)
        self.font_size = 35
        self.show = True
        self.timezone = None  # Timezone specification (e.g., 'UTC', 'America/Sao_Paulo', or None for local)
    
    def initialize(self, app_config) -> bool:
        super().initialize(app_config)
        
        self.format_str = self.config.get('format', self.format_str)
        
        # Timezone configuration (optional)
        # Can be: None (local time), 'UTC', 'America/Sao_Paulo', etc.
        self.timezone = self.config.get('timezone', None)
        
        # Usa posição da própria config do plugin, se disponível
        # Caso contrário, usa as configurações globais (para compatibilidade)
        if 'position' in self.config:
            self.position = tuple(self.config['position'])
        elif hasattr(app_config, 'clock_position'):
            self.position = app_config.clock_position
        
        if 'font_size' in self.config:
            self.font_size = self.config['font_size']
        elif hasattr(app_config, 'clock_font_size'):
            self.font_size = app_config.clock_font_size
        
        if 'show' in self.config:
            self.show = self.config['show']
        elif 'show_by_default' in self.config:
            self.show = self.config['show_by_default']
        elif hasattr(app_config, 'show_clock'):
            self.show = app_config.show_clock
        else:
            self.show = True  # Default visibility
        
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
            font = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", self.font_size)
        except:
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", self.font_size)
            except:
                font = ImageFont.load_default()
        
        return font
    
    def _get_current_time(self) -> datetime:
        """
        Retorna o datetime atual, aplicando timezone se especificado na config.
        
        Suporta:
        - None: usa timezone local se o formato requerer (%z ou %Z), caso contrário hora local naive
        - 'local': usa timezone local do sistema
        - 'UTC': timezone UTC
        - 'America/Sao_Paulo', etc: timezone por nome (usa zoneinfo)
        """
        import zoneinfo
        
        # Check if format string requires timezone info
        needs_tz = '%z' in self.format_str or '%Z' in self.format_str
        
        if self.timezone is None:
            if needs_tz:
                # Use local timezone from system
                local_tz = datetime.now().astimezone().tzinfo
                return datetime.now(local_tz)
            else:
                # Return naive datetime for local time (default behavior)
                return datetime.now()
        
        if self.timezone.lower() == 'local':
            # Explicitly use local timezone
            local_tz = datetime.now().astimezone().tzinfo
            return datetime.now(local_tz)
        
        if not needs_tz:
            # No timezone needed, return local time
            return datetime.now()
        
        # Handle timezone specification
        tz = None
        if self.timezone.upper() == 'UTC':
            tz = timezone.utc
        else:
            try:
                tz = zoneinfo.ZoneInfo(self.timezone)
            except KeyError:
                print(f"Aviso: Timezone '{self.timezone}' não reconhecida. Usando hora local.")
                return datetime.now()
        
        return datetime.now(tz)
    
    def process_frame(self, frame: Image.Image, draw: ImageDraw.Draw) -> Image.Image:
        if not self.show:
            return frame
        
        # Get current time, handling timezone if specified
        now = self._get_current_time()
        hora_str = now.strftime(self.format_str)
        
        # Fundo semi-transparente
        bbox = draw.textbbox(self.position, hora_str, font=self.font)
        padding = 5
        draw.rectangle(
            [bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding],
            fill=(0, 0, 0, 100)
        )
        
        # Texto
        draw.text(self.position, hora_str, font=self.font, fill=(255, 255, 255, 255))
        
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
