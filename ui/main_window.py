"""
Главное окно приложения Asset Manager
"""

import sys
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog,
    QProgressBar, QGroupBox, QCheckBox, QTabWidget, QMessageBox,
    QFrame, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QFont, QTextCursor, QColor, QBrush

# Добавляем путь к core
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import AssetAnalyzer, FileManager, AnalysisResult, OrganizeResult
from core.asset_analyzer import FileInfo
from ui.statistics_widget import StatisticsWidget
from ui.folder_tree_widget import FolderTreeWidget


class AnalyzerThread(QThread):
    """Поток для анализа сцен"""
    
    progress = pyqtSignal(str)
    finished_analysis = pyqtSignal(object)
    error = pyqtSignal(str)
    
    def __init__(self, path: Path, is_folder: bool = False, 
                 recursive: bool = False):
        super().__init__()
        self.path = path
        self.is_folder = is_folder
        self.recursive = recursive
        self.analyzer = AssetAnalyzer(debug=True)
    
    def run(self):
        try:
            self.progress.emit(f"🔍 Начинаем анализ: {self.path}")
            
            if self.is_folder:
                result = self.analyzer.analyze_folder(self.path, self.recursive)
            else:
                result = self.analyzer.analyze_single_scene(self.path)
            
            self.progress.emit("✅ Анализ завершен")
            self.finished_analysis.emit(result)
            
        except Exception as e:
            import traceback
            self.error.emit(f"Ошибка анализа: {str(e)}\n{traceback.format_exc()}")


class OrganizerThread(QThread):
    """Поток для организации файлов"""
    
    progress = pyqtSignal(str)
    finished_organizing = pyqtSignal(object)
    error = pyqtSignal(str)
    
    def __init__(self, analysis, 
                 create_maps: bool = True,
                 move_unused: bool = True,
                 copy_mode: bool = False,
                 delete_duplicates: bool = True):
        super().__init__()
        self.analysis = analysis
        self.create_maps = create_maps
        self.move_unused = move_unused
        self.copy_mode = copy_mode
        self.delete_duplicates = delete_duplicates
    
    def run(self):
        result = None
        try:
            # Используем импорты из начала файла
            def safe_progress(msg):
                try:
                    self.progress.emit(str(msg))
                except (RuntimeError, TypeError):
                    pass
            
            manager = FileManager(progress_callback=safe_progress)
            
            result = manager.organize_assets(
                self.analysis,
                create_maps_folder=self.create_maps,
                move_unused=self.move_unused,
                copy_instead_of_move=self.copy_mode,
                delete_duplicates=self.delete_duplicates
            )
            
        except Exception as e:
            import traceback
            error_msg = f"Ошибка: {str(e)}\n{traceback.format_exc()}"
            self.error.emit(error_msg)
            # Используем импорт из начала файла
            result = OrganizeResult()
        
        finally:
            if result is None:
                # Используем импорт из начала файла
                result = OrganizeResult()
            self.finished_organizing.emit(result)



