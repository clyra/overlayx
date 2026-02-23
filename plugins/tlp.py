# -*- coding: utf-8 -*-
"""
OverlayX - TLP Plugin
======================
Plugin que exibe a classificação TLP (Traffic Light Protocol) do FIRST.org
sobre o vídeo.

O TLP é um protocolo de manipulação de sensibilidade de informação definido
pelo FIRST (Forum of Incident Response and Security Teams).

Níveis TLP:
- TLP:RED   - Não para divulgação,restrito aos participantes
- TLP:AMBER - Divulgação limitada, destinatários podem compartilhar com outros sob necessidade
- TLP:GREEN - Divulgação limitada, destinatários podem compartilhar, mas não publicamente  
- TLP:CLEAR - Divulgação não é limitada

Referência: https://www.first.org/tlp/

Autor: OverlayX
"""

from typing import Optional, Dict, Any
from PIL import Image, ImageDraw, ImageFont

from .base import Plugin


class TLPPlugin(Plugin):
    """Plugin que exibe classificação TLP"""
    
    # Constantes de classificação TLP
    TLP_RED = "RED"
    TLP_AMBER = "AMBER"
    TLP_GREEN = "GREEN"
    TLP_CLEAR = "CLEAR"
    
    # Mapeamento de cores para cada nível TLP
    # Formato: (text_color, background_color)
    TLP_COLORS = {
        TLP_RED: ((255, 43, 43), (0, 0, 0)),        # Red text on black background
        TLP_AMBER: ((255, 192, 0), (0, 0, 0)),      # Amber text on black background
        TLP_GREEN: ((51, 255, 0), (0, 0, 0)),       # Green text on black background
        TLP_CLEAR: ((255, 255, 255), (0, 0, 0)),   # White text on black background
    }
    
    # Atalhos para mudança de classificação
    TLP_SHORTCUTS = {
        'red': 'r',
        'amber': 'a', 
        'green': 'g',
        'clear': 'l',  # 'l' for "liberado" / clear
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("tlp", config)
        self.tlp_level = self.TLP_CLEAR  # Default to CLEAR (most open)
        self.font = None
        self.position = (20, 20)
        self.font_size = 18
        self.show = True
        self.padding = 8
    
    def initialize(self, app_config) -> bool:
        super().initialize(app_config)
        
        # Configuração do nível TLP padrão
        default_tlp = self.config.get('default_tlp', self.TLP_CLEAR)
        self.tlp_level = self._validate_tlp_level(default_tlp)
        
        # Posição do TLP na tela
        if 'position' in self.config:
            self.position = tuple(self.config['position'])
        
        # Tamanho da fonte
        if 'font_size' in self.config:
            self.font_size = self.config['font_size']
        
        # Padding
        self.padding = self.config.get('padding', 8)
        
        # Configuração de visibilidade
        if 'show' in self.config:
            self.show = self.config['show']
        elif 'show_by_default' in self.config:
            self.show = self.config['show_by_default']
        elif hasattr(app_config, 'show_tlp'):
            self.show = app_config.show_tlp
        else:
            self.show = True
        
        # Carrega fonte
        self.font = self._load_font(app_config)
        
        # Adiciona atalhos para mudança de classificação se não especificados
        if not self.shortcuts:
            self.shortcuts = dict(self.TLP_SHORTCUTS)
        
        return True
    
    def _validate_tlp_level(self, level: str) -> str:
        """Valida e retorna um nível TLP válido"""
        level_upper = level.upper() if isinstance(level, str) else self.TLP_CLEAR
        valid_levels = [self.TLP_RED, self.TLP_AMBER, self.TLP_GREEN, self.TLP_CLEAR]
        
        if level_upper in valid_levels:
            return level_upper
        
        print(f"Aviso: Nível TLP '{level}' não reconhecido. Usando TLP:CLEAR.")
        return self.TLP_CLEAR
    
    def _load_font(self, app_config) -> ImageFont.ImageFont:
        """Carrega fonte a partir da configuração do plugin ou assets"""
        font = None
        
        # 1. Tenta carregar de caminho direto especificado no plugin config
        if 'font_path' in self.config:
            try:
                font = ImageFont.truetype(self.config['font_path'], self.font_size)
                return font
            except FileNotFoundError:
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
                    except FileNotFoundError:
                        pass
                    except OSError:
                        pass
        
        # 3. Fallback para fonte padrão do sistema (macOS)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", self.font_size)
        except FileNotFoundError:
            try:
                font = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", self.font_size)
            except (FileNotFoundError, OSError):
                font = ImageFont.load_default()
        except OSError:
            font = ImageFont.load_default()
        
        return font
    
    def process_frame(self, frame: Image.Image, draw: ImageDraw.Draw) -> Image.Image:
        if not self.show:
            return frame
        
        # Formata o texto TLP
        tlp_text = f"TLP:{self.tlp_level}"
        
        # Obtém cores para o nível atual
        text_color, bg_color = self.TLP_COLORS.get(
            self.tlp_level, 
            self.TLP_COLORS[self.TLP_CLEAR]
        )
        
        # Calcula bounding box do texto
        bbox = draw.textbbox(self.position, tlp_text, font=self.font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Calcula retângulo de fundo com padding
        x1 = self.position[0] - self.padding
        y1 = self.position[1] - self.padding
        x2 = self.position[0] + text_width + self.padding
        y2 = self.position[1] + text_height + self.padding
        
        # Desenha fundo preto
        draw.rectangle([x1, y1, x2, y2], fill=bg_color)
        
        # Desenha texto
        draw.text(self.position, tlp_text, font=self.font, fill=text_color)
        
        return frame
    
    def handle_shortcut(self, action: str) -> bool:
        """Manipula ações de atalho do plugin."""
        if action == 'toggle':
            self.show = not self.show
            return True
        
        # Atalhos para mudança de classificação
        action_lower = action.lower()
        if action_lower == 'red':
            self.tlp_level = self.TLP_RED
            return True
        elif action_lower == 'amber':
            self.tlp_level = self.TLP_AMBER
            return True
        elif action_lower == 'green':
            self.tlp_level = self.TLP_GREEN
            return True
        elif action_lower == 'clear':
            self.tlp_level = self.TLP_CLEAR
            return True
        
        return False
    
    def on_keypress(self, key: str) -> bool:
        """Manipula teclas pressionadas - delega para o sistema de atalhos do plugin."""
        # Verifica se a tecla corresponde a alguma ação de atalho do plugin
        if self.shortcuts:
            for action, shortcut_key in self.shortcuts.items():
                if key == shortcut_key:
                    return self.handle_shortcut(action)
        return False
    
    def set_tlp_level(self, level: str) -> bool:
        """
        Define o nível TLP.
        
        Args:
            level: Novo nível TLP (RED, AMBER, GREEN, CLEAR)
            
        Returns:
            True se o nível foi alterado, False se nível inválido
        """
        new_level = self._validate_tlp_level(level)
        if new_level != self.tlp_level:
            self.tlp_level = new_level
            return True
        return False
    
    def get_tlp_level(self) -> str:
        """Retorna o nível TLP atual."""
        return self.tlp_level
