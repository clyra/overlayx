#!/usr/bin/env python3
"""
OverlayX - Câmera Virtual com Suporte a Plugins
=====================================================
Um programa para criar overlays em tempo real sobre stream de webcam.
Suporta plugins, configuração via arquivo YAML e teclas de atalho.

Uso:
    python overlayx.py [--config <arquivo_config>]
"""

import pyvirtualcam
import cv2
import numpy as np
import psutil
import time
import os
import sys
import threading
from PIL import Image, ImageDraw, ImageFont, ImageOps
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import yaml

# Importa plugins da pasta plugins
from plugins import Plugin, ClockPlugin, CPUPlugin, OverlayPlugin, CropPlugin, TLPPlugin, TailPlugin, BackgroundPlugin

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

@dataclass
class AppConfig:
    """Classe de configuração global da aplicação"""
    width: int = 1280
    height: int = 720
    fps: int = 30
    device: int = 0
    # Modo de redimensionamento: True = dimensiona para preencher (fit), False = crop (padrão)
    fit: bool = False
    
    # Assets disponíveis (fonts, etc)
    assets: Dict[str, Any] = field(default_factory=lambda: {
        'fonts': []
    })
    
    # Nova propriedade para instâncias de plugins
    plugin_instances: List[Dict[str, Any]] = field(default_factory=list)
    
    keyboard_shortcuts: Dict[str, str] = field(default_factory=lambda: {
        'quit': 'q',
        'pause': ' ',
        'next_filter': 'n',
        'prev_filter': 'b'
    })
    
    @classmethod
    def from_yaml(cls, filepath: str) -> 'AppConfig':
        """Carrega configuração de arquivo YAML"""
        if not os.path.exists(filepath):
            return cls()
        
        # Determina o tipo pelo extensão
        ext = os.path.splitext(filepath)[1].lower()
        
        with open(filepath, 'r') as f:
            if ext in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            else:
                # Tenta YAML como fallback
                f.seek(0)
                try:
                    data = yaml.safe_load(f)
                except:
                    data = {}
        
        if not data:
            return cls()
        
        return cls._parse_config(data)
    
    @classmethod
    def _parse_config(cls, data: dict) -> 'AppConfig':
        """Parse configuration from dictionary"""
        config = cls()
        
        # Camera settings
        if 'camera' in data:
            config.width = data['camera'].get('width', config.width)
            config.height = data['camera'].get('height', config.height)
            config.fps = data['camera'].get('fps', config.fps)
            config.device = data['camera'].get('device', config.device)
            config.fit = data['camera'].get('fit', config.fit)
        
        # Assets (fonts, etc)
        if 'assets' in data:
            config.assets = data['assets']
        
        # Keyboard shortcuts
        if 'keyboard_shortcuts' in data:
            config.keyboard_shortcuts = data['keyboard_shortcuts']
        
        # Parse plugin instances configuration
        config.plugin_instances = cls._parse_plugin_instances(data)
        
        return config
    
    @classmethod
    def _parse_plugin_instances(cls, data: dict) -> List[Dict[str, Any]]:
        """
        Parse plugin instances configuration.
        
        New unified format:
          plugins:
            - name: "clock_main"    # ID único do plugin
              type: "clock"        # Tipo do plugin (classe a ser instanciada)
              enabled: true         # Ativado (opcional, padrão true)
              # Opções específicas do plugin:
              position: [1080, 20]
              format: "%H:%M:%S"
        """
        instances = []
        
        plugins_data = data.get('plugins', {})
        
        # Novo formato: lista direta de plugins
        if isinstance(plugins_data, list):
            for plugin_def in plugins_data:
                plugin_type = plugin_def.get('type')
                if not plugin_type:
                    print(f"Aviso: Plugin sem 'type' especificado: {plugin_def}")
                    continue
                
                # O 'name' é o ID único, se não especificado usa o type como ID
                plugin_id = plugin_def.get('name', plugin_type)
                
                # Extrai opções específicas do plugin (remove campos reserved)
                plugin_config = {k: v for k, v in plugin_def.items() 
                                 if k not in ('name', 'type', 'enabled')}
                
                instances.append({
                    'type': plugin_type,   # tipo do plugin (para encontrar a classe)
                    'id': plugin_id,       # ID único da instância
                    'enabled': plugin_def.get('enabled', True),
                    'config': plugin_config
                })
        
        return instances


