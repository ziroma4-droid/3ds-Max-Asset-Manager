"""
Анализатор ассетов - сравнивает файлы в папке с используемыми в сценах
Улучшенная версия с сопоставлением по имени файла
"""

import os
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from .max_parser import MaxFileParser, SceneAssets


@dataclass
class AnalysisResult:
    """Результат анализа папки"""
    folder_path: Path
    scenes: List[Path] = field(default_factory=list)
    
    # Все ассеты из всех сцен (пути как в сцене)
    used_textures: Set[str] = field(default_factory=set)
    used_proxies: Set[str] = field(default_factory=set)
    used_other: Set[str] = field(default_factory=set)
    
    # Файлы в папке (реальные пути)
    folder_textures: Set[Path] = field(default_factory=set)
    folder_proxies: Set[Path] = field(default_factory=set)
    folder_other: Set[Path] = field(default_factory=set)
    
    # Результаты сравнения
    unused_files: Set[Path] = field(default_factory=set)  # Файлы в папке, не используемые в сцене
    missing_files: Set[str] = field(default_factory=set)  # Файлы из сцены, которых нет в папке
    linked_files: Set[Path] = field(default_factory=set)  # Файлы в папке, используемые в сцене
    
    # Соответствия: файл в папке -> путь в сцене
    file_mappings: Dict[Path, str] = field(default_factory=dict)
    
    # Ошибки и отладка
    errors: List[str] = field(default_factory=list)
    debug_info: List[str] = field(default_factory=list)
    
    # Детали по каждой сцене
    scene_details: Dict[Path, SceneAssets] = field(default_factory=dict)
    
    @property
    def all_used_assets(self) -> Set[str]:
        return self.used_textures | self.used_proxies | self.used_other
    
    @property
    def all_folder_files(self) -> Set[Path]:
        return self.folder_textures | self.folder_proxies | self.folder_other
    
    @property
    def used_asset_names(self) -> Set[str]:
        """Имена файлов из сцены (только имена, без пути)"""
        names = set()
        for p in self.all_used_assets:
            try:
                names.add(Path(p).name.lower())
            except:
                pass
        return names


