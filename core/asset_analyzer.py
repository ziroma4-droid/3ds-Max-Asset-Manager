"""
Анализатор ассетов - сравнивает файлы в папке с используемыми в сценах
Сканирует ВСЕ подпапки включая maps, Proxy, textures и т.д.
"""

import os
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from .max_parser import MaxFileParser, SceneAssets


@dataclass
class FileInfo:
    """Информация о файле"""
    path: Path
    name: str
    extension: str
    folder: str  # Подпапка (maps, Proxy, и т.д.)
    file_type: str  # texture, proxy, other
    is_used: bool = False
    used_in_scenes: List[str] = field(default_factory=list)


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
    unused_files: Set[Path] = field(default_factory=set)
    missing_files: Set[str] = field(default_factory=set)
    linked_files: Set[Path] = field(default_factory=set)
    
    # Детальная информация о каждом файле
    all_files_info: Dict[Path, FileInfo] = field(default_factory=dict)
    
    # Статистика по папкам
    folder_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
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
            except (ValueError, OSError, AttributeError):
                pass
        return names
    
    def get_files_by_folder(self, folder_name: str) -> List[FileInfo]:
        """Получить файлы из конкретной подпапки"""
        return [f for f in self.all_files_info.values() if f.folder.lower() == folder_name.lower()]
    
    def get_unused_by_folder(self) -> Dict[str, List[FileInfo]]:
        """Получить неиспользуемые файлы, сгруппированные по папкам"""
        result = {}
        for file_info in self.all_files_info.values():
            if not file_info.is_used:
                if file_info.folder not in result:
                    result[file_info.folder] = []
                result[file_info.folder].append(file_info)
        return result


class AssetAnalyzer:
    """Анализатор ассетов сцен и папок"""
    
    # Расширения для поиска в папке
    TEXTURE_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.tga', '.tif', '.tiff',
        '.bmp', '.gif', '.exr', '.hdr', '.psd', '.dds',
        '.tx', '.tex'
    }
    
    PROXY_EXTENSIONS = {
        '.vrmesh',  # V-Ray proxy
        '.vrmap',   # V-Ray proxy map
        '.vrscene', # V-Ray scene
        '.cgeo',    # Corona proxy
        '.abc',     # Alembic
        '.rs',      # Redshift proxy
        '.ass',     # Arnold proxy
        '.bgeo',    # Houdini geometry
        '.obj'      # OBJ (часто используется как прокси)
    }
    
    OTHER_EXTENSIONS = {
        '.ies', '.hdri', '.mat', '.vismat'
    }
    
    # Все поддерживаемые расширения
    ALL_EXTENSIONS = TEXTURE_EXTENSIONS | PROXY_EXTENSIONS | OTHER_EXTENSIONS
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.parser = MaxFileParser(debug=debug)
    
    def analyze_single_scene(self, scene_path: Path, 
                             search_folder: Optional[Path] = None) -> AnalysisResult:
        """Анализирует одну сцену и ВСЮ папку проекта"""
        
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
        
        # Сканируем ВСЮ папку проекта
        self._scan_folder_deep(search_folder, result)
        
        # Сравниваем
        self._compare_assets(result)
        
        # Собираем статистику
        self._collect_stats(result)
        
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
        
        # Сканируем ВСЮ папку
        self._scan_folder_deep(folder_path, result)
        
        # Сравниваем
        self._compare_assets(result)
        
        # Собираем статистику
        self._collect_stats(result)
        
        return result
    
    def _scan_folder_deep(self, folder_path: Path, result: AnalysisResult):
        """
        Глубокое сканирование папки - находит ВСЕ файлы ассетов
        во всех подпапках
        """
        
        if self.debug:
            result.debug_info.append(f"\n🔍 Сканирование папки: {folder_path}")
        
        # Рекурсивно сканируем все подпапки
        for file_path in folder_path.rglob('*'):
            if not file_path.is_file():
                continue
            
            # Пропускаем папку unused (если уже есть)
            if 'unused' in file_path.parts:
                continue
            
            ext = file_path.suffix.lower()
            
            # Пропускаем неподдерживаемые расширения
            if ext not in self.ALL_EXTENSIONS:
                continue
            
            # Определяем тип файла
            if ext in self.TEXTURE_EXTENSIONS:
                file_type = 'texture'
                result.folder_textures.add(file_path)
            elif ext in self.PROXY_EXTENSIONS:
                file_type = 'proxy'
                result.folder_proxies.add(file_path)
            else:
                file_type = 'other'
                result.folder_other.add(file_path)
            
            # Определяем подпапку
            try:
                rel_path = file_path.relative_to(folder_path)
                if len(rel_path.parts) > 1:
                    subfolder = rel_path.parts[0]
                else:
                    subfolder = "(корень)"
            except ValueError:
                subfolder = "(корень)"
            
            # Создаём информацию о файле
            file_info = FileInfo(
                path=file_path,
                name=file_path.name,
                extension=ext,
                folder=subfolder,
                file_type=file_type
            )
            
            result.all_files_info[file_path] = file_info
        
        if self.debug:
            result.debug_info.append(f"  Найдено текстур: {len(result.folder_textures)}")
            result.debug_info.append(f"  Найдено прокси: {len(result.folder_proxies)}")
            result.debug_info.append(f"  Найдено других: {len(result.folder_other)}")
            
            # Показываем найденные подпапки
            subfolders = set(f.folder for f in result.all_files_info.values())
            result.debug_info.append(f"  Подпапки: {subfolders}")
    
    def _compare_assets(self, result: AnalysisResult):
        """Сравнивает используемые ассеты с файлами в папке"""
        
        # Создаём индекс имён файлов из сцены
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
            result.debug_info.append(f"\n📋 Имён в сцене: {len(scene_names_index)}")
        
        # Проверяем каждый файл в папке
        for file_path, file_info in result.all_files_info.items():
            file_name = file_path.name.lower()
            
            # Ищем по имени файла
            if file_name in scene_names_index:
                result.linked_files.add(file_path)
                file_info.is_used = True
                file_info.used_in_scenes = scene_names_index[file_name]
                
                if self.debug:
                    result.debug_info.append(f"  ✓ {file_info.folder}/{file_name}")
            else:
                result.unused_files.add(file_path)
                file_info.is_used = False
                
                if self.debug:
                    result.debug_info.append(f"  ✗ {file_info.folder}/{file_name}")
        
        # Определяем отсутствующие файлы
        folder_names = {f.name.lower() for f in result.all_folder_files}
        
        for asset_path in result.all_used_assets:
            try:
                asset_name = Path(asset_path).name.lower()
                
                if asset_name not in folder_names:
                    if not Path(asset_path).exists():
                        result.missing_files.add(asset_path)
                        
            except Exception:
                result.missing_files.add(asset_path)
    
    def _collect_stats(self, result: AnalysisResult):
        """Собирает статистику по папкам"""
        
        for file_info in result.all_files_info.values():
            folder = file_info.folder
            
            if folder not in result.folder_stats:
                result.folder_stats[folder] = {
                    'total': 0,
                    'used': 0,
                    'unused': 0,
                    'textures': 0,
                    'proxies': 0,
                    'other': 0
                }
            
            stats = result.folder_stats[folder]
            stats['total'] += 1
            
            if file_info.is_used:
                stats['used'] += 1
            else:
                stats['unused'] += 1
            
            if file_info.file_type == 'texture':
                stats['textures'] += 1
            elif file_info.file_type == 'proxy':
                stats['proxies'] += 1
            else:
                stats['other'] += 1