class MainWindow(QMainWindow):
    """Главное окно приложения"""
    
    def __init__(self):
        super().__init__()
        
        self.settings = QSettings("MaxAssetManager", "Settings")
        self.current_analysis: Optional[AnalysisResult] = None
        self.analyzer_thread = None
        self.organizer_thread = None
        
        self.init_ui()
        self.load_settings()
    
    def init_ui(self):
        """Инициализация интерфейса"""
        
        self.setWindowTitle("3ds Max Asset Manager")
        self.setMinimumSize(900, 700)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # === Настройки 3ds Max ===
        max_group = QGroupBox("Настройки 3ds Max")
        max_layout = QHBoxLayout(max_group)
        
        max_layout.addWidget(QLabel("Путь к 3dsmax.exe:"))
        self.max_path_edit = QLineEdit()
        self.max_path_edit.setPlaceholderText("C:\\Program Files\\Autodesk\\3ds Max 2024\\3dsmax.exe")
        max_layout.addWidget(self.max_path_edit)
        
        browse_max_btn = QPushButton("Обзор")
        browse_max_btn.clicked.connect(self.browse_max_path)
        max_layout.addWidget(browse_max_btn)
        
        main_layout.addWidget(max_group)
        
        # === Табы ===
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        single_tab = self.create_single_scene_tab()
        self.tabs.addTab(single_tab, "📄 Одна сцена")
        
        folder_tab = self.create_folder_tab()
        self.tabs.addTab(folder_tab, "📁 Папка со сценами")
        
        # Вкладки визуализации (будут доступны после анализа)
        self.stats_widget = StatisticsWidget()
        self.tabs.addTab(self.stats_widget, "📊 Статистика")
        
        self.tree_widget = FolderTreeWidget()
        self.tabs.addTab(self.tree_widget, "📁 Структура папок")
        
                # === Опции ===
        options_group = QGroupBox("Опции организации")
        options_layout = QHBoxLayout(options_group)
        
        self.copy_mode_cb = QCheckBox("Копировать (не перемещать)")
        options_layout.addWidget(self.copy_mode_cb)
        
        self.create_maps_cb = QCheckBox("Собрать в maps")
        self.create_maps_cb.setChecked(True)  # Теперь по умолчанию включено
        self.create_maps_cb.setToolTip("Собрать все связанные файлы в папку maps")
        options_layout.addWidget(self.create_maps_cb)
        
        self.delete_duplicates_cb = QCheckBox("Удалять дубликаты")
        self.delete_duplicates_cb.setChecked(True)
        self.delete_duplicates_cb.setToolTip("Удалять файлы-дубликаты (одинаковое содержимое)")
        options_layout.addWidget(self.delete_duplicates_cb)
        
        self.move_unused_cb = QCheckBox("Unused → папка")
        self.move_unused_cb.setChecked(True)
        options_layout.addWidget(self.move_unused_cb)
        
        options_layout.addStretch()
        main_layout.addWidget(options_group)

        
        # === Кнопки ===
        actions_layout = QHBoxLayout()
        
        self.analyze_btn = QPushButton("🔍 Анализировать")
        self.analyze_btn.setMinimumHeight(40)
        self.analyze_btn.clicked.connect(self.start_analysis)
        actions_layout.addWidget(self.analyze_btn)
        
        self.organize_btn = QPushButton("📦 Организовать файлы")
        self.organize_btn.setMinimumHeight(40)
        self.organize_btn.setEnabled(False)
        self.organize_btn.clicked.connect(self.start_organizing)
        actions_layout.addWidget(self.organize_btn)
        
        self.save_report_btn = QPushButton("💾 Сохранить отчет")
        self.save_report_btn.setMinimumHeight(40)
        self.save_report_btn.setEnabled(False)
        self.save_report_btn.clicked.connect(self.save_report)
        actions_layout.addWidget(self.save_report_btn)
        
        main_layout.addLayout(actions_layout)
        
        # === Прогресс ===
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # === Журнал ===
        log_group = QGroupBox("📋 Журнал")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setMinimumHeight(250)
        log_layout.addWidget(self.log_text)
        
        log_buttons = QHBoxLayout()
        clear_log_btn = QPushButton("Очистить журнал")
        clear_log_btn.clicked.connect(self.log_text.clear)
        log_buttons.addWidget(clear_log_btn)
        log_buttons.addStretch()
        log_layout.addLayout(log_buttons)
        
        main_layout.addWidget(log_group)
    
    def create_single_scene_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        scene_layout = QHBoxLayout()
        scene_layout.addWidget(QLabel("Файл сцены:"))
        
        self.scene_path_edit = QLineEdit()
        self.scene_path_edit.setPlaceholderText("Выберите .max файл")
        scene_layout.addWidget(self.scene_path_edit)
        
        browse_scene_btn = QPushButton("Обзор")
        browse_scene_btn.clicked.connect(self.browse_scene)
        scene_layout.addWidget(browse_scene_btn)
        
        layout.addLayout(scene_layout)
        
        info_frame = QFrame()
        info_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        info_layout = QVBoxLayout(info_frame)
        
        self.scene_info_label = QLabel("Выберите сцену для анализа")
        self.scene_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(self.scene_info_label)
        
        layout.addWidget(info_frame)
        layout.addStretch()
        
        return tab
    
    def create_folder_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("Папка проекта:"))
        
        self.folder_path_edit = QLineEdit()
        self.folder_path_edit.setPlaceholderText("Выберите папку со сценами")
        folder_layout.addWidget(self.folder_path_edit)
        
        browse_folder_btn = QPushButton("Обзор")
        browse_folder_btn.clicked.connect(self.browse_folder)
        folder_layout.addWidget(browse_folder_btn)
        
        layout.addLayout(folder_layout)
        
        self.recursive_cb = QCheckBox("Искать сцены в подпапках")
        layout.addWidget(self.recursive_cb)
        
        scenes_group = QGroupBox("Найденные сцены")
        scenes_layout = QVBoxLayout(scenes_group)
        
        self.scenes_list = QListWidget()
        self.scenes_list.itemDoubleClicked.connect(self.on_scene_double_clicked)
        scenes_layout.addWidget(self.scenes_list)
        
        layout.addWidget(scenes_group)
        
        return tab
    
    def on_scene_double_clicked(self, item):
        """Обработка двойного клика по сцене в списке"""
        scene_path = item.data(Qt.ItemDataRole.UserRole)
        if scene_path:
            import os
            os.startfile(str(scene_path))
    
    def browse_max_path(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите 3dsmax.exe", "", "3ds Max (3dsmax.exe)"
        )
        if file_path:
            self.max_path_edit.setText(file_path)
            self.settings.setValue("max_path", file_path)
    
    def browse_scene(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите сцену 3ds Max",
            self.settings.value("last_scene_dir", ""),
            "3ds Max Scene (*.max)"
        )
        if file_path:
            self.scene_path_edit.setText(file_path)
            self.settings.setValue("last_scene_dir", str(Path(file_path).parent))
            self.scene_info_label.setText(f"Выбрана сцена: {Path(file_path).name}")
    
    def browse_folder(self):
        folder_path = QFileDialog.getExistingDirectory(
            self, "Выберите папку со сценами",
            self.settings.value("last_folder", "")
        )
        if folder_path:
            self.folder_path_edit.setText(folder_path)
            self.settings.setValue("last_folder", folder_path)
            self.scan_folder_for_scenes(Path(folder_path))
    
    def scan_folder_for_scenes(self, folder: Path):
        self.scenes_list.clear()
        
        if self.recursive_cb.isChecked():
            max_files = list(folder.rglob("*.max"))
        else:
            max_files = list(folder.glob("*.max"))
        
        for f in max_files:
            item = QListWidgetItem(f"📄 {f.relative_to(folder)}")
            item.setData(Qt.ItemDataRole.UserRole, str(f))
            # Цветовая индикация: существующие файлы - нормальный цвет, несуществующие - серый
            if not f.exists():
                item.setForeground(QBrush(QColor(158, 158, 158)))
            self.scenes_list.addItem(item)
        
        self.log(f"📁 Найдено сцен: {len(max_files)}")
    
    def start_analysis(self):
        current_tab = self.tabs.currentIndex()
        
        if current_tab == 0:
            path = self.scene_path_edit.text().strip()
            if not path:
                QMessageBox.warning(self, "Ошибка", "Выберите сцену")
                return
            path = Path(path)
            if not path.exists():
                QMessageBox.warning(self, "Ошибка", "Файл не найден")
                return
            is_folder = False
            recursive = False
        else:
            path = self.folder_path_edit.text().strip()
            if not path:
                QMessageBox.warning(self, "Ошибка", "Выберите папку")
                return
            path = Path(path)
            if not path.exists():
                QMessageBox.warning(self, "Ошибка", "Папка не найдена")
                return
            is_folder = True
            recursive = self.recursive_cb.isChecked()
        
        self.set_ui_busy(True)
        self.log_text.clear()
        
        self.analyzer_thread = AnalyzerThread(
            path=path,
            is_folder=is_folder,
            recursive=recursive
        )
        
        self.analyzer_thread.progress.connect(self.log)
        self.analyzer_thread.finished_analysis.connect(self.on_analysis_finished)
        self.analyzer_thread.error.connect(self.on_error)
        self.analyzer_thread.finished.connect(lambda: self.set_ui_busy(False))
        
        self.analyzer_thread.start()
    
    def on_analysis_finished(self, result: AnalysisResult):
        """Обработка завершения анализа"""
        self.current_analysis = result
        self.organize_btn.setEnabled(True)
        self.save_report_btn.setEnabled(True)
        
        # Обновляем виджеты визуализации
        self.stats_widget.update_statistics(result)
        self.tree_widget.update_tree(result)
        
        self.log("\n" + "=" * 60)
        self.log("📊 РЕЗУЛЬТАТЫ АНАЛИЗА")
        self.log("=" * 60)
        
        self.log(f"\n📄 Сцен: {len(result.scenes)}")
        for scene in result.scenes:
            self.log(f"   • {scene.name}")
        
        self.log(f"\n📦 АССЕТЫ В СЦЕНЕ:")
        self.log(f"   🎨 Текстур: {len(result.used_textures)}")
        self.log(f"   📦 Прокси: {len(result.used_proxies)}")
        self.log(f"   📎 Других: {len(result.used_other)}")
        
        # Статистика по папкам
        self.log(f"\n" + "-" * 60)
        self.log(f"📂 ФАЙЛЫ В ПАПКЕ ({result.folder_path}):")
        self.log("-" * 60)
        
        if result.folder_stats:
            for folder_name, stats in sorted(result.folder_stats.items()):
                used_pct = (stats['used'] / stats['total'] * 100) if stats['total'] > 0 else 0
                self.log(f"\n📁 {folder_name}/")
                self.log(f"   Всего: {stats['total']} | ✅ Используется: {stats['used']} ({used_pct:.0f}%) | ⚠️ Не используется: {stats['unused']}")
        
        # Статистика по размерам
        total_size = 0
        used_size = 0
        unused_size = 0
        file_count = 0
        used_count = 0
        
        for file_info in result.all_files_info.values():
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
            except (OSError, AttributeError):
                pass
        
        def format_size(size_bytes):
            for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
                if size_bytes < 1024.0:
                    return f"{size_bytes:.2f} {unit}"
                size_bytes /= 1024.0
            return f"{size_bytes:.2f} ПБ"
        
        # Итоги
        self.log(f"\n" + "=" * 60)
        self.log(f"📋 ИТОГО:")
        self.log(f"   ✅ Связано: {len(result.linked_files)}")
        self.log(f"   ⚠️ Не используется: {len(result.unused_files)}")
        self.log(f"   ❌ Отсутствует: {len(result.missing_files)}")
        
        # Статистика по размерам
        if file_count > 0:
            used_pct = (used_size / total_size * 100) if total_size > 0 else 0
            avg_size = total_size / file_count
            self.log(f"\n💾 РАЗМЕРЫ ФАЙЛОВ:")
            self.log(f"   Общий размер: {format_size(total_size)}")
            self.log(f"   ✅ Используется: {format_size(used_size)} ({used_pct:.1f}%)")
            self.log(f"   ⚠️ Не используется: {format_size(unused_size)}")
            self.log(f"   Средний размер файла: {format_size(avg_size)}")
        
        # Неиспользуемые по папкам
        if result.unused_files:
            self.log(f"\n⚠️ НЕИСПОЛЬЗУЕМЫЕ ФАЙЛЫ:")
            unused_by_folder = result.get_unused_by_folder()
            for folder_name, files in sorted(unused_by_folder.items()):
                self.log(f"\n   📁 {folder_name}/ ({len(files)}):")
                for fi in sorted(files, key=lambda x: x.name)[:10]:
                    self.log(f"      ⚠ {fi.name}")
                if len(files) > 10:
                    self.log(f"      ... и ещё {len(files) - 10}")
        
        self.log("\n" + "=" * 60)
        self.log("💡 Перейдите на вкладки 'Статистика' и 'Структура папок' для детальной информации")
    
    def start_organizing(self):
        """Запускает организацию файлов"""
        if not self.current_analysis:
            QMessageBox.warning(self, "Ошибка", "Сначала выполните анализ")
            return
        
        linked_count = len(self.current_analysis.linked_files)
        unused_count = len(self.current_analysis.unused_files)
        
        if linked_count == 0 and unused_count == 0:
            QMessageBox.information(self, "Информация", "Нет файлов для организации")
            return
        
        msg = f"Будет выполнено:\n\n"
        if self.create_maps_cb.isChecked():
            msg += f"• Собрать связанные файлы в maps: {linked_count}\n"
            if self.delete_duplicates_cb.isChecked():
                msg += f"• Удалить дубликаты: Да\n"
        if self.move_unused_cb.isChecked():
            msg += f"• Переместить неиспользуемые в unused: {unused_count}\n"
        
        if self.copy_mode_cb.isChecked():
            msg += "\n⚠️ Режим: КОПИРОВАНИЕ"
        else:
            msg += "\n⚠️ Режим: ПЕРЕМЕЩЕНИЕ"
        
        reply = QMessageBox.question(
            self, "Подтверждение", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self.set_ui_busy(True)
        self.log("\n" + "=" * 60)
        self.log("📦 ОРГАНИЗАЦИЯ ФАЙЛОВ")
        self.log("=" * 60)
        
        self.organizer_thread = OrganizerThread(
            analysis=self.current_analysis,
            create_maps=self.create_maps_cb.isChecked(),
            move_unused=self.move_unused_cb.isChecked(),
            copy_mode=self.copy_mode_cb.isChecked(),
            delete_duplicates=self.delete_duplicates_cb.isChecked()
        )
        
        self.organizer_thread.progress.connect(self.log)
        self.organizer_thread.finished_organizing.connect(self.on_organizing_finished)
        self.organizer_thread.error.connect(self.on_error)
        self.organizer_thread.finished.connect(lambda: self.set_ui_busy(False))
        
        self.organizer_thread.start()

    
    def on_organizing_finished(self, result):
        """Обработка завершения организации"""
        if result is None:
            self.log("\n❌ Результат пустой")
            return
        
        self.log("\n" + "-" * 60)
        self.log("📊 ИТОГИ ОРГАНИЗАЦИИ:")
        self.log(f"   ✅ Успешно: {len(result.successful_moves)}")
        self.log(f"   ❌ Ошибок: {len(result.failed_moves)}")
        
        if result.maps_folder:
            self.log(f"   📁 maps: {result.maps_folder}")
        if result.unused_folder:
            self.log(f"   📁 unused: {result.unused_folder}")
        
        if result.failed_moves:
            self.log("\n❌ Ошибки:")
            for op in result.failed_moves[:10]:
                self.log(f"   • {op.source.name}: {op.error}")
        
        self.log("=" * 60)
        
        QMessageBox.information(
            self, "Готово",
            f"Организация завершена!\n\nУспешно: {len(result.successful_moves)}\nОшибок: {len(result.failed_moves)}"
        )
    
    def save_report(self):
        if not self.current_analysis:
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить отчет",
            str(self.current_analysis.folder_path / "asset_report.txt"),
            "Text Files (*.txt)"
        )
        
        if file_path:
            try:
                manager = FileManager()
                report = manager.create_report(self.current_analysis)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(report)
                
                self.log(f"\n💾 Отчет сохранен: {file_path}")
                QMessageBox.information(self, "Сохранено", f"Отчет сохранен:\n{file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить:\n{e}")
    
    def on_error(self, error_msg: str):
        self.log(f"\n❌ ОШИБКА: {error_msg}")
        QMessageBox.critical(self, "Ошибка", error_msg)
    
    def set_ui_busy(self, busy: bool):
        self.analyze_btn.setEnabled(not busy)
        self.organize_btn.setEnabled(not busy and self.current_analysis is not None)
        self.save_report_btn.setEnabled(not busy and self.current_analysis is not None)
        self.tabs.setEnabled(not busy)
        
        self.progress_bar.setVisible(busy)
        if busy:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
    
    def log(self, message: str):
        self.log_text.append(message)
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)
        QApplication.processEvents()
    
    def load_settings(self):
        max_path = self.settings.value("max_path", "")
        if max_path:
            self.max_path_edit.setText(max_path)
        else:
            self.auto_detect_max()
    
    def auto_detect_max(self):
        for year in range(2025, 2019, -1):
            path = f"C:\\Program Files\\Autodesk\\3ds Max {year}\\3dsmax.exe"
            if Path(path).exists():
                self.max_path_edit.setText(path)
                self.settings.setValue("max_path", path)
                break
    
    def closeEvent(self, event):
        self.settings.setValue("max_path", self.max_path_edit.text())
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    app.setStyleSheet("""
        QGroupBox { font-weight: bold; border: 1px solid #555; border-radius: 5px; margin-top: 10px; padding-top: 10px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        QPushButton { background-color: #0d6efd; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold; }
        QPushButton:hover { background-color: #0b5ed7; }
        QPushButton:disabled { background-color: #6c757d; }
        QTextEdit { background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #555; border-radius: 4px; }
        QLineEdit { padding: 6px; border: 1px solid #555; border-radius: 4px; background-color: #3c3c3c; color: white; }
        QListWidget { background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #555; }
        QTabBar::tab { background-color: #3c3c3c; color: white; padding: 8px 16px; }
        QTabBar::tab:selected { background-color: #0d6efd; }
        QProgressBar { border: 1px solid #555; border-radius: 4px; }
        QProgressBar::chunk { background-color: #0d6efd; }
    """)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
