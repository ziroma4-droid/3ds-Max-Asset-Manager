# Скрипт запуска 3ds Max Asset Manager
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# Активируем виртуальное окружение
& "$scriptPath\venv\Scripts\Activate.ps1"

# Запускаем приложение
python main.py