# ============================================================================
# SISTEMA DE PLUGINS (importados de plugins/)
# ============================================================================

# As classes de plugins foram movidas para a pasta plugins/
# - plugins/base.py: Classe base Plugin
# - plugins/clock.py: ClockPlugin
# - plugins/cpu.py: CPUPlugin
# - plugins/overlay.py: OverlayPlugin
# - plugins/crop.py: CropPlugin


# ============================================================================
# GERENCIADOR DE PLUGINS
# ============================================================================

class PluginManager:
    """Gerencia todos os plugins carregados"""
    
    # Mapeamento de nomes de plugins para classes
    PLUGIN_CLASSES = {
        'clock': ClockPlugin,
        'cpu': CPUPlugin,
        'overlay': OverlayPlugin,
        'crop': CropPlugin,
        'tlp': TLPPlugin,
        'tail': TailPlugin,
        'background': BackgroundPlugin,
    }
    
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        self.plugins: Dict[str, Plugin] = {}
        self._crop_plugin_name: Optional[str] = None
        self._delta_time: float = 1.0 / app_config.fps
    
    def register_plugin(self, plugin: Plugin, instance_id: str = None):
        """Registra um plugin com um ID único"""
        if instance_id is None:
            instance_id = plugin.name

        original_id = instance_id
        counter = 1
        while instance_id in self.plugins:
            instance_id = f"{original_id}_{counter}"
            counter += 1

        self.plugins[instance_id] = plugin
        if plugin.name == 'crop':
            self._crop_plugin_name = instance_id
        print(f"Plugin registrado: {plugin.name} (ID: {instance_id})")
    
    def initialize_plugins(self) -> bool:
        """Inicializa todos os plugins baseados na configuração"""
        for instance_config in self.app_config.plugin_instances:
            plugin_type = instance_config.get('type')  # tipo do plugin (para encontrar a classe)
            instance_id = instance_config.get('id')  # ID único da instância
            enabled = instance_config.get('enabled', True)
            plugin_config = instance_config.get('config', {})
            
            # Verifica se o plugin existe (procura pelo tipo)
            if plugin_type not in self.PLUGIN_CLASSES:
                print(f"Aviso: Plugin tipo '{plugin_type}' não encontrado, ignorando.")
                continue
            
            # Cria a instância do plugin
            plugin_class = self.PLUGIN_CLASSES[plugin_type]
            plugin = plugin_class(config=plugin_config)
            plugin.enabled = enabled
            
            # Inicializa o plugin
            try:
                plugin.initialize(self.app_config)
                self.register_plugin(plugin, instance_id)
            except Exception as e:
                print(f"Erro ao inicializar plugin {plugin_type} (ID: {instance_id}): {e}")
                return False
        
        return True

    def process_frame(self, frame: Image.Image) -> Image.Image:
        """Processa um frame através de todos os plugins"""
        if self._crop_plugin_name:
            frame = self.plugins[self._crop_plugin_name].process_frame(frame, None)

        for name, plugin in self.plugins.items():
            if name == self._crop_plugin_name or not plugin.enabled:
                continue
            plugin.update(self._delta_time)
            draw = ImageDraw.Draw(frame)
            frame = plugin.process_frame(frame, draw)

        return frame
    
    def on_keypress(self, key: str) -> bool:
        """Propaga eventos de teclado para plugins"""
        for plugin in self.plugins.values():
            plugin.on_keypress(key)

        if key == self.app_config.keyboard_shortcuts.get('quit', 'q'):
            return 'quit'

        return False
    
    def cleanup(self):
        """Limpa todos os plugins"""
        for plugin in self.plugins.values():
            plugin.cleanup()


# ============================================================================
# GERENCIADOR DE ENTRADA DE TECLADO
# ============================================================================

