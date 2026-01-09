"""
Менеджер файлов - перемещение и организация ассетов
Собирает все связанные файлы в maps, удаляет дубликаты
"""

import os
import shutil
import hashlib
import uuid
from pathlib import Path
from typing import List, Set, Dict, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime

from .backup_manager import BackupManager
from .operation_history import OperationHistory, Operation, OperationType
from .file_integrity import FileIntegrityChecker


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
    backup_id: Optional[str] = None
    integrity_errors: List[Dict] = field(default_factory=list)
    
    @property
    def successful_moves(self) -> List[MoveOperation]:
        return [op for op in self.operations if op.success]
    
    @property
    def failed_moves(self) -> List[MoveOperation]:
        return [op for op in self.operations if not op.success]


class FileManager:
    """Менеджер для организации файлов ассетов"""
    
    # Расширения файлов-изображений для проверки целостности
    TEXTURE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tga', '.tif', '.tiff', 
                          '.bmp', '.gif', '.exr', '.hdr', '.psd', '.dds', '.tx', '.tex'}
    
    def __init__(self, progress_callback: Optional[Callable[[str], None]] = None,
                 enable_backup: bool = False,
                 check_integrity: bool = True):
        self.progress_callback = progress_callback
        self.enable_backup = enable_backup
        self.check_integrity = check_integrity
        self.backup_manager: Optional[BackupManager] = None
        self.operation_history = OperationHistory()
    
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
            
            # Инициализируем резервное копирование если нужно
            if self.enable_backup:
                self.backup_manager = BackupManager(base_folder)
                self.backup_manager.cleanup_old_backups()
                backup_id = str(uuid.uuid4())
                result.backup_id = backup_id
                self._log(f"💾 Резервное копирование включено (ID: {backup_id[:8]}...)")
            else:
                backup_id = None
            
            maps_folder = base_folder / "maps"
            unused_folder = base_folder / "unused"
            
            if create_maps_folder:
                maps_folder.mkdir(exist_ok=True)
                result.maps_folder = maps_folder
                self._log(f"📁 Папка maps: {maps_folder}")
            
            # Проверяем, есть ли неиспользуемые файлы перед созданием папки
            unused_files_count = 0
            if move_unused and hasattr(analysis, 'unused_files'):
                unused_files_count = len([f for f in analysis.unused_files 
                                         if Path(f).exists() and Path(f).suffix.lower() != '.max'])
            
            if move_unused and unused_files_count > 0:
                unused_folder.mkdir(exist_ok=True)
                result.unused_folder = unused_folder
                self._log(f"📁 Папка unused: {unused_folder}")
            else:
                # Не создаем папку, если нет неиспользуемых файлов
                result.unused_folder = None
            
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
                        
                        # Проверка целостности только для изображений (текстур)
                        if self.check_integrity:
                            # Проверяем только файлы-изображения
                            if file_path.suffix.lower() in self.TEXTURE_EXTENSIONS:
                                is_valid, error = FileIntegrityChecker.check_image_integrity(file_path)
                                if not is_valid:
                                    result.integrity_errors.append({
                                        'file': str(file_path),
                                        'error': error
                                    })
                                    self._log(f"   ⚠️ Поврежден: {file_name} - {error}")
                        
                        # Резервное копирование
                        if self.enable_backup and backup_id:
                            self.backup_manager.create_backup(file_path, backup_id)
                        
                        # Определяем, копировать или перемещать: если файл вне папки сцены - копировать
                        should_copy = not self._is_file_in_scene_folder(file_path, analysis)
                        if should_copy:
                            self._log(f"   📋 Файл вне папки сцены, будет скопирован: {file_name}")
                        
                        op = self._move_file(file_path, maps_folder, should_copy, backup_id)
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
                                    # Резервное копирование перед удалением
                                    if self.enable_backup and backup_id:
                                        self.backup_manager.create_backup(other_file, backup_id)
                                    op = self._delete_file(other_file, "дубликат", backup_id)
                                    result.operations.append(op)
                                    if op.success:
                                        result.duplicates_deleted += 1
                                else:
                                    self._log(f"      ⚠ Разный контент: {other_file.parent.name}/{other_file.name}")
                                    if self.enable_backup and backup_id:
                                        self.backup_manager.create_backup(other_file, backup_id)
                                    # Определяем, копировать или перемещать
                                    should_copy = not self._is_file_in_scene_folder(other_file, analysis)
                                    op = self._move_file(other_file, maps_folder, should_copy, backup_id, rename=True)
                                    result.operations.append(op)
                        else:
                            master_file = others[0]
                            master_hash = self._get_file_hash(master_file)
                            
                            # Проверка целостности и резервное копирование для master_file
                            # Проверяем только файлы-изображения
                            if self.check_integrity:
                                if master_file.suffix.lower() in self.TEXTURE_EXTENSIONS:
                                    is_valid, error = FileIntegrityChecker.check_image_integrity(master_file)
                                    if not is_valid:
                                        result.integrity_errors.append({
                                            'file': str(master_file),
                                            'error': error
                                        })
                                        self._log(f"   ⚠️ Поврежден: {master_file.name} - {error}")
                            
                            if self.enable_backup and backup_id:
                                self.backup_manager.create_backup(master_file, backup_id)
                            
                            # Определяем, копировать или перемещать
                            should_copy = not self._is_file_in_scene_folder(master_file, analysis)
                            if should_copy:
                                self._log(f"   📋 Файл вне папки сцены, будет скопирован: {master_file.name}")
                            
                            op = self._move_file(master_file, maps_folder, should_copy, backup_id)
                            result.operations.append(op)
                            if op.success:
                                result.files_moved += 1
                            
                            for other_file in others[1:]:
                                other_hash = self._get_file_hash(other_file)
                                
                                if other_hash == master_hash and delete_duplicates:
                                    if self.enable_backup and backup_id:
                                        self.backup_manager.create_backup(other_file, backup_id)
                                    op = self._delete_file(other_file, "дубликат", backup_id)
                                    result.operations.append(op)
                                    if op.success:
                                        result.duplicates_deleted += 1
                                else:
                                    self._log(f"      ⚠ Разный контент: {other_file.parent.name}/{other_file.name}")
                                    if self.enable_backup and backup_id:
                                        self.backup_manager.create_backup(other_file, backup_id)
                                    # Определяем, копировать или перемещать
                                    should_copy = not self._is_file_in_scene_folder(other_file, analysis)
                                    op = self._move_file(other_file, maps_folder, should_copy, backup_id, rename=True)
                                    result.operations.append(op)
            
            # === ШАГ 2: Неиспользуемые в unused ===
            if move_unused and hasattr(analysis, 'unused_files') and unused_folder and unused_folder.exists():
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
                    
                    # Резервное копирование
                    if self.enable_backup and backup_id:
                        self.backup_manager.create_backup(file_path, backup_id)
                    
                    # Для неиспользуемых файлов также проверяем расположение
                    # Если файл вне папки сцены - копируем, иначе перемещаем
                    should_copy = not self._is_file_in_scene_folder(file_path, analysis)
                    
                    op = self._move_file(file_path, unused_folder, should_copy, backup_id)
                    result.operations.append(op)
            
            # Проверяем, осталась ли папка unused пустой после обработки
            if move_unused and unused_folder.exists():
                try:
                    # Проверяем, есть ли файлы в папке
                    has_files = False
                    for item in unused_folder.iterdir():
                        has_files = True
                        break
                    
                    # Если папка пуста, удаляем её
                    if not has_files:
                        unused_folder.rmdir()
                        result.unused_folder = None
                        self._log(f"🗑️ Папка unused была пуста и удалена")
                except Exception as e:
                    # Игнорируем ошибки при проверке/удалении
                    pass
            
            # === ШАГ 3: Удаление пустых папок ===
            self._log(f"\n{'='*50}")
            self._log(f"🧹 УДАЛЕНИЕ ПУСТЫХ ПАПОК")
            self._log(f"{'='*50}")
            # Исключаем папки maps и unused из удаления
            exclude = []
            if maps_folder.exists():
                exclude.append(maps_folder)
            if unused_folder.exists():
                exclude.append(unused_folder)
            empty_folders_removed = self._remove_empty_folders(base_folder, exclude_folders=exclude)
            self._log(f"Удалено пустых папок: {empty_folders_removed}")
            
            # === ИТОГИ ===
            self._log(f"\n{'='*50}")
            self._log(f"✅ ГОТОВО!")
            self._log(f"   Перемещено в maps: {result.files_moved}")
            self._log(f"   Удалено дубликатов: {result.duplicates_deleted}")
            self._log(f"   Пропущено: {result.files_skipped}")
            self._log(f"   Успешно: {len(result.successful_moves)}")
            self._log(f"   Ошибок: {len(result.failed_moves)}")
            self._log(f"   Удалено пустых папок: {empty_folders_removed}")
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
    
    def _is_file_in_scene_folder(self, file_path: Path, analysis) -> bool:
        """
        Проверяет, находится ли файл внутри папки какой-либо сцены.
        Если файл находится внутри папки сцены (или её подпапок), его нужно перемещать.
        Если файл находится вне всех папок сцен, его нужно копировать.
        
        Args:
            file_path: Путь к файлу для проверки
            analysis: Объект AnalysisResult с информацией о сценах
            
        Returns:
            True если файл находится внутри папки сцены, False если вне
        """
        if not hasattr(analysis, 'scenes') or not analysis.scenes:
            # Если нет информации о сценах, считаем что файл внутри (старое поведение)
            return True
        
        try:
            file_path = Path(file_path).resolve()
            
            # Проверяем каждую сцену
            for scene_path in analysis.scenes:
                scene_path = Path(scene_path)
                if not scene_path.exists():
                    continue
                
                # Получаем папку сцены (родительскую папку .max файла)
                scene_folder = scene_path.parent.resolve()
                
                # Проверяем, находится ли файл внутри папки сцены
                # Используем relative_to для надежной проверки
                try:
                    file_path.relative_to(scene_folder)
                    # Если не выброшено исключение, файл находится внутри папки сцены
                    return True
                except (ValueError, OSError):
                    # Файл не находится в этой папке сцены, проверяем следующую
                    continue
            
            # Файл не находится ни в одной папке сцены
            return False
            
        except Exception:
            # В случае ошибки считаем что файл внутри (безопасное поведение)
            return True
    
    def _move_file(self, source: Path, dest_folder: Path, 
                   copy_mode: bool = False, backup_id: Optional[str] = None,
                   rename: bool = False) -> MoveOperation:
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
                op_type = OperationType.COPY
            else:
                shutil.move(str(source), str(dest))
                self._log(f"   📦 Перемещен: {source.parent.name}/{source.name}")
                op_type = OperationType.MOVE
            
            operation.success = True
            
            # Добавляем в историю
            history_op = Operation(
                id=str(uuid.uuid4()),
                type=op_type,
                source=source,
                destination=dest,
                success=True,
                backup_id=backup_id,
                base_folder=self.backup_manager.base_folder if self.backup_manager else None
            )
            self.operation_history.add_operation(history_op)
            
        except PermissionError:
            operation.error = "Нет доступа"
            self._log(f"   ❌ Нет доступа: {source.name}")
            
            # Добавляем в историю с ошибкой
            history_op = Operation(
                id=str(uuid.uuid4()),
                type=OperationType.MOVE if not copy_mode else OperationType.COPY,
                source=source,
                destination=dest,
                success=False,
                error="Нет доступа",
                backup_id=backup_id,
                base_folder=self.backup_manager.base_folder if self.backup_manager else None
            )
            self.operation_history.add_operation(history_op)
        except Exception as e:
            operation.error = str(e)
            self._log(f"   ❌ Ошибка: {source.name} - {e}")
            
            # Добавляем в историю с ошибкой
            history_op = Operation(
                id=str(uuid.uuid4()),
                type=OperationType.MOVE if not copy_mode else OperationType.COPY,
                source=source,
                destination=dest,
                success=False,
                error=str(e),
                backup_id=backup_id,
                base_folder=self.backup_manager.base_folder if self.backup_manager else None
            )
            self.operation_history.add_operation(history_op)
        
        return operation
    
    def _delete_file(self, file_path: Path, reason: str = "", backup_id: Optional[str] = None) -> MoveOperation:
        operation = MoveOperation(
            source=file_path,
            destination=Path("(удалён)"),
            action="deleted_duplicate"
        )
        
        try:
            file_path.unlink()
            self._log(f"   🗑️ Удалён ({reason}): {file_path.parent.name}/{file_path.name}")
            operation.success = True
            
            # Добавляем в историю
            history_op = Operation(
                id=str(uuid.uuid4()),
                type=OperationType.DELETE,
                source=file_path,
                success=True,
                backup_id=backup_id,
                base_folder=self.backup_manager.base_folder if self.backup_manager else None
            )
            self.operation_history.add_operation(history_op)
        except Exception as e:
            operation.error = str(e)
            self._log(f"   ❌ Не удалось удалить: {file_path.name}")
            
            # Добавляем в историю с ошибкой
            history_op = Operation(
                id=str(uuid.uuid4()),
                type=OperationType.DELETE,
                source=file_path,
                success=False,
                error=str(e),
                backup_id=backup_id,
                base_folder=self.backup_manager.base_folder if self.backup_manager else None
            )
            self.operation_history.add_operation(history_op)
        
        return operation
    
    def restore_folder(self, base_folder: Path, backup_id: str) -> bool:
        """
        Восстанавливает всю папку из резервной копии
        
        Args:
            base_folder: Корневая папка для восстановления
            backup_id: Идентификатор резервной копии
            
        Returns:
            True если успешно
        """
        if not self.backup_manager:
            # Создаем BackupManager для этой папки
            self.backup_manager = BackupManager(base_folder)
        
        return self.backup_manager.restore_backup(backup_id)
    
    def undo_last_operation(self) -> bool:
        """Отменяет последнюю операцию"""
        if not self.operation_history.can_undo():
            return False
        
        last_op = self.operation_history.get_last_operation()
        if not last_op or not last_op.success:
            return False
        
        try:
            if last_op.type == OperationType.MOVE:
                # Возвращаем файл обратно
                if last_op.destination and last_op.destination.exists():
                    shutil.move(str(last_op.destination), str(last_op.source))
            elif last_op.type == OperationType.COPY:
                # Удаляем копию
                if last_op.destination and last_op.destination.exists():
                    last_op.destination.unlink()
            elif last_op.type == OperationType.DELETE:
                # Восстанавливаем из резервной копии
                if last_op.backup_id and self.backup_manager:
                    return self.backup_manager.restore_backup(last_op.backup_id)
            
            # Добавляем операцию восстановления в историю
            restore_op = Operation(
                id=str(uuid.uuid4()),
                type=OperationType.RESTORE,
                source=last_op.source,
                destination=last_op.destination,
                success=True,
                backup_id=last_op.backup_id,
                base_folder=last_op.base_folder
            )
            self.operation_history.add_operation(restore_op)
            
            return True
        except Exception as e:
            return False
    
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
    
    def _remove_empty_folders(self, base_folder: Path, exclude_folders: Optional[List[Path]] = None) -> int:
        """
        Удаляет пустые папки в базовой директории
        
        Args:
            base_folder: Базовая папка для поиска пустых папок
            exclude_folders: Список папок, которые не нужно удалять (например, maps, unused)
            
        Returns:
            Количество удаленных папок
        """
        if exclude_folders is None:
            exclude_folders = []
        
        # Преобразуем в абсолютные пути
        exclude_folders = [Path(f).resolve() for f in exclude_folders]
        base_folder = Path(base_folder).resolve()
        
        removed_count = 0
        
        try:
            # Собираем все папки, начиная с самых глубоких
            all_folders = []
            for folder in base_folder.rglob('*'):
                if folder.is_dir():
                    # Пропускаем исключенные папки и их содержимое
                    folder_resolved = folder.resolve()
                    if any(excluded in folder_resolved.parents or excluded == folder_resolved 
                          for excluded in exclude_folders):
                        continue
                    # Пропускаем папки maps и unused
                    if folder.name.lower() in ['maps', 'unused']:
                        continue
                    all_folders.append(folder_resolved)
            
            # Сортируем по глубине (самые глубокие сначала)
            all_folders.sort(key=lambda p: len(p.parts), reverse=True)
            
            # Удаляем пустые папки
            for folder in all_folders:
                try:
                    # Проверяем, что папка существует и пуста
                    if folder.exists() and folder.is_dir():
                        # Проверяем, что папка действительно пуста
                        has_files = False
                        try:
                            for item in folder.iterdir():
                                has_files = True
                                break
                        except (OSError, PermissionError):
                            has_files = True  # Если не можем прочитать, считаем что не пуста
                        
                        if not has_files:
                            folder.rmdir()
                            removed_count += 1
                            self._log(f"   🗑️ Удалена пустая папка: {folder.relative_to(base_folder)}")
                except (OSError, PermissionError) as e:
                    # Игнорируем ошибки доступа
                    pass
                    
        except Exception as e:
            self._log(f"   ⚠️ Ошибка при удалении пустых папок: {e}")
        
        return removed_count
    
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
