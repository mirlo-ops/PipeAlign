@echo off
REM ===========================================================================
REM  PipeAlign / ТрубоНастрой — сборка Windows-приложения (PyInstaller)
REM  Запускайте из любого каталога:  scripts\build_windows.bat
REM  Результат:  dist\PipeAlign\PipeAlign.exe
REM ===========================================================================
setlocal

REM Переходим в корень проекта. pushd корректно работает и с UNC-путями
REM (например \\server\share\...), где обычный cd /d завершается ошибкой.
pushd "%~dp0.." || (
    echo [ОШИБКА] Не удалось перейти в корень проекта.
    exit /b 1
)

REM Python ищем сначала как "python", затем как лаунчер "py -3".
set "PY_CMD=python"
where python >nul 2>&1
if errorlevel 1 (
    where py >nul 2>&1
    if errorlevel 1 (
        echo [ОШИБКА] Python не найден ни как "python", ни как "py".
        echo Установите Python 3.10+ и повторите сборку.
        popd
        exit /b 1
    )
    set "PY_CMD=py -3"
)

echo.
echo ============================================
echo  PipeAlign / ТрубоНастрой — сборка .exe
echo ============================================
echo.

echo [1/4] Проверка зависимостей...
%PY_CMD% -c "import PySide6" 2>nul
if errorlevel 1 (
    echo       PySide6 не найден, выполняется установка...
    %PY_CMD% -m pip install "PySide6>=6.6.0" || goto :error
) else (
    echo       PySide6 установлен.
)

%PY_CMD% -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo       PyInstaller не найден, выполняется установка...
    %PY_CMD% -m pip install "pyinstaller>=6.0.0" || goto :error
) else (
    echo       PyInstaller установлен.
)

echo.
echo [2/4] Очистка предыдущей сборки...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [3/4] Сборка PyInstaller...
if exist assets\icon.ico (
    echo       Используется иконка assets\icon.ico
    %PY_CMD% -m PyInstaller --noconfirm --clean --windowed --name PipeAlign ^
        --add-data "data;data" ^
        --add-data "app/resources;app/resources" ^
        --icon "assets\icon.ico" ^
        --collect-all PySide6 ^
        main.py
) else (
    %PY_CMD% -m PyInstaller --noconfirm --clean --windowed --name PipeAlign ^
        --add-data "data;data" ^
        --add-data "app/resources;app/resources" ^
        --collect-all PySide6 ^
        main.py
)

if errorlevel 1 goto :error

echo.
echo [4/4] Проверка результата...
if not exist "dist\PipeAlign\PipeAlign.exe" (
    echo [ОШИБКА] Файл dist\PipeAlign\PipeAlign.exe не создан.
    goto :error
)

echo.
echo ============================================
echo  Готово: dist\PipeAlign\PipeAlign.exe
echo  Журнал пишется в %%APPDATA%%\PipeAlign
echo ============================================
echo.
popd
endlocal
exit /b 0

:error
echo.
echo [ОШИБКА] Сборка не удалась. Подробности — выше в консоли.
popd
endlocal
exit /b 1