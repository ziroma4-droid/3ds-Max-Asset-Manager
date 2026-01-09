"""
Парсер .max файлов для извлечения путей к ассетам через OLE
Улучшенная версия с лучшим поиском путей
"""

import olefile
import re
import os
import struct
from pathlib import Path
from typing import Set, Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class SceneAssets:
    """Контейнер для ассетов сцены"""
    scene_path: Path
    textures: Set[str] = field(default_factory=set)
    proxies: Set[str] = field(default_factory=set)
    other_assets: Set[str] = field(default_factory=set)
    errors: List[str] = field(default_factory=list)
    debug_info: List[str] = field(default_factory=list)
    
    @property
    def all_assets(self) -> Set[str]:
        return self.textures | self.proxies | self.other_assets
    
    def get_existing_assets(self) -> Dict[str, List[Path]]:
        """Возвращает только существующие файлы"""
        result = {
            'textures': [],
            'proxies': [],
            'other': []
        }
        
        for tex in self.textures:
            path = Path(tex)
            if path.exists():
                result['textures'].append(path)
                
        for proxy in self.proxies:
            path = Path(proxy)
            if path.exists():
                result['proxies'].append(path)
                
        for other in self.other_assets:
            path = Path(other)
            if path.exists():
                result['other'].append(path)
                
        return result


