"""
Модуль для автоматического обновления путей в сценах 3ds Max после перемещения файлов
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Callable, Tuple
from dataclasses import dataclass


@dataclass
class PathMapping:
    """Маппинг старого пути на новый"""
    old_path: Path
    new_path: Path


@dataclass
class UpdatePathsResult:
    """Результат обновления путей"""
    scene_path: Path
    success: bool
    paths_updated: int
    error: Optional[str] = None


class MaxPathUpdater:
    """Управляет обновлением путей в сценах 3ds Max"""
    
    def __init__(self, max_exe_path: Optional[Path] = None,
                 progress_callback: Optional[Callable[[str], None]] = None):
        """
        Args:
            max_exe_path: Путь к 3dsmax.exe. Если None, будет попытка автоопределения
            progress_callback: Функция для вывода прогресса
        """
        self.max_exe_path = max_exe_path or self._find_max_exe()
        self.progress_callback = progress_callback
        self.script_dir = Path(__file__).parent.parent / "maxscripts"
    
    def _find_max_exe(self) -> Optional[Path]:
        """Автоматически находит путь к 3dsmax.exe"""
        # Стандартные пути для разных версий
        common_paths = []
        for year in range(2025, 2019, -1):
            common_paths.extend([
                Path(f"C:\\Program Files\\Autodesk\\3ds Max {year}\\3dsmax.exe"),
                Path(f"C:\\Program Files (x86)\\Autodesk\\3ds Max {year}\\3dsmax.exe"),
            ])
        
        for path in common_paths:
            if path.exists():
                return path
        
        return None
    
    def _log(self, message: str):
        """Выводит сообщение через callback или print"""
        if self.progress_callback:
            try:
                self.progress_callback(message)
            except Exception:
                print(message)
        else:
            print(message)
    
    def check_scene_open(self, scene_path: Path) -> bool:
        """
        Проверяет, открыта ли сцена в 3ds Max.
        
        Примечание: Это простая проверка - проверяет, запущен ли процесс 3dsmax.exe.
        Более точная проверка требует OLE Automation или проверки файла блокировки.
        
        Args:
            scene_path: Путь к файлу сцены
            
        Returns:
            True если сцена может быть открыта (или точно не открыта), False если нужно предупредить
        """
        # Простая проверка: если процесс 3dsmax.exe запущен, предупреждаем
        try:
            import psutil
            for proc in psutil.process_iter(['name', 'exe']):
                try:
                    proc_name = proc.info.get('name') or ''
                    proc_exe = proc.info.get('exe') or ''
                    
                    # Проверяем имя процесса или путь к exe
                    if ('3dsmax.exe' in proc_name.lower() or 
                        (proc_exe and '3dsmax.exe' in proc_exe.lower())):
                        # Процесс найден, но мы не можем точно проверить, какая сцена открыта
                        # без OLE Automation, поэтому просто возвращаем предупреждение
                        return False
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except ImportError:
            # psutil не установлен - пропускаем проверку
            # Это нормально, функционал будет работать, но без предупреждения
            pass
        except Exception:
            # Игнорируем все остальные ошибки проверки
            pass
        
        return True
    
    def create_path_mappings_file(self, path_mappings: List[PathMapping], 
                                  output_file: Path) -> bool:
        """
        Создает файл с маппингом путей для MaxScript
        
        Формат файла:
        старый_путь|новый_путь
        старый_путь2|новый_путь2
        ...
        
        Args:
            path_mappings: Список маппингов путей
            output_file: Путь к выходному файлу
            
        Returns:
            True если успешно
        """
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for mapping in path_mappings:
                    old_str = str(mapping.old_path).replace('/', '\\')
                    new_str = str(mapping.new_path).replace('/', '\\')
                    f.write(f"{old_str}|{new_str}\n")
            
            return True
        except Exception as e:
            self._log(f"❌ Ошибка создания файла маппинга: {e}")
            return False
    
    def update_scene_paths(self, scene_path: Path,
                          path_mappings: List[PathMapping]) -> UpdatePathsResult:
        """
        Обновляет пути в указанной сцене 3ds Max
        
        Args:
            scene_path: Путь к файлу сцены .max
            path_mappings: Список маппингов путей (старый -> новый)
            
        Returns:
            UpdatePathsResult с результатами обновления
        """
        if not self.max_exe_path or not self.max_exe_path.exists():
            error = "Путь к 3dsmax.exe не найден. Укажите путь в настройках."
            self._log(f"❌ {error}")
            return UpdatePathsResult(
                scene_path=scene_path,
                success=False,
                paths_updated=0,
                error=error
            )
        
        if not scene_path.exists():
            error = f"Сцена не найдена: {scene_path}"
            self._log(f"❌ {error}")
            return UpdatePathsResult(
                scene_path=scene_path,
                success=False,
                paths_updated=0,
                error=error
            )
        
        # Проверяем, не является ли файл только для чтения
        try:
            import stat
            file_stat = scene_path.stat()
            if file_stat.st_mode & stat.S_IWRITE == 0:
                error = f"Файл сцены только для чтения: {scene_path.name}. Снимите атрибут 'только для чтения' перед обновлением путей."
                self._log(f"❌ {error}")
                return UpdatePathsResult(
                    scene_path=scene_path,
                    success=False,
                    paths_updated=0,
                    error=error
                )
        except Exception:
            # Если не удалось проверить атрибуты, продолжаем (может быть проблема с правами)
            pass
        
        if not path_mappings:
            self._log(f"⚠️ Нет путей для обновления в сцене {scene_path.name}")
            return UpdatePathsResult(
                scene_path=scene_path,
                success=True,
                paths_updated=0
            )
        
        # Проверяем, не открыта ли сцена
        if not self.check_scene_open(scene_path):
            self._log(f"⚠️ Внимание: 3ds Max запущен. Рекомендуется закрыть сцену перед обновлением путей.")
        
        # Создаем временный файл для маппинга путей
        script_path = self.script_dir / "update_paths.ms"
        if not script_path.exists():
            error = f"MaxScript не найден: {script_path}"
            self._log(f"❌ {error}")
            return UpdatePathsResult(
                scene_path=scene_path,
                success=False,
                paths_updated=0,
                error=error
            )
        
        try:
            # Создаем временный файл для маппинга
            temp_file = tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.txt',
                delete=False,
                encoding='utf-8'
            )
            temp_file_path = Path(temp_file.name)
            temp_file.close()
            
            # Записываем маппинги
            if not self.create_path_mappings_file(path_mappings, temp_file_path):
                return UpdatePathsResult(
                    scene_path=scene_path,
                    success=False,
                    paths_updated=0,
                    error="Не удалось создать файл маппинга"
                )
            
            self._log(f"🔄 Обновление путей в сцене: {scene_path.name}")
            self._log(f"   Путей для обновления: {len(path_mappings)}")
            
            # Формируем команду для запуска 3ds Max
            # Формат: 3dsmax.exe -silent -mxs "script.ms" -scene:path -mappings:path
            # В Windows используем shell=True для правильной обработки путей с пробелами
            use_shell = os.name == 'nt'
            
            if use_shell:
                # Для Windows формируем команду как строку с правильным экранированием
                max_exe_escaped = str(self.max_exe_path).replace('"', '\\"')
                script_escaped = str(script_path).replace('"', '\\"')
                scene_escaped = str(scene_path).replace('"', '\\"')
                mappings_escaped = str(temp_file_path).replace('"', '\\"')
                
                cmd_str = f'"{max_exe_escaped}" -silent -mxs "{script_escaped}" -scene:"{scene_escaped}" -mappings:"{mappings_escaped}"'
                cmd = cmd_str
            else:
                # Для других ОС используем список аргументов
                cmd = [
                    str(self.max_exe_path),
                    "-silent",
                    "-mxs", str(script_path),
                    f"-scene:{scene_path}",
                    f"-mappings:{temp_file_path}"
                ]
            
            # Запускаем 3ds Max в silent режиме
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 минут максимум
                    encoding='utf-8',
                    errors='ignore',
                    shell=use_shell
                )
                
                # Выводим лог из MaxScript (фильтруем служебные сообщения)
                if result.stdout:
                    for line in result.stdout.split('\n'):
                        line = line.strip()
                        if not line:
                            continue
                        
                        # Фильтруем служебные сообщения от 3ds Max (более агрессивная фильтрация)
                        line_lower = line.lower()
                        skip_patterns = [
                            'authorized application',
                            'firewall',
                            'port',
                            'log started',
                            'arnold',
                            'running on',
                            'nvidia driver',
                            'gpu',
                            'windows',
                            'soft limit',
                            'installing system',
                            'loading plugin',
                            'loading metadata',
                            'loaded',
                            'releasing resource',
                            'unloading',
                            'closing',
                            'arnold shutdown',
                            'pid=',
                            'amd',
                            'ryzen',
                            'processor',
                            'cores',
                            'logical',
                            'mb',
                            'gb',
                            'with',
                            'ocio',
                            '[color_manager',
                            '[metadata]',
                            '[ass]',
                            'bytes',
                            'nodes',
                            'uses arnold',
                            'system handler',
                            'mask',
                            'default',
                            'config found',
                            'applicationplugins'
                        ]
                        
                        if any(pattern in line_lower for pattern in skip_patterns):
                            continue
                        
                        # Также фильтруем строки, которые выглядят как служебные (много пробелов, таймстампы и т.д.)
                        if re.match(r'^\d{2}:\d{2}:\d{2}\s+\d+\w+\s+\|', line):
                            continue
                        
                        # Показываем только важные сообщения из MaxScript
                        important_patterns = [
                            'loading scene',
                            'scene loaded',
                            'found',
                            'loaded.*path mapping',
                            'updating path',
                            'updated',
                            'warning:',
                            'error:',
                            'error updating',
                            'failed',
                            'saving scene',
                            'scene saved',
                            'total paths updated',
                            'success'
                        ]
                        
                        if any(pattern in line_lower for pattern in important_patterns):
                            self._log(f"   {line}")
                
                if result.stderr:
                    for line in result.stderr.split('\n'):
                        line = line.strip()
                        if not line:
                            continue
                        
                        line_lower = line.lower()
                        # Фильтруем служебные сообщения из stderr
                        if any(skip in line_lower for skip in [
                            'authorized application',
                            'firewall',
                            'port',
                            'arnold',
                            'log started',
                            'loading',
                            'unloading'
                        ]):
                            continue
                        
                        # Показываем только реальные ошибки и предупреждения
                        if any(important in line_lower for important in [
                            'error',
                            'failed',
                            'warning:',
                            'exception'
                        ]):
                            self._log(f"   ⚠️ {line}")
                
                # Парсим результат из stdout
                paths_updated = 0
                save_success = False
                load_success = False
                error_messages = []
                
                for line in result.stdout.split('\n'):
                    line_stripped = line.strip()
                    
                    if 'Scene loaded successfully' in line_stripped:
                        load_success = True
                    elif 'Scene saved successfully' in line_stripped or 'Scene saved successfully (method' in line_stripped:
                        save_success = True
                    elif 'Total paths updated:' in line_stripped:
                        try:
                            paths_updated = int(line_stripped.split(':')[-1].strip())
                        except (ValueError, IndexError):
                            pass
                    elif 'Error:' in line_stripped or 'Error saving' in line_stripped or 'Failed to' in line_stripped or 'Failed to save' in line_stripped:
                        error_messages.append(line_stripped)
                    elif 'Warning:' in line_stripped and 'path mappings' not in line_stripped.lower():
                        # Важные предупреждения (но не про отсутствие маппингов)
                        if 'write permission' in line_stripped.lower() or 'cannot write' in line_stripped.lower():
                            error_messages.append(line_stripped)
                
                # Удаляем временный файл маппинга
                try:
                    temp_file_path.unlink()
                except Exception:
                    pass
                
                # Проверяем результат
                if result.returncode != 0:
                    # 3ds Max вернул код ошибки
                    error_msg = f"3ds Max вернул код ошибки: {result.returncode}"
                    if error_messages:
                        error_msg += f" ({'; '.join(error_messages[:2])})"
                    self._log(f"   ❌ {error_msg}")
                    return UpdatePathsResult(
                        scene_path=scene_path,
                        success=False,
                        paths_updated=paths_updated,
                        error=error_msg
                    )
                
                # Проверяем, была ли сцена сохранена
                if save_success:
                    self._log(f"   ✅ Обновлено путей: {paths_updated}, сцена сохранена")
                    return UpdatePathsResult(
                        scene_path=scene_path,
                        success=True,
                        paths_updated=paths_updated
                    )
                elif load_success:
                    # Сцена загружена, но не сохранена - это ошибка
                    error_msg = "Сцена загружена, но не сохранена. Возможно, нет прав на запись, файл только для чтения, или файл заблокирован другим процессом."
                    if error_messages:
                        error_msg += f" Ошибки: {'; '.join(error_messages[:2])}"
                    self._log(f"   ⚠️ {error_msg}")
                    self._log(f"   Обновлено путей: {paths_updated} (но сцена не сохранена)")
                    return UpdatePathsResult(
                        scene_path=scene_path,
                        success=False,
                        paths_updated=paths_updated,
                        error=error_msg
                    )
                else:
                    # Сцена даже не загрузилась
                    error_msg = "Не удалось загрузить сцену"
                    if error_messages:
                        error_msg += f": {'; '.join(error_messages[:2])}"
                    self._log(f"   ❌ {error_msg}")
                    return UpdatePathsResult(
                        scene_path=scene_path,
                        success=False,
                        paths_updated=0,
                        error=error_msg
                    )
                    
            except subprocess.TimeoutExpired:
                error_msg = "Превышено время ожидания обновления путей"
                self._log(f"❌ {error_msg}")
                # Удаляем временный файл
                try:
                    temp_file_path.unlink()
                except Exception:
                    pass
                return UpdatePathsResult(
                    scene_path=scene_path,
                    success=False,
                    paths_updated=0,
                    error=error_msg
                )
            except Exception as e:
                error_msg = f"Ошибка запуска 3ds Max: {e}"
                self._log(f"❌ {error_msg}")
                # Удаляем временный файл
                try:
                    temp_file_path.unlink()
                except Exception:
                    pass
                return UpdatePathsResult(
                    scene_path=scene_path,
                    success=False,
                    paths_updated=0,
                    error=error_msg
                )
                
        except Exception as e:
            error_msg = f"Ошибка обновления путей: {e}"
            self._log(f"❌ {error_msg}")
            return UpdatePathsResult(
                scene_path=scene_path,
                success=False,
                paths_updated=0,
                error=error_msg
            )
    
    def update_multiple_scenes(self, scenes: List[Path],
                              path_mappings_by_scene: Dict[Path, List[PathMapping]]) -> List[UpdatePathsResult]:
        """
        Обновляет пути в нескольких сценах
        
        Args:
            scenes: Список путей к сценам
            path_mappings_by_scene: Словарь {scene_path: [path_mappings]}
            
        Returns:
            Список результатов обновления
        """
        results = []
        
        for scene in scenes:
            mappings = path_mappings_by_scene.get(scene, [])
            result = self.update_scene_paths(scene, mappings)
            results.append(result)
        
        return results
    
    def create_mappings_from_move_operations(self, 
                                           move_operations: List,
                                           scene_path: Path) -> List[PathMapping]:
        """
        Создает маппинги путей из операций перемещения файлов
        
        Args:
            move_operations: Список операций перемещения (MoveOperation или dict с source/destination)
            scene_path: Путь к сцене (для фильтрации только релевантных операций)
            
        Returns:
            Список маппингов путей
        """
        mappings = []
        
        # Получаем все возможные варианты старого пути (может быть относительный, абсолютный)
        scene_folder = scene_path.parent
        
        for op in move_operations:
            try:
                # Извлекаем source и destination из операции
                if hasattr(op, 'source') and hasattr(op, 'destination'):
                    old_path = Path(op.source)
                    new_path = Path(op.destination)
                elif isinstance(op, dict):
                    old_path = Path(op.get('source', ''))
                    new_path = Path(op.get('destination', ''))
                else:
                    continue
                
                if not old_path.exists() and new_path.exists():
                    # Файл был перемещен, создаем маппинг
                    # Добавляем разные варианты старого пути
                    mappings.append(PathMapping(
                        old_path=old_path,
                        new_path=new_path
                    ))
                    
                    # Добавляем относительный путь от папки сцены
                    try:
                        old_rel = old_path.relative_to(scene_folder)
                        mappings.append(PathMapping(
                            old_path=scene_folder / old_rel,
                            new_path=new_path
                        ))
                    except ValueError:
                        pass
                    
                    # Добавляем только имя файла (если совпадает)
                    if old_path.name == new_path.name:
                        # Создаем маппинг для всех возможных путей с этим именем
                        mappings.append(PathMapping(
                            old_path=old_path.parent / old_path.name,
                            new_path=new_path
                        ))
                        
            except Exception as e:
                # Игнорируем ошибки обработки отдельных операций
                continue
        
        # Удаляем дубликаты
        unique_mappings = []
        seen = set()
        for mapping in mappings:
            key = (str(mapping.old_path), str(mapping.new_path))
            if key not in seen:
                seen.add(key)
                unique_mappings.append(mapping)
        
        return unique_mappings
