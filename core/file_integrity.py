"""
Проверка целостности файлов (изображений)
"""

from pathlib import Path
from typing import List, Dict, Tuple, Optional
import struct


class FileIntegrityChecker:
    """Проверяет целостность файлов, особенно изображений"""
    
    # Сигнатуры файлов (магические числа)
    IMAGE_SIGNATURES = {
        b'\xFF\xD8\xFF': 'JPEG',
        b'\x89PNG\r\n\x1a\n': 'PNG',
        b'GIF87a': 'GIF87a',
        b'GIF89a': 'GIF89a',
        b'BM': 'BMP',
        b'II*\x00': 'TIFF (little-endian)',
        b'MM\x00*': 'TIFF (big-endian)',
        b'RIFF': 'WEBP/AVI',
    }
    
    @staticmethod
    def check_image_integrity(file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Проверяет целостность изображения
        
        Returns:
            (is_valid, error_message)
        """
        if not file_path.exists():
            return False, "Файл не существует"
        
        try:
            ext = file_path.suffix.lower()
            
            # Проверяем по расширению
            if ext in ['.jpg', '.jpeg']:
                return FileIntegrityChecker._check_jpeg(file_path)
            elif ext == '.png':
                return FileIntegrityChecker._check_png(file_path)
            elif ext == '.gif':
                return FileIntegrityChecker._check_gif(file_path)
            elif ext == '.bmp':
                return FileIntegrityChecker._check_bmp(file_path)
            elif ext in ['.tif', '.tiff']:
                return FileIntegrityChecker._check_tiff(file_path)
            elif ext == '.tga':
                return FileIntegrityChecker._check_tga(file_path)
            elif ext == '.dds':
                return FileIntegrityChecker._check_dds(file_path)
            elif ext in ['.exr', '.hdr']:
                # Для EXR и HDR проверяем только наличие файла
                return True, None
            else:
                # Для неизвестных форматов проверяем только размер
                size = file_path.stat().st_size
                if size == 0:
                    return False, "Файл пустой"
                return True, None
                
        except Exception as e:
            return False, f"Ошибка проверки: {str(e)}"
    
    @staticmethod
    def _check_jpeg(file_path: Path) -> Tuple[bool, Optional[str]]:
        """Проверяет JPEG файл"""
        try:
            with open(file_path, 'rb') as f:
                # Проверяем сигнатуру
                header = f.read(3)
                if header != b'\xFF\xD8\xFF':
                    return False, "Неверная сигнатура JPEG"
                
                # Проверяем наличие маркера конца файла
                f.seek(-2, 2)  # Переходим к концу файла
                footer = f.read(2)
                if footer != b'\xFF\xD9':
                    return False, "JPEG файл поврежден (нет маркера конца)"
                
                return True, None
        except Exception as e:
            return False, f"Ошибка чтения JPEG: {str(e)}"
    
    @staticmethod
    def _check_png(file_path: Path) -> Tuple[bool, Optional[str]]:
        """Проверяет PNG файл"""
        try:
            with open(file_path, 'rb') as f:
                # Проверяем сигнатуру
                header = f.read(8)
                if header != b'\x89PNG\r\n\x1a\n':
                    return False, "Неверная сигнатура PNG"
                
                # Проверяем IEND chunk в конце
                f.seek(-8, 2)
                footer = f.read(8)
                if footer[-4:] != b'IEND':
                    return False, "PNG файл поврежден (нет IEND chunk)"
                
                return True, None
        except Exception as e:
            return False, f"Ошибка чтения PNG: {str(e)}"
    
    @staticmethod
    def _check_gif(file_path: Path) -> Tuple[bool, Optional[str]]:
        """Проверяет GIF файл"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(6)
                if header not in [b'GIF87a', b'GIF89a']:
                    return False, "Неверная сигнатура GIF"
                
                # Проверяем наличие терминатора
                f.seek(-1, 2)
                terminator = f.read(1)
                if terminator != b';':
                    return False, "GIF файл поврежден (нет терминатора)"
                
                return True, None
        except Exception as e:
            return False, f"Ошибка чтения GIF: {str(e)}"
    
    @staticmethod
    def _check_bmp(file_path: Path) -> Tuple[bool, Optional[str]]:
        """Проверяет BMP файл"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(2)
                if header != b'BM':
                    return False, "Неверная сигнатура BMP"
                
                # Проверяем размер файла
                f.seek(2)
                file_size = struct.unpack('<I', f.read(4))[0]
                actual_size = file_path.stat().st_size
                
                if file_size != actual_size:
                    return False, "BMP файл поврежден (неверный размер)"
                
                return True, None
        except Exception as e:
            return False, f"Ошибка чтения BMP: {str(e)}"
    
    @staticmethod
    def _check_tiff(file_path: Path) -> Tuple[bool, Optional[str]]:
        """Проверяет TIFF файл"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(4)
                if header not in [b'II*\x00', b'MM\x00*']:
                    return False, "Неверная сигнатура TIFF"
                
                return True, None
        except Exception as e:
            return False, f"Ошибка чтения TIFF: {str(e)}"
    
    @staticmethod
    def _check_tga(file_path: Path) -> Tuple[bool, Optional[str]]:
        """Проверяет TGA файл"""
        try:
            size = file_path.stat().st_size
            if size < 18:  # Минимальный размер TGA заголовка
                return False, "TGA файл слишком мал"
            
            with open(file_path, 'rb') as f:
                # Читаем заголовок
                f.read(18)
                # Проверяем, что файл не пустой
                if size == 18:
                    return False, "TGA файл содержит только заголовок"
                
                return True, None
        except Exception as e:
            return False, f"Ошибка чтения TGA: {str(e)}"
    
    @staticmethod
    def _check_dds(file_path: Path) -> Tuple[bool, Optional[str]]:
        """Проверяет DDS файл"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(4)
                if header != b'DDS ':
                    return False, "Неверная сигнатура DDS"
                
                return True, None
        except Exception as e:
            return False, f"Ошибка чтения DDS: {str(e)}"
    
    @staticmethod
    def check_files_batch(file_paths: List[Path]) -> Dict[Path, Tuple[bool, Optional[str]]]:
        """
        Проверяет целостность нескольких файлов
        
        Returns:
            Словарь {путь: (валиден, сообщение_об_ошибке)}
        """
        results = {}
        for file_path in file_paths:
            is_valid, error = FileIntegrityChecker.check_image_integrity(file_path)
            results[file_path] = (is_valid, error)
        return results

