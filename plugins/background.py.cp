# -*- coding: utf-8 -*-
"""
OverlayX - Background Plugin
=============================
Plugin que utiliza MediaPipe para segmentação de pessoa e aplica
efeitos no fundo da imagem (blur ou imagem de background).

Usa o modelo selfie_segmentation_landscape.tflite do MediaPipe 0.10.x.

Opções de configuração:
- mode: "blur" ou "image" (padrão: "blur")
- blur_radius: raio do blur (padrão: 21)
- background_image: caminho para imagem de fundo (usado quando mode="image")

Autor: OverlayX
"""

import os
import numpy as np
from typing import Optional, Dict, Any
from PIL import Image, ImageFilter  # Removed unused ImageDraw

from .base import Plugin

# Tenta importar mediapipe 0.10.x
try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    print("Aviso: MediaPipe não disponível. Plugin background desabilitado.")


class BackgroundPlugin(Plugin):
    """Plugin que aplica blur ou imagem no fundo usando segmentação MediaPipe"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("background", config)
        self.mode = "blur"  # "blur" ou "image"
        self.blur_radius = 21
        self.blur_step = 3  # Step for increasing/decreasing blur
        self.min_blur_radius = 1
        self.max_blur_radius = 50
        self.background_image_path = None
        self.background_image = None
        self.segmenter = None
        self.frame_count = 0
        self.skip_frames = 0  # Processa a cada N frames (0 = todos)
        self._model_loaded = False
    
    def initialize(self, app_config) -> bool:
        super().initialize(app_config)
        
        if not MEDIAPIPE_AVAILABLE:
            print("Erro: MediaPipe não está instalado")
            return False
        
        # Configurações do plugin
        self.mode = self.config.get('mode', 'blur')
        self.blur_radius = self.config.get('blur_radius', 21)
        self.blur_step = self.config.get('blur_step', 3)
        self.min_blur_radius = self.config.get('min_blur_radius', 1)
        self.max_blur_radius = self.config.get('max_blur_radius', 50)
        self.background_image_path = self.config.get('background_image', None)
        self.skip_frames = self.config.get('skip_frames', 0)
        
        # Valida modo
        if self.mode not in ('blur', 'image'):
            print(f"Aviso: Modo '{self.mode}' desconhecido, usando 'blur'")
            self.mode = 'blur'
        
        # Carrega imagem de background se necessário
        if self.mode == 'image' and self.background_image_path:
            if os.path.exists(self.background_image_path):
                self.background_image = Image.open(self.background_image_path).convert('RGB')
                print(f"Imagem de background carregada: {self.background_image_path}")
            else:
                print(f"Aviso: Imagem de background não encontrada: {self.background_image_path}")
                self.mode = 'blur'  # Fallback para blur
        
        # Localiza o modelo TFLite
        model_path = self._find_model()
        if not model_path:
            print("Erro: Modelo selfie_segmentation_landscape.tflite não encontrado")
            return False
        
        # Inicializa o segmentador do MediaPipe 0.10.x
        try:
            # Configuração do segmentador
            base_options = python.BaseOptions(model_asset_path=model_path)
            options = vision.ImageSegmenterOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.IMAGE,
                output_category_mask=False  # Retorna masks de probabilidade
            )
            self.segmenter = vision.ImageSegmenter.create_from_options(options)
            self._model_loaded = True
            print(f"Segmentador MediaPipe carregado: {model_path}")
        except Exception as e:
            print(f"Erro ao carregar segmentador: {e}")
            return False
        
        return True
    
    def _find_model(self) -> Optional[str]:
        """Encontra o modelo TFLite na pasta atual ou em locais comuns"""
        # Lista de locais para procurar
        search_paths = [
            'selfie_segmentation_landscape.tflite',
            os.path.join(os.path.dirname(__file__), '..', 'selfie_segmentation_landscape.tflite'),
            os.path.join(os.getcwd(), 'selfie_segmentation_landscape.tflite'),
        ]
        
        for path in search_paths:
            full_path = os.path.abspath(path)
            if os.path.exists(full_path):
                return full_path
        
        return None
    
    def _apply_blur_background(self, frame: Image.Image, mask: Image.Image) -> Image.Image:
        """Aplica blur no fundo da imagem"""
        # Cria versão borrada da imagem inteira
        blurred = frame.filter(ImageFilter.GaussianBlur(radius=self.blur_radius))
        
        # Converte mask para numpy para manipulação
        mask_array = np.array(mask).astype(np.float32) / 255.0
        
        # Expande dimensões para broadcast
        if len(mask_array.shape) == 2:
            mask_array = np.expand_dims(mask_array, axis=-1)
        
        # Converte imagens para arrays numpy
        frame_array = np.array(frame).astype(np.float32)
        blurred_array = np.array(blurred).astype(np.float32)
        
        # Aplica a máscara: pessoa = original, fundo = blur
        # mask = 1 (pessoa), mask = 0 (fundo)
        result = frame_array * mask_array + blurred_array * (1 - mask_array)
        
        return Image.fromarray(result.astype(np.uint8))
    
    def _apply_image_background(self, frame: Image.Image, mask: Image.Image, target_size: tuple) -> Image.Image:
        """Aplica imagem de background"""
        # Redimensiona a imagem de background para o tamanho do frame
        bg = self.background_image.copy()
        bg = bg.resize(target_size, Image.Resampling.LANCZOS)
        
        # Converte mask para numpy
        mask_array = np.array(mask).astype(np.float32) / 255.0
        
        # Expande dimensões para broadcast
        if len(mask_array.shape) == 2:
            mask_array = np.expand_dims(mask_array, axis=-1)
        
        # Converte imagens para arrays numpy
        frame_array = np.array(frame).astype(np.float32)
        bg_array = np.array(bg).astype(np.float32)
        
        # Garante que têm o mesmo shape
        if frame_array.shape != bg_array.shape:
            bg_array = np.array(bg.resize((frame.width, frame.height))).astype(np.float32)
        
        # Aplica a máscara: pessoa = original, fundo = imagem
        result = frame_array * mask_array + bg_array * (1 - mask_array)
        
        return Image.fromarray(result.astype(np.uint8))
    
    def process_frame(self, frame: Image.Image, draw) -> Image.Image:
        """
        Versão "PRO" do background:
        - threshold configurável (recorte mais/menos agressivo)
        - suavização da máscara (reduz serrilhado)
        - feather (borda mais natural)
        - pequena limpeza morfológica (tira ruído pontual)
        - opcional: modo VIDEO (se você inicializar o segmenter em RunningMode.VIDEO)

        Config (self.config):
        threshold: float (0..1)         -> padrão 0.60
        mask_blur: int                  -> padrão 3 (Gaussian blur no mask)
        feather: int                    -> padrão 4 (blur extra para bordas)
        morph_open: bool                -> padrão True (remove pontos pequenos)
        morph_close: bool               -> padrão True (fecha buracos pequenos)
        morph_kernel: int               -> padrão 3 (tamanho do kernel)
        invert_mask: bool               -> padrão False (inverte se estiver pegando classe errada)
        video_mode: bool                -> padrão False (usa segment_for_video com timestamp)
        """
        if not self.enabled or not self._model_loaded:
            return frame

        self.frame_count += 1

        # Processa 1 frame a cada (skip_frames+1)
        if self.skip_frames > 0 and self.frame_count % (self.skip_frames + 1) != 1:
            return frame

        # Configs "PRO"
        threshold = float(self.config.get("threshold", 0.60))
        mask_blur = int(self.config.get("mask_blur", 3))
        feather = int(self.config.get("feather", 4))
        morph_open = bool(self.config.get("morph_open", True))
        morph_close = bool(self.config.get("morph_close", True))
        morph_kernel = int(self.config.get("morph_kernel", 3))
        invert_mask = bool(self.config.get("invert_mask", False))
        video_mode = bool(self.config.get("video_mode", False))

        target_size = frame.size

        try:
            # Frame em RGB
            frame_rgb = frame.convert("RGB") if frame.mode != "RGB" else frame

            # MediaPipe Image
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.array(frame_rgb))

            # Segmentação
            if video_mode and hasattr(self.segmenter, "segment_for_video"):
                # timestamp em ms (monótono o suficiente para VIDEO mode)
                timestamp_ms = int(self.frame_count * (1000 / 30))  # assume 30fps; se souber o fps real, use ele
                segmentation_result = self.segmenter.segment_for_video(mp_image, timestamp_ms)
            else:
                segmentation_result = self.segmenter.segment(mp_image)

            # Pega a máscara: preferir confidence_masks; em binário, geralmente:
            # masks[0]=background, masks[1]=person
            if hasattr(segmentation_result, "confidence_masks") and segmentation_result.confidence_masks:
                masks = segmentation_result.confidence_masks
                category_mask = masks[1] if len(masks) > 1 else masks[0]
            elif hasattr(segmentation_result, "category_mask"):
                category_mask = segmentation_result.category_mask
            else:
                return frame

            # Extrai numpy
            if hasattr(category_mask, "numpy_view"):
                mask_array = category_mask.numpy_view()
            else:
                mask_array = np.asarray(category_mask)

            mask_array = np.asarray(mask_array)

            # Garante numérico
            if not np.issubdtype(mask_array.dtype, np.number):
                raise TypeError(f"Mask inválida: dtype={mask_array.dtype}, type={type(category_mask)}")

            # Normaliza para float [0..1] (confidence)
            # Se vier uint8 (0..255), reescala.
            if mask_array.dtype == np.uint8:
                mask_f = mask_array.astype(np.float32) / 255.0
            else:
                mask_f = mask_array.astype(np.float32)

            # Se vier (H,W,1), achata
            if mask_f.ndim == 3 and mask_f.shape[-1] == 1:
                mask_f = mask_f[:, :, 0]
            elif mask_f.ndim != 2:
                mask_f = np.squeeze(mask_f)
                if mask_f.ndim != 2:
                    raise TypeError(f"Máscara com shape inesperado: {mask_f.shape}")

            # (Opcional) Inverter se a classe estiver trocada
            if invert_mask:
                mask_f = 1.0 - mask_f

            # Threshold -> máscara binária
            mask_bin = (mask_f >= threshold).astype(np.uint8) * 255  # 0 ou 255

            # Morfologia (limpeza de ruído / buracos)
            # (sem OpenCV; usando PIL em modo L)
            mask_img = Image.fromarray(mask_bin, mode="L")

            if morph_open or morph_close:
                # Kernel simples via Min/Max filter (aproxima erosão/dilatação)
                # kernel deve ser ímpar e >= 3
                k = max(3, morph_kernel | 1)

                if morph_open:
                    # erosão -> dilatação
                    mask_img = mask_img.filter(ImageFilter.MinFilter(size=k))
                    mask_img = mask_img.filter(ImageFilter.MaxFilter(size=k))

                if morph_close:
                    # dilatação -> erosão
                    mask_img = mask_img.filter(ImageFilter.MaxFilter(size=k))
                    mask_img = mask_img.filter(ImageFilter.MinFilter(size=k))

            # Suavização/feather para bordas mais naturais
            if mask_blur > 0:
                mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=mask_blur))
            if feather > 0:
                mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=feather))

            # Redimensiona para o frame (se necessário)
            mask_img = mask_img.resize(target_size, Image.Resampling.BILINEAR)

            # Aplica efeito
            if self.mode == "blur":
                return self._apply_blur_background(frame, mask_img)
            elif self.mode == "image":
                return self._apply_image_background(frame, mask_img, target_size)

        except Exception as e:
            print(f"Erro na segmentação: {e}")

        return frame


    def process_frame2(self, frame: Image.Image, draw) -> Image.Image:
        if not self.enabled or not self._model_loaded:
            return frame

        self.frame_count += 1

        # processa 1 frame a cada (skip_frames+1)
        if self.skip_frames > 0 and self.frame_count % (self.skip_frames + 1) != 1:
            return frame

        target_size = frame.size

        try:
            frame_rgb = frame.convert("RGB") if frame.mode != "RGB" else frame
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.array(frame_rgb))

            segmentation_result = self.segmenter.segment(mp_image)

            # Preferir confidence masks (probabilidade). Em modelos binários, geralmente:
            # masks[0] = background, masks[1] = person
            if hasattr(segmentation_result, "confidence_masks") and segmentation_result.confidence_masks:
                masks = segmentation_result.confidence_masks
                category_mask = masks[1] if len(masks) > 1 else masks[0]
            elif hasattr(segmentation_result, "category_mask"):
                category_mask = segmentation_result.category_mask
            else:
                return frame

            if hasattr(category_mask, "numpy_view"):
                mask_array = category_mask.numpy_view()
            else:
                mask_array = np.asarray(category_mask)

            mask_array = np.asarray(mask_array)
            if not np.issubdtype(mask_array.dtype, np.number):
                raise TypeError(f"Mask inválida: dtype={mask_array.dtype}, type={type(category_mask)}")

            # normaliza para uint8 (0..255)
            if mask_array.dtype == np.uint8 and mask_array.max() > 1:
                mask_u8 = mask_array
            else:
                mask_u8 = np.clip(mask_array * 255.0, 0, 255).astype(np.uint8)

            # Pillow quer (H,W) para 'L'
            if mask_u8.ndim == 3 and mask_u8.shape[-1] == 1:
                mask_u8 = mask_u8[:, :, 0]
            elif mask_u8.ndim != 2:
                mask_u8 = np.squeeze(mask_u8)
                if mask_u8.ndim != 2:
                    raise TypeError(f"Máscara com shape inesperado: {mask_u8.shape}")

            mask_image = Image.fromarray(mask_u8, mode="L").resize(target_size, Image.Resampling.BILINEAR)

            if self.mode == "blur":
                return self._apply_blur_background(frame, mask_image)
            elif self.mode == "image":
                return self._apply_image_background(frame, mask_image, target_size)

        except Exception as e:
            print(f"Erro na segmentação: {e}")

        return frame
        
    def cleanup(self):
        """Limpa recursos do plugin"""
        if self.segmenter:
            # No MediaPipe 0.10.x, o segmentador não tem método close()
            self.segmenter = None
        self._model_loaded = False
    
    def get_info(self) -> Dict[str, Any]:
        """Retorna informações do plugin"""
        info = super().get_info()
        info.update({
            'mode': self.mode,
            'blur_radius': self.blur_radius,
            'blur_step': self.blur_step,
            'min_blur_radius': self.min_blur_radius,
            'max_blur_radius': self.max_blur_radius,
            'background_image': self.background_image_path,
            'model_loaded': self._model_loaded,
            'frame_count': self.frame_count
        })
        return info
    
    def handle_shortcut(self, action: str) -> bool:
        """Manipula atalhos específicos do plugin background"""
        if action == 'toggle':
            self.enabled = not self.enabled
            return True
        elif action == 'increase_blur':
            if self.blur_radius < self.max_blur_radius:
                self.blur_radius = min(self.blur_radius + self.blur_step, self.max_blur_radius)
                print(f"Blur radius aumentado para: {self.blur_radius}")
                return True
        elif action == 'decrease_blur':
            if self.blur_radius > self.min_blur_radius:
                self.blur_radius = max(self.blur_radius - self.blur_step, self.min_blur_radius)
                print(f"Blur radius diminuído para: {self.blur_radius}")
                return True
        elif action == 'toggle_mode':
            # Alterna entre modo blur e modo image
            if self.mode == 'blur':
                # Tenta carregar a imagem se ainda não foi carregada
                if not self.background_image and self.background_image_path:
                    if os.path.exists(self.background_image_path):
                        self.background_image = Image.open(self.background_image_path).convert('RGB')
                        print(f"Imagem de background carregada: {self.background_image_path}")
                    else:
                        print(f"Aviso: Imagem de background não encontrada: {self.background_image_path}")
                        
                if self.background_image:
                    self.mode = 'image'
                    print("Modo alterado para: image (background personalizado)")
                elif self.background_image_path:
                    print("Aviso: background_image não encontrado. Mantendo modo blur.")
                else:
                    print("Aviso: background_image não configurado. Mantendo modo blur.")
            else:
                self.mode = 'blur'
                print("Modo alterado para: blur")
            return True
        return False
