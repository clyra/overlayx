# -*- coding: utf-8 -*-
"""
OverlayX - Overlay Plugin
============================
Plugin que aplica overlay (molduras, watermarks, figuras) sobre o vídeo.
Suporta múltiplas instâncias com diferentes imagens, posições e opacidade.

Opções de redimensionamento:
- fit: true  -> redimensiona para o tamanho do output
- fit: false + resize: 1.0 -> mantém tamanho original
- fit: false + resize: 0.5 -> 50% do tamanho original
- fit: false + resize: 2.0 -> dobro do tamanho original

Autor: OverlayX
"""

import os
from typing import Optional, Dict, Any, Tuple
from PIL import Image, ImageDraw

from .base import Plugin


class OverlayPlugin(Plugin):
    """Plugin que aplica overlay (moldura/watermark) sobre o vídeo"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("overlay", config)
        self.overlay_image = None
        self.file = "moldura.png"
        self.enabled = True
        self.opacity = 1.0
        self.position: Tuple[int, int] = (0, 0)
        self.fit: bool = False
        self.resize: float = 1.0  # Fator de redimensionamento (1.0 = original)
    
    def initialize(self, app_config) -> bool:
        super().initialize(app_config)
        
        # Arquivo de imagem (pode ser moldura, watermark, etc)
        self.file = self.config.get('file', 'moldura.png')
        
        # Usa enabled da própria config do plugin
        if 'enabled' in self.config:
            self.enabled = self.config['enabled']
        elif 'show_by_default' in self.config:
            self.enabled = self.config['show_by_default']
        elif hasattr(app_config, 'overlay_enabled'):
            self.enabled = app_config.overlay_enabled
        else:
            self.enabled = True  # Default visibility
        
        # Opacidade (0.0 a 1.0)
        self.opacity = self.config.get('opacity', 1.0)
        
        # Posição do overlay [x, y]
        pos = self.config.get('position', [0, 0])
        self.position = tuple(pos) if isinstance(pos, list) else pos
        
        # Flags de redimensionamento
        self.fit = self.config.get('fit', False)
        self.resize = self.config.get('resize', 1.0)
        
        # Carrega overlay
        if os.path.exists(self.file):
            self.overlay_image = Image.open(self.file).convert('RGBA')
            
            # Aplica redimensionamento conforme as flags
            self.overlay_image = self._apply_resize(self.overlay_image, app_config)
        else:
            print(f"Aviso: Arquivo de overlay não encontrado: {self.file}")
        
        return True
    
    def _apply_resize(self, image: Image.Image, app_config) -> Image.Image:
        """
        Aplica redimensionamento baseado nas flags fit e resize.
        
        - fit: true  -> redimensiona para o tamanho do output
        - fit: false + resize: 1.0 -> mantém tamanho original
        - fit: false + resize: 0.5 -> 50% do tamanho original
        - fit: false + resize: 2.0 -> dobro do tamanho original
        """
        if self.fit:
            # Fit: redimensiona para o tamanho do output
            target_size = (app_config.width, app_config.height)
            if image.size != target_size:
                image = image.resize(target_size, Image.Resampling.LANCZOS)
        elif self.resize != 1.0:
            # Resize por percentual
            new_width = int(image.width * self.resize)
            new_height = int(image.height * self.resize)
            if (new_width, new_height) != image.size:
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        # Se fit=false e resize=1.0, mantém tamanho original
        
        return image
    
    def process_frame(self, frame: Image.Image, draw: ImageDraw.Draw) -> Image.Image:
        if not self.enabled or self.overlay_image is None:
            return frame
        
        if self.opacity < 1.0:
            # Aplica opacidade
            overlay_copy = self.overlay_image.copy()
            alpha = overlay_copy.split()[3]
            alpha = alpha.point(lambda p: p * self.opacity)
            overlay_copy.putalpha(alpha)
            frame.paste(overlay_copy, self.position, mask=overlay_copy)
        else:
            frame.paste(self.overlay_image, self.position, mask=self.overlay_image)
        
        return frame
    
    def on_keypress(self, key: str) -> bool:
        """Manipula teclas pressionadas - delega para o sistema de atalhos do plugin."""
        # Verifica atalhos do plugin
        if self.shortcuts:
            for action, shortcut_key in self.shortcuts.items():
                if key == shortcut_key:
                    if action == 'toggle':
                        self.enabled = not self.enabled
                        return True
        return False
