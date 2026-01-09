"""
Виджет меню для восстановления папок
"""

import sys
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QGroupBox,
    QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

# Добавляем путь к core
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.operation_history import OperationHistory
from core.backup_manager import BackupManager


class RestoreMenuWidget(QWidget):
    """Виджет для отображения меню восстановления папок"""
    
    def __init__(self, operation_history: OperationHistory):
        super().__init__()
        self.operation_history = operation_history
        self.init_ui()
        self.update_folders_list()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Заголовок
        header_label = QLabel("↩️ Восстановление папок из резервных копий")
        header_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(header_label)
        
        info_label = QLabel(
            "Выберите папку для восстановления в исходное состояние.\n"
            "Все файлы будут восстановлены из резервной копии."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Список папок
        folders_group = QGroupBox("📁 Папки с операциями")
        folders_layout = QVBoxLayout(folders_group)
        
        self.folders_list = QListWidget()
        self.folders_list.setMinimumHeight(200)
        folders_layout.addWidget(self.folders_list)
        
        refresh_btn = QPushButton("🔄 Обновить список")
        refresh_btn.clicked.connect(self.update_folders_list)
        folders_layout.addWidget(refresh_btn)
        
        layout.addWidget(folders_group)
        
        # Кнопки действий
        actions_layout = QHBoxLayout()
        
        self.restore_btn = QPushButton("↩️ Восстановить выбранную папку")
        self.restore_btn.setMinimumHeight(40)
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self.restore_selected_folder)
        actions_layout.addWidget(self.restore_btn)
        
        self.delete_btn = QPushButton("🗑️ Удалить выбранную позицию")
        self.delete_btn.setMinimumHeight(40)
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self.delete_selected_folder)
        actions_layout.addWidget(self.delete_btn)
        
        actions_layout.addStretch()
        layout.addLayout(actions_layout)
    
    def update_folders_list(self):
        """Обновляет список операций (каждая операция организации - отдельная запись)"""
        self.folders_list.clear()
        
        operations_list = self.operation_history.get_folders_with_operations()
        
        if not operations_list:
            item = QListWidgetItem("Нет операций для восстановления")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.folders_list.addItem(item)
            self.restore_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            return
        
        # Сортируем по дате (самые новые сначала)
        operations_list.sort(key=lambda x: x['timestamp'], reverse=True)
        
        for info in operations_list:
            base_folder = info['base_folder']
            backup_id = info['backup_id']
            try:
                timestamp = datetime.fromisoformat(info['timestamp'])
                timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                
                # Формируем текст элемента
                folder_name = base_folder.name if base_folder.name else str(base_folder)
                folder_path = str(base_folder)
                
                # Обрезаем длинный путь
                if len(folder_path) > 80:
                    folder_path = "..." + folder_path[-77:]
                
                # Обрезаем backup_id для отображения
                backup_id_short = backup_id[:8] + "..." if len(backup_id) > 8 else backup_id
                
                text = f"📁 {folder_name}\n"
                text += f"   Путь: {folder_path}\n"
                text += f"   Операций: {info['operations_count']}\n"
                text += f"   ID: {backup_id_short}\n"
                text += f"   Дата: {timestamp_str}"
                
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, {
                    'base_folder': base_folder,
                    'backup_id': backup_id,
                    'info': info
                })
                self.folders_list.addItem(item)
            except Exception as e:
                print(f"Ошибка при добавлении операции в список: {e}")
        
        # Подключаем сигнал выбора
        def update_buttons():
            has_selection = len(self.folders_list.selectedItems()) > 0
            self.restore_btn.setEnabled(has_selection)
            self.delete_btn.setEnabled(has_selection)
        
        self.folders_list.itemSelectionChanged.connect(update_buttons)
    
    def restore_selected_folder(self):
        """Восстанавливает выбранную папку"""
        selected_items = self.folders_list.selectedItems()
        if not selected_items:
            return
        
        item = selected_items[0]
        data = item.data(Qt.ItemDataRole.UserRole)
        
        if not data:
            return
        
        base_folder = data['base_folder']
        backup_id = data['backup_id']
        info = data['info']
        
        # Подтверждение
        backup_id_short = backup_id[:8] + "..." if len(backup_id) > 8 else backup_id
        msg = f"⚠️ ВОССТАНОВЛЕНИЕ ОПЕРАЦИИ\n\n"
        msg += f"Папка: {base_folder.name}\n"
        msg += f"Путь: {base_folder}\n"
        msg += f"ID операции: {backup_id_short}\n\n"
        msg += f"Будет восстановлено:\n"
        msg += f"• Файлов: {info['operations_count']}\n"
        msg += f"• Дата операции: {datetime.fromisoformat(info['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        msg += f"⚠️ ВНИМАНИЕ: Все текущие изменения в папке будут перезаписаны!\n\n"
        msg += f"Вы уверены, что хотите восстановить эту операцию?"
        
        reply = QMessageBox.warning(
            self, "⚠️ Подтверждение восстановления", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Восстанавливаем
        try:
            backup_manager = BackupManager(base_folder)
            success = backup_manager.restore_backup(backup_id)
            
            if success:
                QMessageBox.information(
                    self, "Успешно",
                    f"Папка '{base_folder.name}' успешно восстановлена!\n\n"
                    f"Восстановлено файлов: {info['operations_count']}"
                )
                # Обновляем список
                self.update_folders_list()
            else:
                QMessageBox.warning(
                    self, "Ошибка",
                    "Не удалось восстановить папку.\n"
                    "Возможно, резервная копия была удалена или повреждена."
                )
        except Exception as e:
            QMessageBox.critical(
                self, "Ошибка",
                f"Произошла ошибка при восстановлении:\n{str(e)}"
            )
    
    def delete_selected_folder(self):
        """Удаляет выбранную позицию из истории и временных файлов"""
        selected_items = self.folders_list.selectedItems()
        if not selected_items:
            return
        
        item = selected_items[0]
        data = item.data(Qt.ItemDataRole.UserRole)
        
        if not data:
            return
        
        base_folder = data['base_folder']
        backup_id = data['backup_id']
        info = data['info']
        
        # Подтверждение
        backup_id_short = backup_id[:8] + "..." if len(backup_id) > 8 else backup_id
        msg = f"⚠️ УДАЛЕНИЕ ОПЕРАЦИИ ИЗ ИСТОРИИ\n\n"
        msg += f"Папка: {base_folder.name}\n"
        msg += f"Путь: {base_folder}\n"
        msg += f"ID операции: {backup_id_short}\n\n"
        msg += f"Будет удалено:\n"
        msg += f"• Операций из истории: {info['operations_count']}\n"
        msg += f"• Резервная копия: {backup_id_short}\n"
        msg += f"• Дата операции: {datetime.fromisoformat(info['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        msg += f"⚠️ ВНИМАНИЕ: Это действие нельзя отменить!\n"
        msg += f"Резервная копия и история операций будут удалены безвозвратно.\n\n"
        msg += f"Вы уверены, что хотите удалить эту операцию?"
        
        reply = QMessageBox.warning(
            self, "⚠️ Подтверждение удаления", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Удаляем
        try:
            # Удаляем из истории операций только для конкретного backup_id
            operations_to_delete = self.operation_history.get_operations_by_backup_id(backup_id)
            deleted_ops = 0
            for op in operations_to_delete:
                if op in self.operation_history.operations:
                    self.operation_history.operations.remove(op)
                    deleted_ops += 1
            if deleted_ops > 0:
                self.operation_history._save_history()
            
            # Удаляем резервную копию
            backup_manager = BackupManager(base_folder)
            backup_deleted = backup_manager.delete_backup(backup_id)
            
            if deleted_ops > 0 or backup_deleted:
                QMessageBox.information(
                    self, "Успешно",
                    f"Позиция успешно удалена!\n\n"
                    f"• Удалено операций из истории: {deleted_ops}\n"
                    f"• Резервная копия удалена: {'Да' if backup_deleted else 'Нет'}"
                )
                # Обновляем список
                self.update_folders_list()
            else:
                QMessageBox.warning(
                    self, "Предупреждение",
                    "Не удалось удалить позицию.\n"
                    "Возможно, она уже была удалена."
                )
        except Exception as e:
            QMessageBox.critical(
                self, "Ошибка",
                f"Произошла ошибка при удалении:\n{str(e)}"
            )