class MaxFileParser:
    """Парсер .max файлов через OLE структуру"""
    
    # Расширения текстур
    TEXTURE_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.tga', '.tif', '.tiff', 
        '.bmp', '.gif', '.exr', '.hdr', '.psd', '.dds',
        '.tx', '.tex'
    }
    
    # Расширения прокси
    PROXY_EXTENSIONS = {
        '.vrmesh',  # V-Ray proxy
        '.vrmap',   # V-Ray proxy map
        '.vrscene', # V-Ray scene
        '.cgeo',    # Corona proxy
        '.abc',     # Alembic
        '.rs',      # Redshift proxy
        '.ass',     # Arnold proxy
        '.bgeo',    # Houdini geometry
        '.obj',     # OBJ (часто используется как прокси)
    }
    
    def __init__(self, debug: bool = False):
        self.debug = debug
    
    def parse_scene(self, max_file_path: str | Path) -> SceneAssets:
        """
        Парсит .max файл и извлекает все пути к ассетам
        """
        max_file_path = Path(max_file_path)
        assets = SceneAssets(scene_path=max_file_path)
        
        if not max_file_path.exists():
            assets.errors.append(f"Файл не найден: {max_file_path}")
            return assets
        
        if max_file_path.suffix.lower() != '.max':
            assets.errors.append(f"Неверный формат файла: {max_file_path}")
            return assets
        
        try:
            if not olefile.isOleFile(str(max_file_path)):
                assets.errors.append(f"Файл не является OLE: {max_file_path}")
                return assets
            
            with olefile.OleFileIO(str(max_file_path)) as ole:
                self._extract_from_ole(ole, assets)
                
        except Exception as e:
            assets.errors.append(f"Ошибка парсинга {max_file_path}: {str(e)}")
        
        # Резолвим относительные пути
        self._resolve_relative_paths(assets)
        
        # Очищаем невалидные пути
        self._clean_paths(assets)
        
        if self.debug:
            assets.debug_info.append(f"Найдено текстур: {len(assets.textures)}")
            assets.debug_info.append(f"Найдено прокси: {len(assets.proxies)}")
        
        return assets
    
    def _extract_from_ole(self, ole: olefile.OleFileIO, assets: SceneAssets):
        """Извлекает пути из OLE структуры"""
        
        if self.debug:
            assets.debug_info.append(f"OLE streams: {ole.listdir()}")
        
        # Объединяем все данные для поиска
        all_data = b''
        
        for stream_path in ole.listdir():
            try:
                stream_name = '/'.join(stream_path)
                data = ole.openstream(stream_path).read()
                all_data += data
                
                if self.debug:
                    assets.debug_info.append(f"Stream: {stream_name}, size: {len(data)}")
                    
            except Exception as e:
                if self.debug:
                    assets.debug_info.append(f"Error reading stream {stream_path}: {e}")
                continue
        
        # Извлекаем пути разными методами
        self._extract_ascii_paths(all_data, assets)
        self._extract_unicode_paths(all_data, assets)
        self._extract_by_extension(all_data, assets)
    
    def _extract_ascii_paths(self, data: bytes, assets: SceneAssets):
        """Извлекает ASCII пути"""
        
        # Паттерны для Windows путей
        patterns = [
            # Полный путь: C:\folder\file.ext
            rb'([A-Za-z]:[\\\/](?:[^\x00-\x1f\\/:*?"<>|]+[\\\/])*[^\x00-\x1f\\/:*?"<>|]+\.(?:jpg|jpeg|png|tga|tif|tiff|bmp|gif|exr|hdr|psd|dds|tx|tex|vrmesh|abc|rs|ass|bgeo|obj|ies|hdri))',
            # UNC путь: \\server\share\file.ext
            rb'(\\\\[^\x00-\x1f\\/:*?"<>|]+(?:\\[^\x00-\x1f\\/:*?"<>|]+)+\.(?:jpg|jpeg|png|tga|tif|tiff|bmp|gif|exr|hdr|psd|dds|tx|tex|vrmesh|abc|rs|ass|bgeo|obj|ies|hdri))',
        ]
        
        for pattern in patterns:
            try:
                matches = re.findall(pattern, data, re.IGNORECASE)
                for match in matches:
                    self._process_found_path(match, assets)
            except Exception as e:
                if self.debug:
                    assets.debug_info.append(f"ASCII pattern error: {e}")
    
    def _extract_unicode_paths(self, data: bytes, assets: SceneAssets):
        """Извлекает Unicode (UTF-16 LE) пути"""
        
        # Ищем паттерны типа "C\x00:\x00\\x00" (UTF-16 LE)
        # Паттерн для диска
        drive_pattern = rb'([A-Za-z]\x00:\x00[\\/]\x00)'
        
        matches = list(re.finditer(drive_pattern, data))
        
        for match in matches:
            start = match.start()
            # Читаем до 500 символов (1000 байт в UTF-16)
            end = min(start + 1000, len(data))
            chunk = data[start:end]
            
            # Ищем конец строки (null-terminator или невалидный символ)
            try:
                # Декодируем UTF-16 LE
                decoded = ""
                for i in range(0, len(chunk) - 1, 2):
                    char_code = struct.unpack('<H', chunk[i:i+2])[0]
                    if char_code == 0 or char_code > 127:
                        # Проверяем кириллицу (0x0400-0x04FF)
                        if 0x0400 <= char_code <= 0x04FF:
                            decoded += chr(char_code)
                        elif char_code == 0:
                            break
                        else:
                            break
                    else:
                        decoded += chr(char_code)
                
                if decoded and len(decoded) > 5:
                    self._process_found_path(decoded.encode('utf-8'), assets)
                    
            except Exception as e:
                if self.debug:
                    assets.debug_info.append(f"Unicode decode error: {e}")
    
    def _extract_by_extension(self, data: bytes, assets: SceneAssets):
        """Ищет пути по известным расширениям"""
        
        all_extensions = list(self.TEXTURE_EXTENSIONS) + list(self.PROXY_EXTENSIONS)
        
        for ext in all_extensions:
            # ASCII версия
            ext_bytes = ext.encode('ascii')
            self._find_paths_by_extension(data, ext_bytes, assets)
            
            # UTF-16 LE версия
            ext_utf16 = ext.encode('utf-16-le')
            self._find_paths_by_extension_utf16(data, ext_utf16, assets)
    
    def _find_paths_by_extension(self, data: bytes, ext: bytes, assets: SceneAssets):
        """Ищет пути с конкретным расширением (ASCII)"""
        
        pos = 0
        while True:
            pos = data.find(ext, pos)
            if pos == -1:
                break
            
            # Ищем начало пути (идём назад)
            start = pos
            for i in range(pos - 1, max(pos - 500, 0), -1):
                byte = data[i]
                # Проверяем на допустимые символы пути
                if byte < 32 or byte > 126:
                    start = i + 1
                    break
                # Проверяем на начало пути (буква диска)
                if i > 0 and data[i] == ord(':') and (65 <= data[i-1] <= 90 or 97 <= data[i-1] <= 122):
                    start = i - 1
                    break
            
            # Извлекаем путь
            end = pos + len(ext)
            path_bytes = data[start:end]
            
            self._process_found_path(path_bytes, assets)
            
            pos = end
    
    def _find_paths_by_extension_utf16(self, data: bytes, ext: bytes, assets: SceneAssets):
        """Ищет пути с конкретным расширением (UTF-16 LE)"""
        
        pos = 0
        while True:
            pos = data.find(ext, pos)
            if pos == -1:
                break
            
            # Ищем начало пути
            start = pos
            for i in range(pos - 2, max(pos - 1000, 0), -2):
                if i < 0:
                    break
                    
                char_code = struct.unpack('<H', data[i:i+2])[0] if i + 2 <= len(data) else 0
                
                # Проверяем на начало пути
                if i >= 2:
                    prev_code = struct.unpack('<H', data[i-2:i])[0]
                    # Буква диска + двоеточие
                    if char_code == ord(':') and (65 <= prev_code <= 90 or 97 <= prev_code <= 122):
                        start = i - 2
                        break
                
                # Невалидный символ
                if char_code == 0 or (char_code > 127 and not (0x0400 <= char_code <= 0x04FF)):
                    start = i + 2
                    break
            
            # Извлекаем и декодируем путь
            end = pos + len(ext)
            try:
                path_str = data[start:end].decode('utf-16-le', errors='ignore')
                if path_str:
                    self._process_found_path(path_str.encode('utf-8'), assets)
            except Exception:
                pass
            
            pos = end
    
    def _process_found_path(self, path_data: bytes, assets: SceneAssets):
        """Обрабатывает найденный путь"""
        
        # Пробуем разные кодировки
        path_str = None
        for encoding in ['utf-8', 'cp1251', 'latin-1']:
            try:
                path_str = path_data.decode(encoding).strip()
                break
            except UnicodeDecodeError:
                continue
        
        if not path_str:
            return
        
        # Очищаем путь
        path_str = path_str.strip('\x00').strip()
        
        # Проверяем валидность
        if not self._is_valid_path(path_str):
            return
        
        # Классифицируем
        self._classify_path(path_str, assets)
    
    def _is_valid_path(self, path_str: str) -> bool:
        """Проверяет валидность пути"""
        
        if not path_str or len(path_str) < 5:
            return False
        
        # Должен содержать расширение
        if '.' not in path_str:
            return False
        
        # Получаем расширение
        try:
            ext = Path(path_str).suffix.lower()
        except Exception:
            return False
        
        if not ext:
            return False
        
        # Проверяем на известные расширения
        all_extensions = self.TEXTURE_EXTENSIONS | self.PROXY_EXTENSIONS | {'.ies', '.hdri', '.mat', '.vismat'}
        if ext not in all_extensions:
            return False
        
        # Фильтруем системные пути
        lower_path = path_str.lower()
        if any(x in lower_path for x in ['windows', 'system32', 'program files\\autodesk', 
                                          'program files\\chaos', '.dll', '.exe', 
                                          'en-us', 'mui', 'autodesk\\3ds max']):
            return False
        
        return True
    
    def _classify_path(self, path_str: str, assets: SceneAssets):
        """Классифицирует путь по типу ассета"""
        
        try:
            ext = Path(path_str).suffix.lower()
        except Exception:
            return
        
        if ext in self.TEXTURE_EXTENSIONS:
            assets.textures.add(path_str)
            if self.debug:
                assets.debug_info.append(f"Found texture: {path_str}")
        elif ext in self.PROXY_EXTENSIONS:
            assets.proxies.add(path_str)
            if self.debug:
                assets.debug_info.append(f"Found proxy: {path_str}")
        elif ext in {'.ies', '.hdri', '.mat', '.vismat'}:
            assets.other_assets.add(path_str)
    
    def _resolve_relative_paths(self, assets: SceneAssets):
        """Резолвит относительные пути"""
        
        scene_dir = assets.scene_path.parent
        
        def resolve_path(path_str: str) -> str:
            if path_str.startswith('..') or path_str.startswith('.\\') or path_str.startswith('./'):
                try:
                    resolved = (scene_dir / path_str).resolve()
                    return str(resolved)
                except Exception:
                    pass
            return path_str
        
        assets.textures = {resolve_path(p) for p in assets.textures}
        assets.proxies = {resolve_path(p) for p in assets.proxies}
        assets.other_assets = {resolve_path(p) for p in assets.other_assets}
    
    def _clean_paths(self, assets: SceneAssets):
        """Очищает пути от мусора"""
        
        def clean_set(paths: Set[str]) -> Set[str]:
            cleaned = set()
            for p in paths:
                # Убираем дубликаты с разным регистром
                # Нормализуем слэши
                normalized = p.replace('/', '\\')
                # Убираем двойные слэши
                while '\\\\' in normalized and not normalized.startswith('\\\\'):
                    normalized = normalized.replace('\\\\', '\\')
                cleaned.add(normalized)
            return cleaned
        
        assets.textures = clean_set(assets.textures)
        assets.proxies = clean_set(assets.proxies)
        assets.other_assets = clean_set(assets.other_assets)
