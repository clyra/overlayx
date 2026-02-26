# -*- coding: utf-8 -*-
"""
OverlayX - Tail Plugin
===========================
Plugin que exibe o conteúdo de um arquivo em tempo real (similar ao tail -f).

Autor: OverlayX
"""

import os
import sys
import time
from typing import Optional, Dict, Any, List
from PIL import Image, ImageDraw, ImageFont

from .base import Plugin


class TailPlugin(Plugin):
    """Plugin que exibe o conteúdo de um arquivo em tempo real (tail -f)"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("tail", config)
        
        # Configurações do arquivo
        self.file_path: str = ""
        
        # Configurações de posição e tamanho
        self.position: tuple = (50, 50)
        self.width: int = 400
        self.height: int = 200
        
        # Configurações de fonte
        self.font_size: int = 14
        self.font: Optional[ImageFont.ImageFont] = None
        self.font_name: Optional[str] = None
        
        # Configurações de cores
        self.text_color: tuple = (255, 255, 255, 255)  # RGBA
        self.background_color: tuple = (0, 0, 0, 150)  # RGBA com transparência
        self.opacity: float = 1.0  # Fator de transparência (0.0 a 1.0)
        
        # Configurações de comportamento
        self.lines: int = 10  # Número de linhas a mostrar
        self.update_interval: float = 0.5  # Intervalo de atualização em segundos
        self.show: bool = True
        self.breakline: bool = False  # Se True, quebra linha; se False, trunca com "..."
        self.following: bool = True  # Se True, tail -f (últimas linhas); se False, mostra primeiras linhas
        
        # Estado interno
        self._last_file_size: int = 0
        self._last_mtime: float = 0
        self._content: List[str] = []
        self._last_update: float = 0  # Initialize to 0 so first update always runs
    
    def initialize(self, app_config) -> bool:
        super().initialize(app_config)
        
        # Carrega configurações do arquivo
        self.file_path = self.config.get('file', '')
        if not self.file_path:
            print("Erro: Plugin 'tail' requer configuração 'file' (caminho do arquivo)")
            return False
        
        # Verifica se o arquivo existe
        if not os.path.exists(self.file_path):
            print(f"Aviso: Arquivo '{self.file_path}' não existe. O plugin será habilitado quando o arquivo for criado.")
        
        # Posição
        if 'position' in self.config:
            self.position = tuple(self.config['position'])
        
        # Tamanho da caixa de texto
        if 'width' in self.config:
            self.width = self.config['width']
        if 'height' in self.config:
            self.height = self.config['height']
        
        # Configurações de fonte
        if 'font_size' in self.config:
            self.font_size = self.config['font_size']
        
        # Cor do texto (pode ser especificada como [R, G, B, A] ou [R, G, B])
        if 'text_color' in self.config:
            colors = self.config['text_color']
            if len(colors) == 4:
                self.text_color = tuple(colors)
            elif len(colors) == 3:
                self.text_color = tuple(colors) + (255,)
        
        # Cor de fundo (pode ser especificada como [R, G, B, A] ou [R, G, B])
        # A opacidade é aplicada separadamente em process_frame
        if 'background_color' in self.config:
            colors = self.config['background_color']
            if len(colors) == 4:
                self.background_color = tuple(colors)
            elif len(colors) == 3:
                self.background_color = tuple(colors) + (255,)  # Alpha completo, opacity aplicada depois
        else:
            self.background_color = (0, 0, 0, 255)  # Padrão: preto opaco
        
        # Opacity (transparência) - controla a transparência do fundo
        # Valor de 0.0 (totalmente transparente) a 1.0 (opaco)
        self.opacity = self.config.get('opacity', 1.0)
        
        # Número de linhas
        if 'lines' in self.config:
            self.lines = self.config['lines']
        
        # Intervalo de atualização
        if 'update_interval' in self.config:
            self.update_interval = self.config['update_interval']
        
        # Visibilidade
        if 'show' in self.config:
            self.show = self.config['show']
        elif 'show_by_default' in self.config:
            self.show = self.config['show_by_default']
        
        # Breakline: se True, quebra linha; se False, trunca com "..."
        if 'breakline' in self.config:
            self.breakline = self.config['breakline']
        
        # Following: se True, tail -f (seguir últimas linhas); se False, mostra primeiras linhas
        if 'following' in self.config:
            self.following = self.config['following']
        
        # Carrega fonte
        self.font = self._load_font(app_config)
        
        # Inicializa leitura do arquivo
        self._read_file()
        self._last_update = time.time()  # Prevent redundant read on first frame
        
        return True
    
    def _load_font(self, app_config) -> ImageFont.ImageFont:
        """Carrega fonte a partir da configuração do plugin ou assets"""
        font = None
        
        # 1. Tenta carregar de caminho direto especificado no plugin config
        if 'font_path' in self.config:
            try:
                font = ImageFont.truetype(self.config['font_path'], self.font_size)
                return font
            except OSError:
                pass
        
        # 2. Tenta encontrar por nome nos assets
        if 'font' in self.config:
            self.font_name = self.config['font']
            fonts_list = app_config.assets.get('fonts', [])
            for f in fonts_list:
                if f.get('name') == self.font_name:
                    try:
                        font = ImageFont.truetype(f.get('path'), self.font_size)
                        return font
                    except OSError:
                        pass
        
        # 3. Fallback para fonte padrão do sistema (cross-platform)
        # Tenta detectar e usar fontes do sistema operacional
        font_paths = []
        
        if sys.platform == 'darwin':  # macOS
            font_paths = [
                "/System/Library/Fonts/SFNS.ttf",
                "/System/Library/Fonts/Menlo.ttc",
                "/Library/Fonts/Menlo.ttc",
            ]
        elif sys.platform == 'win32':  # Windows
            font_paths = [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/consola.ttf",
                "C:/Windows/Fonts/cour.ttf",
            ]
        elif sys.platform == 'linux':  # Linux
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/TTF/DejaVuSans.ttf",
                "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            ]
        
        for font_path in font_paths:
            try:
                font = ImageFont.truetype(font_path, self.font_size)
                return font
            except OSError:
                continue
        
        # 4. Ultimate fallback - PIL's default font
        return ImageFont.load_default()
    
    def _read_file(self):
        """Lê o conteúdo do arquivo (similar ao tail)"""
        if not os.path.exists(self.file_path):
            self._content = [f"[Arquivo não encontrado: {self.file_path}]"]
            return
        
        try:
            stat = os.stat(self.file_path)
            file_size = stat.st_size
            mtime = stat.st_mtime
            
            # Se o arquivo não mudou, não relê
            if file_size == self._last_file_size and mtime == self._last_mtime:
                return
            
            self._last_file_size = file_size
            self._last_mtime = mtime
            
            # Lê o arquivo
            with open(self.file_path, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()
            
            # Pega as linhas conforme modo following:
            # following=True: últimas N linhas (tail -f)
            # following=False: primeiras N linhas
            if self.following:
                self._content = all_lines[-self.lines:] if len(all_lines) > self.lines else all_lines
            else:
                self._content = all_lines[:self.lines] if len(all_lines) > self.lines else all_lines
            
            # Remove quebras de linha extras
            self._content = [line.rstrip('\n\r') for line in self._content]
            
        except Exception as e:
            self._content = [f"[Erro ao ler arquivo: {e}]"]
    
    def update(self, delta_time: float):
        """Atualiza o conteúdo do arquivo periodicamente"""
        current_time = time.time()
        
        if current_time - self._last_update >= self.update_interval:
            self._read_file()
            self._last_update = current_time
    
    def process_frame(self, frame: Image.Image, draw: ImageDraw.Draw) -> Image.Image:
        if not self.show:
            return frame
        
        # Converte para RGBA para suportar transparência
        frame = frame.convert('RGBA')
        
        # Cria imagem de fundo separada com opacidade aplicada (como em OverlayPlugin)
        if self.opacity < 1.0:
            # Cria imagem de fundo com a cor base
            bg_box = Image.new('RGBA', 
                (self.width, self.height), 
                self.background_color[:3] + (255,))  # Alpha 255, depois aplica opacity
            
            # Aplica opacidade à imagem de fundo
            alpha = bg_box.split()[3]
            alpha = alpha.point(lambda p: p * self.opacity)
            bg_box.putalpha(alpha)
        else:
            # Sem opacidade, usa direto
            bg_box = Image.new('RGBA', 
                (self.width, self.height), 
                self.background_color)
        
        # Desenha a caixa de fundo usando paste com máscara alpha
        frame.paste(bg_box, self.position, mask=bg_box)
        
        # Cria novo draw object para o texto
        draw = ImageDraw.Draw(frame)
        
        # Desenha as linhas de texto
        y_offset = self.position[1] + 5
        line_height = self.font_size + 2
        max_width = self.width - 10  # Margem de 5 pixels em cada lado
        
        def get_text_width(text):
            """Helper to get text width"""
            try:
                bbox = draw.textbbox((0, 0), text, font=self.font)
                return bbox[2] - bbox[0]
            except Exception:
                return len(text) * self.font_size * 0.6
        
        def wrap_text(text):
            """Word wrap text to fit within max_width"""
            if get_text_width(text) <= max_width:
                return [text]
            
            wrapped = []
            current_line = ""
            
            for word in text.split():
                test_line = current_line + (" " if current_line else "") + word
                if get_text_width(test_line) <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        wrapped.append(current_line)
                    # Try single word that's too wide
                    if get_text_width(word) > max_width:
                        # Force break the long word
                        chars = []
                        for char in word:
                            test = "".join(chars) + char
                            if get_text_width(test) > max_width:
                                wrapped.append("".join(chars))
                                chars = [char]
                            else:
                                chars.append(char)
                        current_line = "".join(chars)
                    else:
                        current_line = word
            
            if current_line:
                wrapped.append(current_line)
            
            return wrapped if wrapped else [text]
        
        for line in self._content:
            if self.breakline:
                # Quebra a linha para caber
                wrapped_lines = wrap_text(line)
                for wrapped_line in wrapped_lines:
                    if y_offset > self.position[1] + self.height - line_height:
                        break
                    draw.text((self.position[0] + 5, y_offset), wrapped_line, font=self.font, fill=self.text_color)
                    y_offset += line_height
            else:
                # Trunca com "..." (comportamento original)
                text_width = get_text_width(line)
                
                # Truncate if text exceeds box width
                if text_width > max_width:
                    # Binary search-like approach to find max chars that fit
                    for i in range(len(line), 0, -1):
                        truncated = line[:i]
                        if get_text_width(truncated + "...") <= max_width:
                            line = truncated + "..."
                            break
                # else: line stays as-is (no truncation needed)
                
                draw.text((self.position[0] + 5, y_offset), line, font=self.font, fill=self.text_color)
                y_offset += line_height
            
            # Para se passar da altura máxima
            if y_offset > self.position[1] + self.height - line_height:
                break
        
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
