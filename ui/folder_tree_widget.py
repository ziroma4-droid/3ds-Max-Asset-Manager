"""
Виджет для отображения структуры папок с цветовой индикацией
"""

from pathlib import Path
from typing import Optional, Dict, Set
from collections import defaultdict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QTreeWidget, QTreeWidgetItem, QPushButton
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QIcon

import sys
from pathlib import Path

# Добавляем путь к core
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.asset_analyzer import AnalysisResult, FileInfo


class FolderTreeWidget(QWidget):
    """Виджет для отображения структуры папок с файлами"""
    
    def __init__(self):
        super().__init__()
        self.current_analysis: Optional[AnalysisResult] = None
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Заголовок
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("📁 Структура папок и файлов"))
        
        expand_all_btn = QPushButton("Развернуть все")
        expand_all_btn.clicked.connect(self.expand_all)
        header_layout.addWidget(expand_all_btn)
        
        collapse_all_btn = QPushButton("Свернуть все")
        collapse_all_btn.clicked.connect(self.collapse_all)
        header_layout.addWidget(collapse_all_btn)
        
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # Легенда
        legend_group = QGroupBox("Легенда")
        legend_layout = QHBoxLayout(legend_group)
        legend_layout.setSpacing(20)
        
        legend_layout.addWidget(self._create_legend_item("✅", "Используется", QColor(76, 175, 80)))
        legend_layout.addWidget(self._create_legend_item("⚠️", "Не используется", QColor(244, 67, 54)))
        legend_layout.addWidget(self._create_legend_item("❌", "Отсутствует", QColor(158, 158, 158)))
        
        legend_layout.addStretch()
        layout.addWidget(legend_group)
        
        # Дерево
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Имя", "Тип", "Статус", "Размер"])
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 100)
        self.tree.setColumnWidth(2, 150)
        self.tree.setColumnWidth(3, 100)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        layout.addWidget(self.tree)
    
    def _create_legend_item(self, icon: str, text: str, color: QColor) -> QWidget:
        """Создает элемент легенды"""
        from PyQt6.QtWidgets import QLabel
        
        label = QLabel(f"{icon} {text}")
        label.setStyleSheet(f"color: rgb({color.red()}, {color.green()}, {color.blue()});")
        return label
    
    def update_tree(self, analysis: AnalysisResult):
        """Обновляет дерево на основе результатов анализа"""
        self.current_analysis = analysis
        self.tree.clear()
        
        if not analysis.all_files_info:
            return
        
        # Группируем файлы по папкам
        files_by_folder: Dict[str, list] = defaultdict(list)
        for file_info in analysis.all_files_info.values():
            files_by_folder[file_info.folder].append(file_info)
        
        # Создаем корневой элемент
        root_item = QTreeWidgetItem(self.tree)
        root_item.setText(0, str(analysis.folder_path))
        root_item.setExpanded(True)
        
        # Добавляем папки
        for folder_name in sorted(files_by_folder.keys()):
            folder_item = self._create_folder_item(root_item, folder_name, files_by_folder[folder_name], analysis)
        
        # Добавляем отсутствующие файлы
        if analysis.missing_files:
            missing_item = QTreeWidgetItem(root_item)
            missing_item.setText(0, "❌ Отсутствующие файлы")
            missing_item.setForeground(0, QBrush(QColor(158, 158, 158)))
            missing_item.setExpanded(False)
            
            for missing_path in sorted(analysis.missing_files):
                file_item = QTreeWidgetItem(missing_item)
                try:
                    file_name = Path(missing_path).name
                    file_item.setText(0, file_name)
                    file_item.setText(1, Path(missing_path).suffix)
                    file_item.setText(2, "❌ Отсутствует")
                    file_item.setForeground(2, QBrush(QColor(158, 158, 158)))
                    file_item.setForeground(0, QBrush(QColor(158, 158, 158)))
                except Exception:
                    file_item.setText(0, str(missing_path))
                    file_item.setText(2, "❌ Отсутствует")
                    file_item.setForeground(2, QBrush(QColor(158, 158, 158)))
        
        self.tree.expandAll()
    
    def _create_folder_item(self, parent: QTreeWidgetItem, folder_name: str, 
                           files: list, analysis: AnalysisResult) -> QTreeWidgetItem:
        """Создает элемент папки с файлами"""
        folder_item = QTreeWidgetItem(parent)
        folder_item.setText(0, f"📁 {folder_name}")
        folder_item.setExpanded(False)
        
        # Статистика папки
        used_count = sum(1 for f in files if f.is_used)
        unused_count = len(files) - used_count
        total_size = 0
        
        for file_info in files:
            try:
                if file_info.path.exists():
                    total_size += file_info.path.stat().st_size
            except (OSError, AttributeError):
                pass
        
        folder_item.setText(1, f"{len(files)} файлов")
        folder_item.setText(2, f"✅ {used_count} | ⚠️ {unused_count}")
        
        # Добавляем файлы
        for file_info in sorted(files, key=lambda x: x.name):
            file_item = self._create_file_item(folder_item, file_info, analysis)
        
        return folder_item
    
    def _create_file_item(self, parent: QTreeWidgetItem, file_info: FileInfo, 
                          analysis: AnalysisResult) -> QTreeWidgetItem:
        """Создает элемент файла"""
        file_item = QTreeWidgetItem(parent)
        
        # Имя файла
        file_item.setText(0, file_info.name)
        
        # Тип
        type_emoji = {
            'texture': '🎨',
            'proxy': '📦',
            'other': '📎'
        }
        file_type = type_emoji.get(file_info.file_type, '📄')
        file_item.setText(1, f"{file_type} {file_info.file_type}")
        
        # Статус и цвет
        if file_info.is_used:
            file_item.setText(2, "✅ Используется")
            file_item.setForeground(2, QBrush(QColor(76, 175, 80)))  # Зеленый
            file_item.setForeground(0, QBrush(QColor(76, 175, 80)))
            
            # Показываем в каких сценах используется
            if file_info.used_in_scenes:
                scenes_text = ", ".join([Path(s).name for s in file_info.used_in_scenes[:2]])
                if len(file_info.used_in_scenes) > 2:
                    scenes_text += f" (+{len(file_info.used_in_scenes) - 2})"
                file_item.setToolTip(2, f"Используется в: {scenes_text}")
        else:
            file_item.setText(2, "⚠️ Не используется")
            file_item.setForeground(2, QBrush(QColor(244, 67, 54)))  # Красный
            file_item.setForeground(0, QBrush(QColor(244, 67, 54)))
        
        # Размер
        try:
            if file_info.path.exists():
                size = file_info.path.stat().st_size
                file_item.setText(3, self._format_size(size))
            else:
                file_item.setText(3, "—")
                file_item.setForeground(3, QBrush(QColor(158, 158, 158)))
        except (OSError, AttributeError):
            file_item.setText(3, "—")
        
        return file_item
    
    def _format_size(self, size_bytes: int) -> str:
        """Форматирует размер файла"""
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} ГБ"
    
    def expand_all(self):
        """Разворачивает все элементы дерева"""
        self.tree.expandAll()
    
    def collapse_all(self):
        """Сворачивает все элементы дерева"""
        self.tree.collapseAll()
        # Оставляем корневой элемент развернутым
        root = self.tree.topLevelItem(0)
        if root:
            root.setExpanded(True)