class AssetAnalyzer:
    """Анализатор ассетов сцен и папок"""
    
    # Расширения для поиска в папке
    TEXTURE_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.tga', '.tif', '.tiff',
        '.bmp', '.gif', '.exr', '.hdr', '.psd', '.dds',
        '.tx', '.tex'
    }
    
    PROXY_EXTENSIONS = {
        '.vrmesh', '.abc', '.rs', '.ass', '.bgeo', '.obj'
    }
    
    OTHER_EXTENSIONS = {
        '.ies', '.hdri', '.mat', '.vismat'
    }
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.parser = MaxFileParser(debug=debug)
    
    def analyze_single_scene(self, scene_path: Path, 
                             search_folder: Optional[Path] = None) -> AnalysisResult:
        """Анализирует одну сцену"""
        
        if search_folder is None:
            search_folder = scene_path.parent
        
        result = AnalysisResult(
            folder_path=search_folder,
            scenes=[scene_path]
        )
        
        # Парсим сцену
        scene_assets = self.parser.parse_scene(scene_path)
        result.scene_details[scene_path] = scene_assets
        result.errors.extend(scene_assets.errors)
        result.debug_info.extend(scene_assets.debug_info)
        
        # Собираем используемые ассеты
        result.used_textures = scene_assets.textures.copy()
        result.used_proxies = scene_assets.proxies.copy()
        result.used_other = scene_assets.other_assets.copy()
        
        # Сканируем папку
        self._scan_folder(search_folder, result)
        
        # Сравниваем
        self._compare_assets(result)
        
        # Выводим статистику
        if self.debug:
            result.debug_info.append(f"\n=== СТАТИСТИКА СРАВНЕНИЯ ===")
            result.debug_info.append(f"Ассетов в сцене: {len(result.all_used_assets)}")
            result.debug_info.append(f"Файлов в папке: {len(result.all_folder_files)}")
            result.debug_info.append(f"Связанных: {len(result.linked_files)}")
            result.debug_info.append(f"Неиспользуемых: {len(result.unused_files)}")
            result.debug_info.append(f"Отсутствующих: {len(result.missing_files)}")
        
        return result
    
    def analyze_folder(self, folder_path: Path, 
                       recursive: bool = False) -> AnalysisResult:
        """Анализирует папку с несколькими сценами"""
        
        result = AnalysisResult(folder_path=folder_path)
        
        # Находим все .max файлы
        if recursive:
            max_files = list(folder_path.rglob('*.max'))
        else:
            max_files = list(folder_path.glob('*.max'))
        
        result.scenes = max_files
        
        if not max_files:
            result.errors.append(f"В папке {folder_path} не найдено .max файлов")
            return result
        
        # Парсим каждую сцену
        for scene_path in max_files:
            scene_assets = self.parser.parse_scene(scene_path)
            result.scene_details[scene_path] = scene_assets
            result.errors.extend(scene_assets.errors)
            result.debug_info.extend(scene_assets.debug_info)
            
            # Объединяем ассеты
            result.used_textures.update(scene_assets.textures)
            result.used_proxies.update(scene_assets.proxies)
            result.used_other.update(scene_assets.other_assets)
        
        # Сканируем папку
        self._scan_folder(folder_path, result, recursive)
        
        # Сравниваем
        self._compare_assets(result)
        
        return result
    
    def _scan_folder(self, folder_path: Path, result: AnalysisResult, 
                     recursive: bool = True):
        """Сканирует папку на наличие ассетов"""
        
        all_files = []
        
        if recursive:
            all_files = list(folder_path.rglob('*'))
        else:
            # Сканируем корень
            all_files = list(folder_path.glob('*'))
            
            # И стандартные подпапки
            for subdir in ['maps', 'textures', 'tex', 'proxy', 'proxies', 
                          'assets', 'Proxy', 'Maps', 'Textures']:
                sub_path = folder_path / subdir
                if sub_path.exists() and sub_path.is_dir():
                    all_files.extend(sub_path.rglob('*'))
        
        for file_path in all_files:
            if not file_path.is_file():
                continue
            
            # Пропускаем файлы в unused
            if 'unused' in file_path.parts:
                continue
            
            ext = file_path.suffix.lower()
            
            if ext in self.TEXTURE_EXTENSIONS:
                result.folder_textures.add(file_path)
            elif ext in self.PROXY_EXTENSIONS:
                result.folder_proxies.add(file_path)
            elif ext in self.OTHER_EXTENSIONS:
                result.folder_other.add(file_path)
        
        if self.debug:
            result.debug_info.append(f"\nСканирование папки: {folder_path}")
            result.debug_info.append(f"  Текстур найдено: {len(result.folder_textures)}")
            result.debug_info.append(f"  Прокси найдено: {len(result.folder_proxies)}")
    
    def _compare_assets(self, result: AnalysisResult):
        """Сравнивает используемые ассеты с файлами в папке"""
        
        # Создаём индекс имён файлов из сцены
        # имя файла (lower) -> список полных путей из сцены
        scene_names_index: Dict[str, List[str]] = {}
        
        for asset_path in result.all_used_assets:
            try:
                name = Path(asset_path).name.lower()
                if name not in scene_names_index:
                    scene_names_index[name] = []
                scene_names_index[name].append(asset_path)
            except Exception:
                continue
        
        if self.debug:
            result.debug_info.append(f"\nИндекс имён из сцены: {len(scene_names_index)} уникальных имён")
            for name in list(scene_names_index.keys())[:5]:
                result.debug_info.append(f"  {name}")
        
        # Проверяем каждый файл в папке
        matched_scene_assets: Set[str] = set()  # Какие ассеты из сцены нашли
        
        for file_path in result.all_folder_files:
            file_name = file_path.name.lower()
            
            # Ищем по имени файла
            if file_name in scene_names_index:
                result.linked_files.add(file_path)
                result.file_mappings[file_path] = scene_names_index[file_name][0]
                matched_scene_assets.update(scene_names_index[file_name])
                
                if self.debug:
                    result.debug_info.append(f"  ✓ Связан: {file_name}")
            else:
                result.unused_files.add(file_path)
                
                if self.debug:
                    result.debug_info.append(f"  ✗ Не используется: {file_name}")
        
        # Определяем отсутствующие файлы
        # (те, что есть в сцене, но не найдены в папке)
        folder_names = {f.name.lower() for f in result.all_folder_files}
        
        for asset_path in result.all_used_assets:
            try:
                asset_name = Path(asset_path).name.lower()
                
                # Если файл не найден в папке по имени
                if asset_name not in folder_names:
                    # Проверяем, существует ли он по оригинальному пути
                    if not Path(asset_path).exists():
                        result.missing_files.add(asset_path)
                        
            except Exception:
                result.missing_files.add(asset_path)
    
    @staticmethod
    def _normalize_path(path_str: str) -> str:
        """Нормализует путь для сравнения"""
        try:
            normalized = path_str.lower().replace('/', '\\')
            if normalized.startswith('\\\\'):
                prefix = '\\\\'
                normalized = prefix + normalized[2:].replace('\\\\', '\\')
            else:
                normalized = normalized.replace('\\\\', '\\')
            return normalized
        except Exception:
            return path_str.lower()
