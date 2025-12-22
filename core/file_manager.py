"""
Менеджер файлов - перемещение и организация ассетов
Собирает все связанные файлы в maps, удаляет дубликаты
"""

import os
import shutil
import hashlib
from pathlib import Path
from typing import List, Set, Dict, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MoveOperation:
    """Операция перемещения файла"""
    source: Path
    destination: Path
    action: str = "moved"
    success: bool = False
    error: Optional[str] = None


@dataclass 
class OrganizeResult:
    """Результат организации файлов"""
    operations: List[MoveOperation] = field(default_factory=list)
    maps_folder: Optional[Path] = None
    unused_folder: Optional[Path] = None
    duplicates_deleted: int = 0
    files_moved: int = 0
    files_skipped: int = 0
    
    @property
    def successful_moves(self) -> List[MoveOperation]:
        return [op for op in self.operations if op.success]
    
    @property
    def failed_moves(self) -> List[MoveOperation]:
        return [op for op in self.operations if not op.success]


class FileManager:
    """Менеджер для организации файлов ассетов"""
    
    def __init__(self, progress_callback: Optional[Callable[[str], None]] = None):
        self.progress_callback = progress_callback
    
    def _log(self, message: str):
        if self.progress_callback:
            try:
                self.progress_callback(message)
            except Exception:
                print(message)
    
    def _get_file_hash(self, file_path: Path, quick: bool = True) -> str:
        """Получает хэш файла для определения дубликатов"""
        try:
            file_size = file_path.stat().st_size
            
            if quick:
                with open(file_path, 'rb') as f:
                    head = f.read(1024)
                    f.seek(max(0, file_size - 1024))
                    tail = f.read(1024)
                return f"{file_size}_{hashlib.md5(head + tail).hexdigest()}"
            else:
                hasher = hashlib.md5()
                with open(file_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(65536), b''):
                        hasher.update(chunk)
                return hasher.hexdigest()
                
        except Exception as e:
            return f"error_{file_path.name}_{e}"
    
    def organize_assets(self, analysis, 
                        create_maps_folder: bool = True,
                        move_unused: bool = True,
                        copy_instead_of_move: bool = False,
                        delete_duplicates: bool = True) -> OrganizeResult:
        """
        Организует ассеты:
        1. Собирает все связанные файлы в папку maps
        2. Удаляет дубликаты
        3. Перемещает неиспользуемые в unused
        """
        
        result = OrganizeResult()
        
        try:
            base_folder = Path(analysis.folder_path)
            self._log(f"📂 Папка проекта: {base_folder}")
            
            maps_folder = base_folder / "maps"
            unused_folder = base_folder / "unused"
            
            if create_maps_folder:
                maps_folder.mkdir(exist_ok=True)
                result.maps_folder = maps_folder
                self._log(f"📁 Папка maps: {maps_folder}")
            
            if move_unused:
                unused_folder.mkdir(exist_ok=True)
                result.unused_folder = unused_folder
                self._log(f"📁 Папка unused: {unused_folder}")
            
            # === ШАГ 1: Собираем связанные файлы в maps ===
            if create_maps_folder and hasattr(analysis, 'linked_files'):
                self._log(f"\n{'='*50}")
                self._log(f"📦 СБОР СВЯЗАННЫХ ФАЙЛОВ В MAPS")
                self._log(f"{'='*50}")
                
                linked_files = list(analysis.linked_files)
                self._log(f"Связанных файлов: {len(linked_files)}")
                
                # Группируем файлы по имени
                files_by_name: Dict[str, List[Path]] = {}
                
                for file_path in linked_files:
                    file_path = Path(file_path)
                    if not file_path.exists():
                        continue
                    if file_path.suffix.lower() == '.max':
                        continue
                    
                    name = file_path.name.lower()
                    if name not in files_by_name:
                        files_by_name[name] = []
                    files_by_name[name].append(file_path)
                
                # Обрабатываем каждую группу
                for file_name, file_paths in files_by_name.items():
                    
                    if len(file_paths) == 1:
                        file_path = file_paths[0]
                        
                        if self._is_in_folder(file_path, maps_folder):
                            self._log(f"   ✓ Уже в maps: {file_name}")
                            result.files_skipped += 1
                            continue
                        
                        op = self._move_file(file_path, maps_folder, copy_instead_of_move)
                        result.operations.append(op)
                        if op.success:
                            result.files_moved += 1
                    
                    else:
                        self._log(f"\n   🔍 Дубликаты ({len(file_paths)}): {file_name}")
                        
                        in_maps = None
                        others = []
                        
                        for fp in file_paths:
                            if self._is_in_folder(fp, maps_folder):
                                in_maps = fp
                            else:
                                others.append(fp)
                        
                        if in_maps:
                            self._log(f"      ✓ В maps: {in_maps.name}")
                            master_hash = self._get_file_hash(in_maps)
                            
                            for other_file in others:
                                other_hash = self._get_file_hash(other_file)
                                
                                if other_hash == master_hash and delete_duplicates:
                                    op = self._delete_file(other_file, "дубликат")
                                    result.operations.append(op)
                                    if op.success:
                                        result.duplicates_deleted += 1
                                else:
                                    self._log(f"      ⚠ Разный контент: {other_file.parent.name}/{other_file.name}")
                                    op = self._move_file(other_file, maps_folder, copy_instead_of_move, rename=True)
                                    result.operations.append(op)
                        else:
                            master_file = others[0]
                            master_hash = self._get_file_hash(master_file)
                            
                            op = self._move_file(master_file, maps_folder, copy_instead_of_move)
                            result.operations.append(op)
                            if op.success:
                                result.files_moved += 1
                            
                            for other_file in others[1:]:
                                other_hash = self._get_file_hash(other_file)
                                
                                if other_hash == master_hash and delete_duplicates:
                                    op = self._delete_file(other_file, "дубликат")
                                    result.operations.append(op)
                                    if op.success:
                                        result.duplicates_deleted += 1
                                else:
                                    self._log(f"      ⚠ Разный контент: {other_file.parent.name}/{other_file.name}")
                                    op = self._move_file(other_file, maps_folder, copy_instead_of_move, rename=True)
                                    result.operations.append(op)
            
            # === ШАГ 2: Неиспользуемые в unused ===
            if move_unused and hasattr(analysis, 'unused_files'):
                self._log(f"\n{'='*50}")
                self._log(f"🗑️ НЕИСПОЛЬЗУЕМЫЕ → UNUSED")
                self._log(f"{'='*50}")
                
                unused_files = list(analysis.unused_files)
                self._log(f"Неиспользуемых: {len(unused_files)}")
                
                for file_path in unused_files:
                    file_path = Path(file_path)
                    
                    if not file_path.exists():
                        continue
                    if file_path.suffix.lower() == '.max':
                        continue
                    if self._is_in_folder(file_path, unused_folder):
                        continue
                    
                    op = self._move_file(file_path, unused_folder, copy_instead_of_move)
                    result.operations.append(op)
            
            # === ИТОГИ ===
            self._log(f"\n{'='*50}")
            self._log(f"✅ ГОТОВО!")
            self._log(f"   Перемещено в maps: {result.files_moved}")
            self._log(f"   Удалено дубликатов: {result.duplicates_deleted}")
            self._log(f"   Пропущено: {result.files_skipped}")
            self._log(f"   Успешно: {len(result.successful_moves)}")
            self._log(f"   Ошибок: {len(result.failed_moves)}")
            self._log(f"{'='*50}")
            
        except Exception as e:
            import traceback
            self._log(f"\n❌ Ошибка: {str(e)}")
            self._log(traceback.format_exc())
        
        return result
    
    def _is_in_folder(self, file_path: Path, folder: Optional[Path]) -> bool:
        if folder is None:
            return False
        try:
            file_path = Path(file_path).resolve()
            folder = Path(folder).resolve()
            return folder == file_path.parent or folder in file_path.parents
        except Exception:
            return False
    
    def _move_file(self, source: Path, dest_folder: Path, 
                   copy_mode: bool = False, rename: bool = False) -> MoveOperation:
        source = Path(source)
        dest_folder = Path(dest_folder)
        
        if rename:
            parent_name = source.parent.name
            new_name = f"{source.stem}_{parent_name}{source.suffix}"
            dest = dest_folder / new_name
        else:
            dest = dest_folder / source.name
        
        if dest.exists():
            dest = self._get_unique_name(dest)
        
        operation = MoveOperation(
            source=source, 
            destination=dest,
            action="copied" if copy_mode else "moved"
        )
        
        try:
            if copy_mode:
                shutil.copy2(str(source), str(dest))
                self._log(f"   📋 Скопирован: {source.parent.name}/{source.name}")
            else:
                shutil.move(str(source), str(dest))
                self._log(f"   📦 Перемещен: {source.parent.name}/{source.name}")
            
            operation.success = True
            
        except PermissionError:
            operation.error = "Нет доступа"
            self._log(f"   ❌ Нет доступа: {source.name}")
        except Exception as e:
            operation.error = str(e)
            self._log(f"   ❌ Ошибка: {source.name} - {e}")
        
        return operation
    
    def _delete_file(self, file_path: Path, reason: str = "") -> MoveOperation:
        operation = MoveOperation(
            source=file_path,
            destination=Path("(удалён)"),
            action="deleted_duplicate"
        )
        
        try:
            file_path.unlink()
            self._log(f"   🗑️ Удалён ({reason}): {file_path.parent.name}/{file_path.name}")
            operation.success = True
        except Exception as e:
            operation.error = str(e)
            self._log(f"   ❌ Не удалось удалить: {file_path.name}")
        
        return operation
    
    @staticmethod
    def _get_unique_name(path: Path) -> Path:
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        
        counter = 1
        new_path = path
        while new_path.exists():
            new_path = parent / f"{stem}_{counter}{suffix}"
            counter += 1
        
        return new_path
    
    def create_report(self, analysis, 
                      organize_result: Optional[OrganizeResult] = None) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("ОТЧЕТ ПО АССЕТАМ")
        lines.append(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)
        
        try:
            lines.append(f"\nПапка: {analysis.folder_path}")
            lines.append(f"Сцен: {len(analysis.scenes)}")
            lines.append(f"Текстур: {len(analysis.used_textures)}")
            lines.append(f"Прокси: {len(analysis.used_proxies)}")
            lines.append(f"Связанных: {len(analysis.linked_files)}")
            lines.append(f"Неиспользуемых: {len(analysis.unused_files)}")
            
            if organize_result:
                lines.append(f"\n--- ОРГАНИЗАЦИЯ ---")
                lines.append(f"Перемещено: {organize_result.files_moved}")
                lines.append(f"Дубликатов удалено: {organize_result.duplicates_deleted}")
                lines.append(f"Ошибок: {len(organize_result.failed_moves)}")
                
        except Exception as e:
            lines.append(f"\nОшибка: {e}")
        
        return "\n".join(lines)