class KeyboardHandler:
    """Gerencia entrada de teclado de forma não-bloqueante"""
    
    def __init__(self):
        self.key_queue = []
        self.lock = threading.Lock()
    
    def start(self):
        """Inicia o listener de teclado em thread separada (só funciona com TTY)."""
        if not sys.stdin.isatty():
            return
        self.running = True
        self.thread = threading.Thread(target=self._keyboard_listener, daemon=True)
        self.thread.start()
    
    def _keyboard_listener(self):
        """Thread que escuta o teclado"""
        import tty
        import termios
        
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        
        try:
            tty.setcbreak(fd)
            while self.running:
                try:
                    ch = sys.stdin.read(1)
                    if ch:
                        with self.lock:
                            self.key_queue.append(ch)
                except:
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    
    def get_key(self) -> Optional[str]:
        """Retorna a próxima tecla pressionada (não-bloqueante)"""
        with self.lock:
            if self.key_queue:
                return self.key_queue.pop(0)
        return None
    
    def stop(self):
        """Para o listener"""
        self.running = False


# ============================================================================
# CLASSE PRINCIPAL
# ============================================================================

class OverlayX:
    """Classe principal da aplicação"""
    
    def __init__(self, config_file: str = "config.yaml"):
        self.config = AppConfig.from_yaml(config_file)
        self.plugin_manager = PluginManager(self.config)
        self.keyboard_handler = KeyboardHandler()
        self.paused = False
        self.running = False
    
    def initialize(self) -> bool:
        """Inicializa a aplicação"""
        print("=" * 50)
        print("OverlayX - Câmera Virtual com Plugins")
        print("=" * 50)
        
        # Inicializa plugins
        if not self.plugin_manager.initialize_plugins():
            print("Erro ao inicializar plugins")
            return False
        
        # Inicia teclado
        self.keyboard_handler.start()
        
        self.running = True
        return True
    
    def run(self):
        """Executa o loop principal (CLI)."""
        if not self.initialize():
            return
        self._run_loop()

    def _run_loop(self):
        """Loop de captura e processamento. Chamar após initialize()."""
        target_size = (self.config.width, self.config.height)

        print(f"\nCâmera Virtual iniciada ({target_size[0]}x{target_size[1]} @ {self.config.fps}fps)")
        print("Pressione Ctrl+C para parar.\n")

        cap = cv2.VideoCapture(self.config.device)

        if not cap.isOpened():
            print("Erro: Não foi possível abrir a câmera")
            return

        try:
            with pyvirtualcam.Camera(
                width=target_size[0],
                height=target_size[1],
                fps=self.config.fps
            ) as cam:
                while self.running:
                    key = self.keyboard_handler.get_key()
                    if key:
                        result = self.plugin_manager.on_keypress(key)
                        if result == 'quit':
                            break
                        if key == self.config.keyboard_shortcuts.get('pause', ' '):
                            self.paused = not self.paused
                            print(f"{'Pausado' if self.paused else 'Retomado'}")

                    if self.paused:
                        time.sleep(0.1)
                        continue

                    ret, frame = cap.read()
                    if not ret:
                        print("Erro ao capturar frame")
                        break

                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame_rgb)

                    if self.config.fit:
                        img = ImageOps.fit(img, target_size, Image.Resampling.LANCZOS)
                    else:
                        if img.width > target_size[0] or img.height > target_size[1]:
                            img = ImageOps.fit(img, target_size, Image.Resampling.LANCZOS)

                    img = self.plugin_manager.process_frame(img)

                    if img.size != target_size:
                        img = img.resize(target_size, Image.Resampling.LANCZOS)

                    if img.mode == 'RGBA':
                        background = Image.new('RGB', img.size, (0, 0, 0))
                        background.paste(img, mask=img.split()[3])
                        img = background

                    cam.send(np.array(img))
                    cam.sleep_until_next_frame()

        except KeyboardInterrupt:
            print("\nEncerrando...")
        finally:
            cap.release()
            self.cleanup()
    
    def cleanup(self):
        """Limpa recursos"""
        self.running = False
        self.keyboard_handler.stop()
        self.plugin_manager.cleanup()
        print("Recursos limpos. Até mais!")


# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='OverlayX - Câmera Virtual com Suporte a Plugins'
    )
    parser.add_argument(
        '-c', '--config',
        default='config.yaml',
        help='Arquivo de configuração (padrão: config.yaml)'
    )
    
    args = parser.parse_args()
    
    # Executa aplicação
    app = OverlayX(config_file=args.config)
    app.run()


if __name__ == "__main__":
    main()
