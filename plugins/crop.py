# -*- coding: utf-8 -*-
"""
OverlayX - Crop Plugin
==========================
Plugin que faz crop inteligente do vídeo.

Autor: OverlayX
"""

from typing import Optional, Dict, Any
from PIL import Image, ImageOps

from .base import Plugin


class CropPlugin(Plugin):
    """Plugin que faz crop inteligente do vídeo"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("crop", config)
        self.target_size = (1280, 720)
    
    def initialize(self, app_config) -> bool:
        super().initialize(app_config)
        self.target_size = (app_config.width, app_config.height)
        return True
    
    def process_frame(self, frame: Image.Image, draw) -> Image.Image:
        return ImageOps.fit(frame, self.target_size, method=Image.Resampling.LANCZOS)
