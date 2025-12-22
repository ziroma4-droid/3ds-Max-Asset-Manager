"""
Главное окно приложения Asset Manager
"""

import sys
import os
from pathlib import Path
from typing import Optional
import subprocess
import tempfile

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog,
    QProgressBar, QGroupBox, QCheckBox, QTabWidget, QMessageBox,
    QFrame, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QFont, QTextCursor

# Добавляем путь к core
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import AssetAnalyzer, FileManager, AnalysisResult, OrganizeResult


class AnalyzerThread(QThread):
    """Поток для анализа сцен"""
    
    progress = pyqtSignal(str)
    finished_analysis = pyqtSignal(object)
    error = pyqtSignal(str)
    
    def __init__(self, path: Path, is_folder: bool = False, 
                 recursive: bool = False, use_maxscript: bool = False,
                 max_path: str = ""):
        super().__init__()
        self.path = path
        self.is_folder = is_folder
        self.recursive = recursive
        self.use_maxscript = use_maxscript
        self.max_path = max_path
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
    
    def __init__(self, analysis: AnalysisResult, 
                 create_maps: bool = True,
                 move_unused: bool = True,
                 copy_mode: bool = False):
        super().__init__()
        self.analysis = analysis
        self.create_maps = create_maps
        self.move_unused = move_unused
        self.copy_mode = copy_mode
    
    def run(self):
        try:
            manager = FileManager(progress_callback=self._emit_progress)
            
            self._emit_progress("📦 Начинаем организацию файлов...")
            
            result = manager.organize_assets(
                self.analysis,
                create_maps_folder=self.create_maps,
                move_unused=self.move_unused,
                copy_instead_of_move=self.copy_mode
            )
            
            self._emit_progress("✅ Организация завершена")
            self.finished_organizing.emit(result)
            
        except Exception as e:
            import traceback
            error_msg = f"Ошибка организации: {str(e)}\n{traceback.format_exc()}"
            self.error.emit(error_msg)
    
    def _emit_progress(self, msg: str):
        """Безопасная отправка прогресса"""
        try:
            self.progress.emit(msg)
        except Exception:
            pass


