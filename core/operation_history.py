"""
История операций с возможностью отмены
"""

import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum


class OperationType(Enum):
    """Тип операции"""
    MOVE = "move"
    COPY = "copy"
    DELETE = "delete"
    RESTORE = "restore"


@dataclass
class Operation:
    """Операция с файлом"""
    id: str
    type: OperationType
    source: Path
    destination: Optional[Path] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    success: bool = False
    error: Optional[str] = None
    backup_id: Optional[str] = None
    base_folder: Optional[Path] = None  # Корневая папка проекта
    
    def to_dict(self) -> Dict:
        """Преобразует в словарь для сохранения"""
        data = asdict(self)
        data['type'] = self.type.value
        data['source'] = str(self.source)
        if self.destination:
            data['destination'] = str(self.destination)
        if self.base_folder:
            data['base_folder'] = str(self.base_folder)
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Operation':
        """Создает из словаря"""
        op_type = OperationType(data['type'])
        source = Path(data['source'])
        destination = Path(data['destination']) if data.get('destination') else None
        base_folder = Path(data['base_folder']) if data.get('base_folder') else None
        
        return cls(
            id=data['id'],
            type=op_type,
            source=source,
            destination=destination,
            timestamp=data.get('timestamp', datetime.now().isoformat()),
            success=data.get('success', False),
            error=data.get('error'),
            backup_id=data.get('backup_id'),
            base_folder=base_folder
        )


class OperationHistory:
    """Управляет историей операций"""
    
    def __init__(self, history_file: Optional[Path] = None):
        """
        Args:
            history_file: Путь к файлу истории (если None, используется временный файл)
        """
        if history_file is None:
            import tempfile
            temp_dir = Path(tempfile.gettempdir())
            history_file = temp_dir / "MaxAssetManager_history.json"
        
        self.history_file = Path(history_file)
        self.operations: List[Operation] = []
        self._load_history()
    
    def _load_history(self):
        """Загружает историю из файла"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.operations = [Operation.from_dict(op) for op in data]
            except Exception:
                self.operations = []
    
    def _save_history(self):
        """Сохраняет историю в файл"""
        try:
            data = [op.to_dict() for op in self.operations]
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def add_operation(self, operation: Operation):
        """Добавляет операцию в историю"""
        self.operations.append(operation)
        self._save_history()
    
    def get_recent_operations(self, limit: int = 50) -> List[Operation]:
        """Возвращает последние операции"""
        return self.operations[-limit:]
    
    def get_operations_by_backup_id(self, backup_id: str) -> List[Operation]:
        """Возвращает операции по идентификатору резервной копии"""
        return [op for op in self.operations if op.backup_id == backup_id]
    
    def can_undo(self) -> bool:
        """Проверяет, можно ли отменить последнюю операцию"""
        if not self.operations:
            return False
        
        last_op = self.operations[-1]
        return last_op.success and last_op.type != OperationType.RESTORE
    
    def get_last_operation(self) -> Optional[Operation]:
        """Возвращает последнюю операцию"""
        return self.operations[-1] if self.operations else None
    
    def clear_history(self):
        """Очищает историю"""
        self.operations = []
        self._save_history()
    
    def get_folders_with_operations(self) -> List[Dict]:
        """
        Возвращает список всех операций организации (каждая операция - отдельная запись)
        Группирует операции по backup_id (каждая операция организации - отдельная запись)
        
        Returns:
            Список словарей: [{'base_folder': Path, 'backup_id': str, 'timestamp': str, 'operations_count': int, 'operations': list}, ...]
        """
        # Группируем операции по backup_id (каждая операция организации - отдельная запись)
        backup_groups = {}
        
        for op in self.operations:
            if not op.success or not op.backup_id or not op.base_folder:
                continue
            
            backup_id = op.backup_id
            
            if backup_id not in backup_groups:
                backup_groups[backup_id] = {
                    'base_folder': Path(op.base_folder),
                    'backup_id': backup_id,
                    'timestamp': op.timestamp,
                    'operations_count': 0,
                    'operations': []
                }
            
            backup_groups[backup_id]['operations_count'] += 1
            backup_groups[backup_id]['operations'].append(op)
            
            # Обновляем timestamp на самый поздний
            if op.timestamp > backup_groups[backup_id]['timestamp']:
                backup_groups[backup_id]['timestamp'] = op.timestamp
        
        # Возвращаем список всех операций
        return list(backup_groups.values())
    
    def get_operations_by_backup_id(self, backup_id: str) -> List[Operation]:
        """Возвращает все операции для указанного backup_id"""
        return [op for op in self.operations 
                if op.backup_id == backup_id and op.success]
    
    def get_operations_by_folder(self, base_folder: Path) -> List[Operation]:
        """Возвращает все операции для указанной корневой папки"""
        return [op for op in self.operations 
                if op.base_folder == base_folder and op.success and op.backup_id]
    
    def delete_operations_by_folder(self, base_folder: Path) -> int:
        """
        Удаляет все операции для указанной корневой папки
        
        Args:
            base_folder: Корневая папка проекта
            
        Returns:
            Количество удаленных операций
        """
        base_folder = Path(base_folder)
        initial_count = len(self.operations)
        
        # Удаляем все операции для этой папки
        self.operations = [op for op in self.operations 
                          if not (op.base_folder == base_folder and op.success and op.backup_id)]
        
        deleted_count = initial_count - len(self.operations)
        
        if deleted_count > 0:
            self._save_history()
        
        return deleted_count

