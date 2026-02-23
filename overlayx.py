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
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from abc import ABC
import yaml
import json

# Importa plugins da pasta plugins
from plugins import Plugin, ClockPlugin, CPUPlugin, OverlayPlugin, CropPlugin, TLPPlugin

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
    
    # Propriedade para armazenar config de plugins (modo legado)
    plugins: Dict[str, Any] = field(default_factory=dict)
    
    keyboard_shortcuts: Dict[str, str] = field(default_factory=lambda: {
        'quit': 'q',
        'pause': ' ',
        'next_filter': 'n',
        'prev_filter': 'b'
    })
    
    @classmethod
    def from_yaml(cls, filepath: str) -> 'AppConfig':
        """Carrega configuração de arquivo JSON ou YAML"""
        if not os.path.exists(filepath):
            return cls()
        
        # Determina o tipo pelo extensão
        ext = os.path.splitext(filepath)[1].lower()
        
        with open(filepath, 'r') as f:
            if ext in ['.yaml', '.yml']:
                try:
                    data = yaml.safe_load(f)
                except (NameError, ModuleNotFoundError, ImportError):
                    # YAML não disponível, tenta JSON
                    data = json.load(f)
            elif ext == '.json':
                data = json.load(f)
            else:
                # Tenta primeiro JSON, depois YAML
                f.seek(0)
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
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
        
        # Store full plugins data for legacy access
        config.plugins = data.get('plugins', {})
        
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
    }
    
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        self.plugins: Dict[str, Plugin] = {}
        self.filter_plugins: List[Plugin] = []
        self.current_filter_index = 0
    
    def register_plugin(self, plugin: Plugin, instance_id: str = None):
        """Registra um plugin com um ID único"""
        if instance_id is None:
            instance_id = plugin.name
        
        # Gera ID único se já existir
        original_id = instance_id
        counter = 1
        while instance_id in self.plugins:
            instance_id = f"{original_id}_{counter}"
            counter += 1
        
        self.plugins[instance_id] = plugin
        print(f"Plugin registrado: {plugin.name} (ID: {instance_id})")
    
    def register_filter(self, plugin: Plugin):
        """Registra um plugin como filtro"""
        self.filter_plugins.append(plugin)
    
    def initialize_plugins(self) -> bool:
        """Inicializa todos os plugins baseados na configuração"""
        
        # Primeiro, registra todas as classes de plugins disponíveis
        for name, plugin_class in self.PLUGIN_CLASSES.items():
            # Não instanciamos aqui, apenas garantimos que estão disponíveis
            pass
        
        # Agora cria instâncias baseadas na configuração
        plugin_instances = getattr(self.app_config, 'plugin_instances', [])
        
        # Se não há instâncias configuradas, usa modo legado (compatibilidade)
        if not plugin_instances:
            # Fallback para o comportamento antigo
            self._initialize_legacy_plugins()
            return True
        
        # Cria instâncias de plugins baseadas na configuração
        for instance_config in plugin_instances:
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
    
    def _initialize_legacy_plugins(self):
        """Inicializa plugins no modo legado (compatibilidade)"""
        # Get plugin configs from legacy format (plugins.config in YAML)
        plugins_data = getattr(self.app_config, 'plugins', {})
        plugin_configs = plugins_data.get('config', {})
        
        # Plugins padrão
        # Nota: CropPlugin foi removido do modo legado pois causava problemas de dimensão
        # (ImageOps.fit com aspect ratios diferentes). Ainda está disponível via
        # sistema de instâncias para quem precisar de crop inteligente.
        # Suporta ambos os formatos: 'frame' (legado) e 'overlay' (novo)
        overlay_config = plugin_configs.get('frame', {}) or plugin_configs.get('overlay', {})
        self.register_plugin(ClockPlugin(config=plugin_configs.get('clock', {})))
        self.register_plugin(CPUPlugin(config=plugin_configs.get('cpu', {})))
        self.register_plugin(OverlayPlugin(config=overlay_config))
        
        # Inicializa plugins
        for name, plugin in self.plugins.items():
            try:
                plugin.initialize(self.app_config)
            except Exception as e:
                print(f"Erro ao inicializar plugin {name}: {e}")
    
    def process_frame(self, frame: Image.Image) -> Image.Image:
        """Processa um frame através de todos os plugins"""
        # Procura por plugin de crop
        crop_plugin = None
        crop_plugin_name = None
        for name, plugin in self.plugins.items():
            if plugin.name == 'crop':
                crop_plugin = plugin
                crop_plugin_name = name
                break
        
        # Primeiro aplica crop/transformações
        if crop_plugin:
            frame = crop_plugin.process_frame(frame, None)
        
        # Cria objeto draw para plugins que precisam
        draw = ImageDraw.Draw(frame)
        
        # Aplica plugins na ordem (exceto crop que já foi)
        for name, plugin in self.plugins.items():
            if name == crop_plugin_name or not plugin.enabled:
                continue
            frame = plugin.process_frame(frame, draw)
        
        return frame
    
    def on_keypress(self, key: str) -> bool:
        """Propaga eventos de teclado para plugins"""
        handled = False
        
        # Primeiro verifica plugins
        for plugin in self.plugins.values():
            if plugin.on_keypress(key):
                handled = True
        
        # Atalhos globais
        if key == self.app_config.keyboard_shortcuts.get('quit', 'q'):
            return 'quit'
        
        if key == self.app_config.keyboard_shortcuts.get('next_filter', 'n'):
            if self.filter_plugins:
                self.current_filter_index = (self.current_filter_index + 1) % len(self.filter_plugins)
                handled = True
        
        if key == self.app_config.keyboard_shortcuts.get('prev_filter', 'b'):
            if self.filter_plugins:
                self.current_filter_index = (self.current_filter_index - 1) % len(self.filter_plugins)
                handled = True
        
        return handled
    
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
        """Inicia o listener de teclado em thread separada"""
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
        """Executa o loop principal"""
        if not self.initialize():
            return
        
        target_size = (self.config.width, self.config.height)
        
        print(f"\nCâmera Virtual iniciada ({target_size[0]}x{target_size[1]} @ {self.config.fps}fps)")
        print("Pressione as teclas de atalho (veja config.yaml)")
        print("Pressione Ctrl+C para parar.\n")
        
        # Inicia captura
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
                    # Verifica teclas
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
                    
                    # Captura frame
                    ret, frame = cap.read()
                    if not ret:
                        print("Erro ao capturar frame")
                        break
                    
                    # Converte BGR -> RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame_rgb)
                    
                    # Aplica modo de redimensionamento baseado na configuração 'fit'
                    target_size = (self.config.width, self.config.height)
                    if self.config.fit:
                        # fit=True: dimensiona a imagem para preencher completamente a saída
                        # (mantém aspect ratio, pode adicionar letterbox/pillarbox)
                        img = ImageOps.fit(img, target_size, Image.Resampling.LANCZOS)
                    else:
                        # fit=False (padrão): 
                        # - Se a imagem da webcam for maior que a saída: faz crop do centro
                        # - Se a imagem da webcam for menor ou igual: mantém o tamanho original
                        if img.width > target_size[0] or img.height > target_size[1]:
                            # Faz crop do centro para caber na resolução de saída
                            img = ImageOps.fit(img, target_size, Image.Resampling.LANCZOS)
                        # Caso contrário, mantém o tamanho original da webcam
                    
                    # Processa através dos plugins
                    # (plugins que precisam de tamanho específico podem redimensionar internamente)
                    img = self.plugin_manager.process_frame(img)
                    
                    # Garante que o frame final tem o tamanho correto para a câmera virtual
                    if img.size != target_size:
                        img = img.resize(target_size, Image.Resampling.LANCZOS)
                    
                    # Envia para câmera virtual
                    final_frame = np.array(img)
                    cam.send(final_frame)
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
