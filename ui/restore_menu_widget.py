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
        
        actions_layout.addStretch()
        layout.addLayout(actions_layout)
    
    def update_folders_list(self):
        """Обновляет список папок"""
        self.folders_list.clear()
        
        folders = self.operation_history.get_folders_with_operations()
        
        if not folders:
            item = QListWidgetItem("Нет папок с операциями для восстановления")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.folders_list.addItem(item)
            self.restore_btn.setEnabled(False)
            return
        
        for base_folder, info in sorted(folders.items(), 
                                       key=lambda x: x[1]['timestamp'], 
                                       reverse=True):
            try:
                timestamp = datetime.fromisoformat(info['timestamp'])
                timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                
                # Формируем текст элемента
                folder_name = base_folder.name if base_folder.name else str(base_folder)
                folder_path = str(base_folder)
                
                # Обрезаем длинный путь
                if len(folder_path) > 80:
                    folder_path = "..." + folder_path[-77:]
                
                text = f"📁 {folder_name}\n"
                text += f"   Путь: {folder_path}\n"
                text += f"   Операций: {info['operations_count']}\n"
                text += f"   Дата: {timestamp_str}"
                
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, {
                    'base_folder': base_folder,
                    'backup_id': info['backup_id'],
                    'info': info
                })
                self.folders_list.addItem(item)
            except Exception as e:
                print(f"Ошибка при добавлении папки в список: {e}")
        
        # Подключаем сигнал выбора
        self.folders_list.itemSelectionChanged.connect(
            lambda: self.restore_btn.setEnabled(
                len(self.folders_list.selectedItems()) > 0
            )
        )
    
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
        msg = f"⚠️ ВОССТАНОВЛЕНИЕ ПАПКИ\n\n"
        msg += f"Папка: {base_folder.name}\n"
        msg += f"Путь: {base_folder}\n\n"
        msg += f"Будет восстановлено:\n"
        msg += f"• Файлов: {info['operations_count']}\n"
        msg += f"• Дата операции: {datetime.fromisoformat(info['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        msg += f"⚠️ ВНИМАНИЕ: Все текущие изменения в папке будут перезаписаны!\n\n"
        msg += f"Вы уверены, что хотите восстановить эту папку?"
        
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

