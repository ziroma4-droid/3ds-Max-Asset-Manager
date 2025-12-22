"""
Менеджер файлов - перемещение и организация ассетов
"""

import os
import shutil
from pathlib import Path
from typing import List, Set, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MoveOperation:
    """Операция перемещения файла"""
    source: Path
    destination: Path
    success: bool = False
    error: Optional[str] = None


@dataclass 
class OrganizeResult:
    """Результат организации файлов"""
    operations: List[MoveOperation] = field(default_factory=list)
    maps_folder: Optional[Path] = None
    unused_folder: Optional[Path] = None
    
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
        """Логирование с колбэком"""
        if self.progress_callback:
            try:
                self.progress_callback(message)
            except Exception:
                pass
    
    def organize_assets(self, analysis, 
                        create_maps_folder: bool = True,
                        move_unused: bool = True,
                        copy_instead_of_move: bool = False) -> OrganizeResult:
        """
        Организует ассеты на основе результатов анализа
        """
        
        result = OrganizeResult()
        
        try:
            base_folder = Path(analysis.folder_path)
            
            # Создаем папки
            if create_maps_folder:
                maps_folder = base_folder / "maps"
                maps_folder.mkdir(exist_ok=True)
                result.maps_folder = maps_folder
                self._log(f"📁 Папка maps: {maps_folder}")
            
            if move_unused:
                unused_folder = base_folder / "unused"
                unused_folder.mkdir(exist_ok=True)
                result.unused_folder = unused_folder
                self._log(f"📁 Папка unused: {unused_folder}")
            
            # Перемещаем связанные файлы в maps
            if create_maps_folder and hasattr(analysis, 'linked_files'):
                self._log(f"\n🔗 Обработка связанных файлов ({len(analysis.linked_files)}):")
                
                for file_path in analysis.linked_files:
                    file_path = Path(file_path)
                    
                    if not file_path.exists():
                        self._log(f"  ⚠ Файл не найден: {file_path.name}")
                        continue
                    
                    # Не перемещаем, если уже в maps
                    if self._is_in_folder(file_path, result.maps_folder):
                        self._log(f"  ✓ Уже в maps: {file_path.name}")
                        continue
                    
                    # Не перемещаем .max файлы
                    if file_path.suffix.lower() == '.max':
                        continue
                    
                    op = self._move_file(
                        file_path, 
                        result.maps_folder, 
                        copy_instead_of_move
                    )
                    result.operations.append(op)
            
            # Перемещаем неиспользуемые файлы в unused
            if move_unused and hasattr(analysis, 'unused_files'):
                self._log(f"\n🗑️ Обработка неиспользуемых файлов ({len(analysis.unused_files)}):")
                
                for file_path in analysis.unused_files:
                    file_path = Path(file_path)
                    
                    if not file_path.exists():
                        self._log(f"  ⚠ Файл не найден: {file_path.name}")
                        continue
                    
                    # Не перемещаем, если уже в unused
                    if self._is_in_folder(file_path, result.unused_folder):
                        self._log(f"  ✓ Уже в unused: {file_path.name}")
                        continue
                    
                    # Не перемещаем .max файлы
                    if file_path.suffix.lower() == '.max':
                        continue
                    
                    op = self._move_file(
                        file_path, 
                        result.unused_folder, 
                        copy_instead_of_move
                    )
                    result.operations.append(op)
            
            self._log(f"\n✅ Готово! Успешно: {len(result.successful_moves)}, Ошибок: {len(result.failed_moves)}")
            
        except Exception as e:
            self._log(f"\n❌ Критическая ошибка: {str(e)}")
            import traceback
            self._log(traceback.format_exc())
        
        return result
    
    def _is_in_folder(self, file_path: Path, folder: Optional[Path]) -> bool:
        """Проверяет, находится ли файл в папке"""
        if folder is None:
            return False
        
        try:
            file_path = Path(file_path).resolve()
            folder = Path(folder).resolve()
            return folder in file_path.parents or file_path.parent == folder
        except Exception:
            return False
    
    def _move_file(self, source: Path, dest_folder: Path, 
                   copy_mode: bool = False) -> MoveOperation:
        """Перемещает или копирует файл"""
        
        source = Path(source)
        dest_folder = Path(dest_folder)
        dest = dest_folder / source.name
        
        # Обработка конфликта имен
        if dest.exists():
            dest = self._get_unique_name(dest)
        
        operation = MoveOperation(source=source, destination=dest)
        
        try:
            if copy_mode:
                shutil.copy2(str(source), str(dest))
                self._log(f"  📋 Скопирован: {source.name}")
            else:
                shutil.move(str(source), str(dest))
                self._log(f"  📦 Перемещен: {source.name}")
            
            operation.success = True
            
        except PermissionError:
            operation.error = "Нет доступа к файлу"
            self._log(f"  ❌ Ошибка доступа: {source.name}")
        except FileNotFoundError:
            operation.error = "Файл не найден"
            self._log(f"  ❌ Файл не найден: {source.name}")
        except Exception as e:
            operation.error = str(e)
            self._log(f"  ❌ Ошибка: {source.name} - {e}")
        
        return operation
    
    @staticmethod
    def _get_unique_name(path: Path) -> Path:
        """Генерирует уникальное имя файла"""
        
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
        """Создает текстовый отчет"""
        
        lines = []
        lines.append("=" * 60)
        lines.append("ОТЧЕТ ПО АНАЛИЗУ АССЕТОВ")
        lines.append(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)
        
        # Информация о сценах
        lines.append(f"\n📁 Папка: {analysis.folder_path}")
        lines.append(f"📄 Сцен найдено: {len(analysis.scenes)}")
        
        for scene in analysis.scenes:
            lines.append(f"   • {scene.name}")
        
        # Статистика
        lines.append("\n" + "-" * 40)
        lines.append("СТАТИСТИКА")
        lines.append("-" * 40)
        
        lines.append(f"\n🎨 Текстуры в сценах: {len(analysis.used_textures)}")
        lines.append(f"📦 Прокси в сценах: {len(analysis.used_proxies)}")
        lines.append(f"📎 Другие ассеты: {len(analysis.used_other)}")
        
        lines.append(f"\n📂 Файлов в папке:")
        lines.append(f"   • Текстуры: {len(analysis.folder_textures)}")
        lines.append(f"   • Прокси: {len(analysis.folder_proxies)}")
        lines.append(f"   • Другие: {len(analysis.folder_other)}")
        
        # Результаты сравнения
        lines.append("\n" + "-" * 40)
        lines.append("РЕЗУЛЬТАТЫ АНАЛИЗА")
        lines.append("-" * 40)
        
        lines.append(f"\n✅ Связанные файлы: {len(analysis.linked_files)}")
        for f in sorted(analysis.linked_files, key=lambda x: x.name):
            lines.append(f"   • {f.name}")
        
        lines.append(f"\n⚠️ Неиспользуемые файлы: {len(analysis.unused_files)}")
        for f in sorted(analysis.unused_files, key=lambda x: x.name):
            lines.append(f"   • {f.name}")
        
        lines.append(f"\n❌ Отсутствующие файлы: {len(analysis.missing_files)}")
        for f in sorted(analysis.missing_files):
            lines.append(f"   • {Path(f).name}")
        
        # Результаты организации
        if organize_result:
            lines.append("\n" + "-" * 40)
            lines.append("РЕЗУЛЬТАТЫ ОРГАНИЗАЦИИ")
            lines.append("-" * 40)
            
            lines.append(f"\n✅ Успешно: {len(organize_result.successful_moves)}")
            lines.append(f"❌ Ошибки: {len(organize_result.failed_moves)}")
            
            if organize_result.failed_moves:
                lines.append("\nОшибки:")
                for op in organize_result.failed_moves:
                    lines.append(f"   • {op.source.name}: {op.error}")
        
        # Ошибки парсинга
        if analysis.errors:
            lines.append("\n" + "-" * 40)
            lines.append("ОШИБКИ")
            lines.append("-" * 40)
            for error in analysis.errors:
                lines.append(f"   ⚠️ {error}")
        
        lines.append("\n" + "=" * 60)
        
        return "\n".join(lines)
