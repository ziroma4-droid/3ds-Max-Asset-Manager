"""
Виджет статистики ассетов
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, List
from collections import defaultdict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QScrollArea
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont

# Добавляем путь к core
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.asset_analyzer import AnalysisResult, FileInfo


class StatisticsWidget(QWidget):
    """Виджет для отображения статистики"""
    
    def __init__(self):
        super().__init__()
        self.current_analysis: Optional[AnalysisResult] = None
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # === Общая статистика ===
        stats_group = QGroupBox("📊 Общая статистика")
        stats_layout = QVBoxLayout(stats_group)
        
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setFont(QFont("Consolas", 10))
        self.stats_text.setMaximumHeight(200)
        self.stats_text.setPlainText("Выполните анализ для отображения статистики")
        stats_layout.addWidget(self.stats_text)
        
        layout.addWidget(stats_group)
        
        # === Таблица детальной статистики по папкам ===
        table_group = QGroupBox("📋 Детальная статистика по папкам")
        table_layout = QVBoxLayout(table_group)
        
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(6)
        self.stats_table.setHorizontalHeaderLabels([
            "Папка", "Всего", "Используется", "Не используется", 
            "Общий размер", "Средний размер"
        ])
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.stats_table.setAlternatingRowColors(True)
        table_layout.addWidget(self.stats_table)
        
        layout.addWidget(table_group)
    
    def update_statistics(self, analysis: AnalysisResult):
        """Обновляет статистику на основе результатов анализа"""
        self.current_analysis = analysis
        
        # Обновляем общую статистику
        self._update_general_stats(analysis)
        
        # Обновляем таблицу
        self._update_stats_table(analysis)
    
    def _update_general_stats(self, analysis: AnalysisResult):
        """Обновляет общую статистику"""
        total_size = 0
        used_size = 0
        unused_size = 0
        file_count = 0
        used_count = 0
        
        # Считаем размеры файлов
        textures_size = 0
        proxies_size = 0
        other_size = 0
        
        for file_info in analysis.all_files_info.values():
            try:
                if file_info.path.exists():
                    size = file_info.path.stat().st_size
                    total_size += size
                    file_count += 1
                    
                    if file_info.is_used:
                        used_size += size
                        used_count += 1
                    else:
                        unused_size += size
                    
                    # По типам
                    if file_info.file_type == 'texture':
                        textures_size += size
                    elif file_info.file_type == 'proxy':
                        proxies_size += size
                    else:
                        other_size += size
            except (OSError, AttributeError):
                pass
        
        # Форматируем размеры
        def format_size(size_bytes):
            for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
                if size_bytes < 1024.0:
                    return f"{size_bytes:.2f} {unit}"
                size_bytes /= 1024.0
            return f"{size_bytes:.2f} ПБ"
        
        avg_size = total_size / file_count if file_count > 0 else 0
        avg_used_size = used_size / used_count if used_count > 0 else 0
        avg_unused_size = unused_size / (file_count - used_count) if (file_count - used_count) > 0 else 0
        
        used_pct = (used_count / file_count * 100) if file_count > 0 else 0
        used_size_pct = (used_size / total_size * 100) if total_size > 0 else 0
        
        stats_text = f"""═══════════════════════════════════════════════════════════
📊 ОБЩАЯ СТАТИСТИКА
═══════════════════════════════════════════════════════════

📄 СЦЕНЫ:
   • Всего сцен: {len(analysis.scenes)}
   • Проанализировано: {len(analysis.scene_details)}

📦 АССЕТЫ В СЦЕНАХ:
   • 🎨 Текстур: {len(analysis.used_textures)}
   • 📦 Прокси: {len(analysis.used_proxies)}
   • 📎 Других: {len(analysis.used_other)}
   • Всего ассетов: {len(analysis.all_used_assets)}

📂 ФАЙЛЫ В ПАПКЕ:
   • Всего файлов: {file_count}
   • ✅ Используется: {used_count} ({used_pct:.1f}%)
   • ⚠️ Не используется: {file_count - used_count}
   • ❌ Отсутствует: {len(analysis.missing_files)}

💾 РАЗМЕРЫ ФАЙЛОВ:
   • Общий размер: {format_size(total_size)}
   • ✅ Используется: {format_size(used_size)} ({used_size_pct:.1f}%)
   • ⚠️ Не используется: {format_size(unused_size)}
   
   По типам:
   • 🎨 Текстур: {format_size(textures_size)}
   • 📦 Прокси: {format_size(proxies_size)}
   • 📎 Других: {format_size(other_size)}

📊 СРЕДНИЕ РАЗМЕРЫ:
   • Средний размер файла: {format_size(avg_size)}
   • Средний размер используемого: {format_size(avg_used_size)}
   • Средний размер неиспользуемого: {format_size(avg_unused_size)}

═══════════════════════════════════════════════════════════"""
        
        self.stats_text.setPlainText(stats_text)
    
    def _update_stats_table(self, analysis: AnalysisResult):
        """Обновляет таблицу детальной статистики"""
        self.stats_table.setRowCount(0)
        
        if not analysis.folder_stats:
            return
        
        def format_size(size_bytes):
            for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
                if size_bytes < 1024.0:
                    return f"{size_bytes:.2f} {unit}"
                size_bytes /= 1024.0
            return f"{size_bytes:.2f} ГБ"
        
        # Считаем размеры по папкам
        folder_sizes = defaultdict(int)
        folder_file_counts = defaultdict(int)
        
        for file_info in analysis.all_files_info.values():
            try:
                if file_info.path.exists():
                    size = file_info.path.stat().st_size
                    folder_sizes[file_info.folder] += size
                    folder_file_counts[file_info.folder] += 1
            except (OSError, AttributeError):
                pass
        
        # Заполняем таблицу
        for folder_name, stats in sorted(analysis.folder_stats.items()):
            row = self.stats_table.rowCount()
            self.stats_table.insertRow(row)
            
            total = stats['total']
            used = stats['used']
            unused = stats['unused']
            
            total_size = folder_sizes.get(folder_name, 0)
            file_count = folder_file_counts.get(folder_name, 0)
            avg_size = total_size / file_count if file_count > 0 else 0
            
            # Папка
            item = QTableWidgetItem(folder_name)
            self.stats_table.setItem(row, 0, item)
            
            # Всего
            item = QTableWidgetItem(str(total))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stats_table.setItem(row, 1, item)
            
            # Используется
            item = QTableWidgetItem(str(used))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if used > 0:
                item.setForeground(QBrush(QColor(76, 175, 80)))  # Зеленый
            self.stats_table.setItem(row, 2, item)
            
            # Не используется
            item = QTableWidgetItem(str(unused))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if unused > 0:
                item.setForeground(QBrush(QColor(244, 67, 54)))  # Красный
            self.stats_table.setItem(row, 3, item)
            
            # Общий размер
            item = QTableWidgetItem(format_size(total_size))
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.stats_table.setItem(row, 4, item)
            
            # Средний размер
            item = QTableWidgetItem(format_size(avg_size))
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.stats_table.setItem(row, 5, item)
        
        self.stats_table.resizeColumnsToContents()

