#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Запуск с отловом всех ошибок
"""

import sys
import traceback
from pathlib import Path

def exception_hook(exctype, value, tb):
    """Глобальный обработчик исключений"""
    error_msg = ''.join(traceback.format_exception(exctype, value, tb))
    print("\n" + "=" * 60)
    print("КРИТИЧЕСКАЯ ОШИБКА:")
    print("=" * 60)
    print(error_msg)
    print("=" * 60)
    
    # Сохраняем в файл
    with open("crash_log.txt", "w", encoding="utf-8") as f:
        f.write(error_msg)
    print("Лог сохранён в crash_log.txt")
    
    input("\nНажмите Enter для выхода...")

# Устанавливаем обработчик
sys.excepthook = exception_hook

# Добавляем путь
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    try:
        from ui.main_window import main
        main()
    except Exception as e:
        exception_hook(type(e), e, e.__traceback__)
