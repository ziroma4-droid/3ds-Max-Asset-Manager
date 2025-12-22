#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
3ds Max Asset Manager
Программа для управления текстурами и прокси в сценах 3ds Max
"""

import sys
from pathlib import Path

# Добавляем пути
sys.path.insert(0, str(Path(__file__).parent))

from ui.main_window import main

if __name__ == "__main__":
    main()
