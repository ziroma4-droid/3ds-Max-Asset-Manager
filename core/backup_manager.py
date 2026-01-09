"""
Менеджер резервного копирования
Создает резервные копии файлов во временную папку и автоматически удаляет старые
"""

import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import json


class BackupManager:
    """Управляет резервным копированием файлов"""
    
    def __init__(self, base_folder: Path, retention_days: int = 7):
        """
        Args:
            base_folder: Базовая папка проекта
            retention_days: Количество дней хранения резервных копий
        """
        self.base_folder = Path(base_folder)
        self.retention_days = retention_days
        
        # Создаем папку для резервных копий во временной директории
        temp_dir = Path(tempfile.gettempdir())
        self.backup_root = temp_dir / "MaxAssetManager_Backups"
        self.backup_root.mkdir(exist_ok=True)
        
        # Папка для текущего проекта
        project_hash = str(abs(hash(str(self.base_folder))))
        self.backup_folder = self.backup_root / project_hash
        self.backup_folder.mkdir(exist_ok=True)
        
        # Файл метаданных
        self.metadata_file = self.backup_folder / "backup_metadata.json"
        self.metadata = self._load_metadata()
    
    def _load_metadata(self) -> Dict:
        """Загружает метаданные резервных копий"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _save_metadata(self):
        """Сохраняет метаданные"""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def create_backup(self, file_path: Path, backup_id: str) -> Optional[Path]:
        """
        Создает резервную копию файла
        
        Args:
            file_path: Путь к файлу для резервного копирования
            backup_id: Уникальный идентификатор операции резервного копирования
            
        Returns:
            Путь к резервной копии или None при ошибке
        """
        if not file_path.exists():
            return None
        
        try:
            # Создаем папку для этой операции резервного копирования
            backup_op_folder = self.backup_folder / backup_id
            backup_op_folder.mkdir(exist_ok=True)
            
            # Сохраняем относительный путь от базовой папки
            try:
                rel_path = file_path.relative_to(self.base_folder)
            except ValueError:
                # Если файл вне базовой папки, используем полный путь
                rel_path = Path(file_path.name)
            
            # Создаем структуру папок в резервной копии
            backup_file_path = backup_op_folder / rel_path
            backup_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Копируем файл
            shutil.copy2(str(file_path), str(backup_file_path))
            
            # Сохраняем метаданные
            if backup_id not in self.metadata:
                self.metadata[backup_id] = {
                    'timestamp': datetime.now().isoformat(),
                    'files': []
                }
            
            self.metadata[backup_id]['files'].append({
                'original': str(file_path),
                'backup': str(backup_file_path),
                'relative': str(rel_path)
            })
            
            self._save_metadata()
            
            return backup_file_path
            
        except Exception as e:
            print(f"Ошибка резервного копирования {file_path}: {e}")
            return None
    
    def restore_backup(self, backup_id: str) -> bool:
        """
        Восстанавливает файлы из резервной копии
        
        Args:
            backup_id: Идентификатор операции резервного копирования
            
        Returns:
            True если успешно
        """
        if backup_id not in self.metadata:
            return False
        
        try:
            backup_op_folder = self.backup_folder / backup_id
            if not backup_op_folder.exists():
                return False
            
            restored_count = 0
            for file_info in self.metadata[backup_id]['files']:
                backup_path = Path(file_info['backup'])
                original_path = Path(file_info['original'])
                
                if backup_path.exists():
                    # Восстанавливаем файл
                    original_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(backup_path), str(original_path))
                    restored_count += 1
            
            return restored_count > 0
            
        except Exception as e:
            print(f"Ошибка восстановления из резервной копии {backup_id}: {e}")
            return False
    
    def get_backup_info(self, backup_id: str) -> Optional[Dict]:
        """Возвращает информацию о резервной копии"""
        if backup_id not in self.metadata:
            return None
        
        info = self.metadata[backup_id].copy()
        info['backup_id'] = backup_id
        info['file_count'] = len(info.get('files', []))
        return info
    
    def delete_backup(self, backup_id: str) -> bool:
        """Удаляет резервную копию"""
        try:
            backup_op_folder = self.backup_folder / backup_id
            if backup_op_folder.exists():
                shutil.rmtree(backup_op_folder)
            
            if backup_id in self.metadata:
                del self.metadata[backup_id]
                self._save_metadata()
            
            return True
        except Exception:
            return False
    
    def cleanup_old_backups(self):
        """Удаляет старые резервные копии"""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        backups_to_delete = []
        for backup_id, info in list(self.metadata.items()):
            try:
                timestamp = datetime.fromisoformat(info['timestamp'])
                if timestamp < cutoff_date:
                    backups_to_delete.append(backup_id)
            except Exception:
                backups_to_delete.append(backup_id)
        
        for backup_id in backups_to_delete:
            self.delete_backup(backup_id)
    
    def get_backup_size(self, backup_id: str) -> int:
        """Возвращает размер резервной копии в байтах"""
        if backup_id not in self.metadata:
            return 0
        
        try:
            backup_op_folder = self.backup_folder / backup_id
            if not backup_op_folder.exists():
                return 0
            
            total_size = 0
            for file_path in backup_op_folder.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
            
            return total_size
        except Exception:
            return 0

