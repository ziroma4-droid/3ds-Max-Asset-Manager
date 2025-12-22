#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Отладочный скрипт для тестирования парсера .max файлов
"""

import sys
from pathlib import Path

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent))

from core.max_parser import MaxFileParser


def debug_parse(max_file: str):
    """Парсит .max файл с отладочной информацией"""
    
    print("=" * 60)
    print(f"Анализ файла: {max_file}")
    print("=" * 60)
    
    parser = MaxFileParser(debug=True)
    assets = parser.parse_scene(max_file)
    
    print(f"\n📄 Файл: {assets.scene_path.name}")
    print(f"📁 Папка: {assets.scene_path.parent}")
    
    print(f"\n🎨 Найдено текстур: {len(assets.textures)}")
    for tex in sorted(assets.textures):
        exists = "✓" if Path(tex).exists() else "✗"
        print(f"   [{exists}] {tex}")
    
    print(f"\n📦 Найдено прокси: {len(assets.proxies)}")
    for proxy in sorted(assets.proxies):
        exists = "✓" if Path(proxy).exists() else "✗"
        print(f"   [{exists}] {proxy}")
    
    print(f"\n📎 Другие ассеты: {len(assets.other_assets)}")
    for other in sorted(assets.other_assets):
        exists = "✓" if Path(other).exists() else "✗"
        print(f"   [{exists}] {other}")
    
    if assets.errors:
        print(f"\n⚠️ Ошибки:")
        for err in assets.errors:
            print(f"   {err}")
    
    if assets.debug_info:
        print(f"\n🔧 Отладочная информация:")
        for info in assets.debug_info[:50]:  # Первые 50
            print(f"   {info}")
    
    print("\n" + "=" * 60)
    
    return assets


def dump_raw_strings(max_file: str, output_file: str = None):
    """Извлекает все строки из .max файла для анализа"""
    
    import olefile
    import re
    
    print(f"Извлечение строк из: {max_file}")
    
    if not olefile.isOleFile(max_file):
        print("Ошибка: файл не является OLE")
        return
    
    all_strings = set()
    
    with olefile.OleFileIO(max_file) as ole:
        for stream_path in ole.listdir():
            try:
                data = ole.openstream(stream_path).read()
                
                # Ищем ASCII строки (минимум 10 символов)
                ascii_strings = re.findall(rb'[\x20-\x7e]{10,}', data)
                for s in ascii_strings:
                    try:
                        decoded = s.decode('ascii')
                        if any(ext in decoded.lower() for ext in ['.jpg', '.png', '.tga', '.exr', '.tif', '.vrmesh', '.abc']):
                            all_strings.add(decoded)
                    except:
                        pass
                
            except Exception as e:
                print(f"  Ошибка чтения {stream_path}: {e}")
    
    print(f"\nНайдено строк с путями: {len(all_strings)}")
    
    for s in sorted(all_strings):
        print(f"  {s}")
    
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            for s in sorted(all_strings):
                f.write(s + '\n')
        print(f"\nСтроки сохранены в: {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python debug_parser.py <путь_к_файлу.max>")
        print("  python debug_parser.py <путь_к_файлу.max> --dump")
        sys.exit(1)
    
    max_file = sys.argv[1]
    
    if not Path(max_file).exists():
        print(f"Файл не найден: {max_file}")
        sys.exit(1)
    
    if len(sys.argv) > 2 and sys.argv[2] == '--dump':
        dump_raw_strings(max_file, max_file + "_strings.txt")
    else:
        debug_parse(max_file)