class MainWindow(QMainWindow):
    """Главное окно приложения"""
    
    def __init__(self):
        super().__init__()
        
        self.settings = QSettings("MaxAssetManager", "Settings")
        self.current_analysis: Optional[AnalysisResult] = None
        
        self.init_ui()
        self.load_settings()
    
    def init_ui(self):
        """Инициализация интерфейса"""
        
        self.setWindowTitle("3ds Max Asset Manager")
        self.setMinimumSize(900, 700)
        
        # Центральный виджет
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
        
        # === Табы для режимов работы ===
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Таб одной сцены
        single_tab = self.create_single_scene_tab()
        self.tabs.addTab(single_tab, "📄 Одна сцена")
        
        # Таб папки
        folder_tab = self.create_folder_tab()
        self.tabs.addTab(folder_tab, "📁 Папка со сценами")
        
        # === Опции ===
        options_group = QGroupBox("Опции")
        options_layout = QHBoxLayout(options_group)
        
        self.copy_mode_cb = QCheckBox("Копировать (не перемещать)")
        self.copy_mode_cb.setToolTip("Копировать файлы вместо перемещения")
        options_layout.addWidget(self.copy_mode_cb)
        
        self.create_maps_cb = QCheckBox("Связанные → maps")
        self.create_maps_cb.setChecked(True)
        self.create_maps_cb.setToolTip("Перемещать связанные файлы в папку maps")
        options_layout.addWidget(self.create_maps_cb)
        
        self.move_unused_cb = QCheckBox("Неиспользуемые → unused")
        self.move_unused_cb.setChecked(True)
        self.move_unused_cb.setToolTip("Перемещать неиспользуемые файлы в папку unused")
        options_layout.addWidget(self.move_unused_cb)
        
        options_layout.addStretch()
        main_layout.addWidget(options_group)
        
        # === Кнопки действий ===
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
        
        # Кнопки журнала
        log_buttons = QHBoxLayout()
        
        clear_log_btn = QPushButton("Очистить журнал")
        clear_log_btn.clicked.connect(self.log_text.clear)
        log_buttons.addWidget(clear_log_btn)
        
        log_buttons.addStretch()
        log_layout.addLayout(log_buttons)
        
        main_layout.addWidget(log_group)
    
    def create_single_scene_tab(self) -> QWidget:
        """Создает таб для работы с одной сценой"""
        
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Выбор сцены
        scene_layout = QHBoxLayout()
        scene_layout.addWidget(QLabel("Файл сцены:"))
        
        self.scene_path_edit = QLineEdit()
        self.scene_path_edit.setPlaceholderText("Выберите .max файл")
        scene_layout.addWidget(self.scene_path_edit)
        
        browse_scene_btn = QPushButton("Обзор")
        browse_scene_btn.clicked.connect(self.browse_scene)
        scene_layout.addWidget(browse_scene_btn)
        
        layout.addLayout(scene_layout)
        
        # Информация о сцене
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
        """Создает таб для работы с папкой"""
        
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Выбор папки
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("Папка проекта:"))
        
        self.folder_path_edit = QLineEdit()
        self.folder_path_edit.setPlaceholderText("Выберите папку со сценами")
        folder_layout.addWidget(self.folder_path_edit)
        
        browse_folder_btn = QPushButton("Обзор")
        browse_folder_btn.clicked.connect(self.browse_folder)
        folder_layout.addWidget(browse_folder_btn)
        
        layout.addLayout(folder_layout)
        
        # Опция рекурсивного поиска
        self.recursive_cb = QCheckBox("Искать сцены в подпапках")
        layout.addWidget(self.recursive_cb)
        
        # Список найденных сцен
        scenes_group = QGroupBox("Найденные сцены")
        scenes_layout = QVBoxLayout(scenes_group)
        
        self.scenes_list = QListWidget()
        scenes_layout.addWidget(self.scenes_list)
        
        layout.addWidget(scenes_group)
        
        return tab
    
    def browse_max_path(self):
        """Выбор пути к 3dsmax.exe"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите 3dsmax.exe",
            "",
            "3ds Max (3dsmax.exe)"
        )
        if file_path:
            self.max_path_edit.setText(file_path)
            self.settings.setValue("max_path", file_path)
    
    def browse_scene(self):
        """Выбор .max файла"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите сцену 3ds Max",
            self.settings.value("last_scene_dir", ""),
            "3ds Max Scene (*.max)"
        )
        if file_path:
            self.scene_path_edit.setText(file_path)
            self.settings.setValue("last_scene_dir", str(Path(file_path).parent))
            self.scene_info_label.setText(f"Выбрана сцена: {Path(file_path).name}")
    
    def browse_folder(self):
        """Выбор папки со сценами"""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку со сценами",
            self.settings.value("last_folder", "")
        )
        if folder_path:
            self.folder_path_edit.setText(folder_path)
            self.settings.setValue("last_folder", folder_path)
            self.scan_folder_for_scenes(Path(folder_path))
    
    def scan_folder_for_scenes(self, folder: Path):
        """Сканирует папку на наличие .max файлов"""
        self.scenes_list.clear()
        
        if self.recursive_cb.isChecked():
            max_files = list(folder.rglob("*.max"))
        else:
            max_files = list(folder.glob("*.max"))
        
        for f in max_files:
            item = QListWidgetItem(str(f.relative_to(folder)))
            item.setData(Qt.ItemDataRole.UserRole, str(f))
            self.scenes_list.addItem(item)
        
        self.log(f"📁 Найдено сцен в папке: {len(max_files)}")
    
    def start_analysis(self):
        """Запускает анализ"""
        # Определяем режим работы
        current_tab = self.tabs.currentIndex()
        
        if current_tab == 0:  # Одна сцена
            path = self.scene_path_edit.text().strip()
            if not path:
                QMessageBox.warning(self, "Ошибка", "Выберите сцену для анализа")
                return
            
            path = Path(path)
            if not path.exists():
                QMessageBox.warning(self, "Ошибка", "Файл не найден")
                return
            
            is_folder = False
            recursive = False
            
        else:  # Папка
            path = self.folder_path_edit.text().strip()
            if not path:
                QMessageBox.warning(self, "Ошибка", "Выберите папку для анализа")
                return
            
            path = Path(path)
            if not path.exists():
                QMessageBox.warning(self, "Ошибка", "Папка не найдена")
                return
            
            is_folder = True
            recursive = self.recursive_cb.isChecked()
        
        # Настраиваем UI
        self.set_ui_busy(True)
        self.log_text.clear()
        
        # Запускаем анализ в отдельном потоке
        self.analyzer_thread = AnalyzerThread(
            path=path,
            is_folder=is_folder,
            recursive=recursive,
            use_maxscript=False,
            max_path=self.max_path_edit.text().strip()
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
        
        # Выводим результаты в журнал
        self.log("\n" + "=" * 50)
        self.log("📊 РЕЗУЛЬТАТЫ АНАЛИЗА")
        self.log("=" * 50)
        
        self.log(f"\n📄 Сцен проанализировано: {len(result.scenes)}")
        for scene in result.scenes:
            self.log(f"   • {scene.name}")
        
        # Статистика из сцены
        self.log(f"\n📦 Ассеты В СЦЕНЕ:")
        self.log(f"   🎨 Текстур: {len(result.used_textures)}")
        self.log(f"   📦 Прокси: {len(result.used_proxies)}")
        self.log(f"   📎 Других: {len(result.used_other)}")
        
        # Показываем примеры путей из сцены
        if result.used_textures:
            self.log(f"\n   Примеры текстур из сцены:")
            for tex in list(result.used_textures)[:3]:
                self.log(f"      {tex}")
        
        # Статистика из папки
        self.log(f"\n📂 Файлы В ПАПКЕ ({result.folder_path}):")
        self.log(f"   🎨 Текстур: {len(result.folder_textures)}")
        self.log(f"   📦 Прокси: {len(result.folder_proxies)}")
        self.log(f"   📎 Других: {len(result.folder_other)}")
        
        # Результаты сравнения
        self.log(f"\n" + "-" * 50)
        self.log(f"📋 РЕЗУЛЬТАТЫ СРАВНЕНИЯ (по имени файла):")
        self.log(f"-" * 50)
        
        self.log(f"\n✅ Связанные файлы (есть в сцене и в папке): {len(result.linked_files)}")
        for f in sorted(result.linked_files, key=lambda x: x.name)[:15]:
            self.log(f"   ✓ {f.name}")
        if len(result.linked_files) > 15:
            self.log(f"   ... и ещё {len(result.linked_files) - 15}")
        
        self.log(f"\n⚠️ Неиспользуемые файлы (есть в папке, нет в сцене): {len(result.unused_files)}")
        for f in sorted(result.unused_files, key=lambda x: x.name)[:15]:
            self.log(f"   ⚠ {f.name}")
        if len(result.unused_files) > 15:
            self.log(f"   ... и ещё {len(result.unused_files) - 15}")
        
        if result.missing_files:
            self.log(f"\n❌ Отсутствующие файлы (есть в сцене, нет в папке): {len(result.missing_files)}")
            for f in sorted(result.missing_files)[:10]:
                self.log(f"   ✗ {Path(f).name}")
            if len(result.missing_files) > 10:
                self.log(f"   ... и ещё {len(result.missing_files) - 10}")
        
        if result.errors:
            self.log(f"\n⚠️ Предупреждения:")
            for e in result.errors[:5]:
                self.log(f"   {e}")
        
        self.log("\n" + "=" * 50)
    
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
        
        # Подтверждение
        msg = f"Будет выполнено:\n\n"
        
        if self.create_maps_cb.isChecked():
            msg += f"• Связанных файлов → maps: {linked_count}\n"
        
        if self.move_unused_cb.isChecked():
            msg += f"• Неиспользуемых файлов → unused: {unused_count}\n"
        
        if self.copy_mode_cb.isChecked():
            msg += "\n⚠️ Режим копирования (оригиналы останутся)"
        else:
            msg += "\n⚠️ Режим перемещения (оригиналы будут перенесены)"
        
        msg += f"\n\nПапка: {self.current_analysis.folder_path}"
        
        reply = QMessageBox.question(
            self, 
            "Подтверждение",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self.set_ui_busy(True)
        self.log("\n" + "=" * 50)
        self.log("📦 ОРГАНИЗАЦИЯ ФАЙЛОВ")
        self.log("=" * 50)
        
        self.organizer_thread = OrganizerThread(
            analysis=self.current_analysis,
            create_maps=self.create_maps_cb.isChecked(),
            move_unused=self.move_unused_cb.isChecked(),
            copy_mode=self.copy_mode_cb.isChecked()
        )
        
        self.organizer_thread.progress.connect(self.log)
        self.organizer_thread.finished_organizing.connect(self.on_organizing_finished)
        self.organizer_thread.error.connect(self.on_error)
        self.organizer_thread.finished.connect(lambda: self.set_ui_busy(False))
        
        self.organizer_thread.start()
    
    def on_organizing_finished(self, result):
        """Обработка завершения организации"""
        if result is None:
            self.log("\n❌ Ошибка: результат организации пустой")
            return
        
        self.log("\n" + "-" * 50)
        self.log("📊 ИТОГИ:")
        self.log(f"   ✅ Успешно: {len(result.successful_moves)}")
        self.log(f"   ❌ Ошибок: {len(result.failed_moves)}")
        
        if result.maps_folder:
            self.log(f"   📁 Папка maps: {result.maps_folder}")
        if result.unused_folder:
            self.log(f"   📁 Папка unused: {result.unused_folder}")
        
        if result.failed_moves:
            self.log("\n❌ Файлы с ошибками:")
            for op in result.failed_moves[:10]:
                self.log(f"   • {op.source.name}: {op.error}")
        
        self.log("=" * 50)
        
        QMessageBox.information(
            self,
            "Готово",
            f"Организация файлов завершена!\n\n"
            f"Успешно: {len(result.successful_moves)}\n"
            f"Ошибок: {len(result.failed_moves)}"
        )
    
    def save_report(self):
        """Сохраняет отчет в файл"""
        if not self.current_analysis:
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить отчет",
            str(self.current_analysis.folder_path / "asset_report.txt"),
            "Text Files (*.txt);;All Files (*)"
        )
        
        if file_path:
            try:
                manager = FileManager()
                report = manager.create_report(self.current_analysis)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(report)
                
                self.log(f"\n💾 Отчет сохранен: {file_path}")
                
                QMessageBox.information(
                    self,
                    "Сохранено",
                    f"Отчет сохранен:\n{file_path}"
                )
                
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Ошибка",
                    f"Не удалось сохранить отчет:\n{str(e)}"
                )
    
    def on_error(self, error_msg: str):
        """Обработка ошибок"""
        self.log(f"\n❌ ОШИБКА: {error_msg}")
        QMessageBox.critical(self, "Ошибка", error_msg)
    
    def set_ui_busy(self, busy: bool):
        """Переключает UI в режим занятости"""
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
        """Добавляет сообщение в журнал"""
        self.log_text.append(message)
        
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)
        
        QApplication.processEvents()
    
    def load_settings(self):
        """Загружает настройки"""
        max_path = self.settings.value("max_path", "")
        if max_path:
            self.max_path_edit.setText(max_path)
        
        if not max_path:
            self.auto_detect_max()
    
    def auto_detect_max(self):
        """Автоматическое определение пути к 3ds Max"""
        possible_paths = [
            r"C:\Program Files\Autodesk\3ds Max 2025\3dsmax.exe",
            r"C:\Program Files\Autodesk\3ds Max 2024\3dsmax.exe",
            r"C:\Program Files\Autodesk\3ds Max 2023\3dsmax.exe",
            r"C:\Program Files\Autodesk\3ds Max 2022\3dsmax.exe",
            r"C:\Program Files\Autodesk\3ds Max 2021\3dsmax.exe",
        ]
        
        for path in possible_paths:
            if Path(path).exists():
                self.max_path_edit.setText(path)
                self.settings.setValue("max_path", path)
                self.log(f"🔍 Найден 3ds Max: {path}")
                break
    
    def closeEvent(self, event):
        """Сохраняем настройки при закрытии"""
        self.settings.setValue("max_path", self.max_path_edit.text())
        self.settings.setValue("geometry", self.saveGeometry())
        event.accept()


def main():
    """Точка входа"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Стиль
    app.setStyleSheet("""
        QMainWindow { background-color: #2b2b2b; }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #555;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        QPushButton {
            background-color: #0d6efd;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }
        QPushButton:hover { background-color: #0b5ed7; }
        QPushButton:pressed { background-color: #0a58ca; }
        QPushButton:disabled { background-color: #6c757d; }
        QTextEdit {
            background-color: #1e1e1e;
            color: #d4d4d4;
            border: 1px solid #555;
            border-radius: 4px;
        }
        QLineEdit {
            padding: 6px;
            border: 1px solid #555;
            border-radius: 4px;
            background-color: #3c3c3c;
            color: white;
        }
        QListWidget {
            background-color: #1e1e1e;
            color: #d4d4d4;
            border: 1px solid #555;
            border-radius: 4px;
        }
        QCheckBox { spacing: 8px; }
        QTabWidget::pane {
            border: 1px solid #555;
            border-radius: 4px;
        }
        QTabBar::tab {
            background-color: #3c3c3c;
            color: white;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
        QTabBar::tab:selected { background-color: #0d6efd; }
        QProgressBar {
            border: 1px solid #555;
            border-radius: 4px;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: #0d6efd;
            border-radius: 3px;
        }
    """)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
