@echo off
REM ===========================================================================
REM  PipeAlign / ТрубоНастрой — запуск из исходников
REM  Запускайте из любого каталога:  scripts\run_windows.bat
REM ===========================================================================
setlocal

REM pushd работает и с сетевыми путями (\\server\share\...), где cd /d не работает.
pushd "%~dp0.." || (
    echo [ОШИБКА] Не удалось перейти в корень проекта.
    exit /b 1
)

set "PY_CMD=python"
where python >nul 2>&1
if errorlevel 1 (
    where py >nul 2>&1
    if errorlevel 1 (
        echo [ОШИБКА] Python не найден ни как "python", ни как "py".
        echo Установите Python 3.10+ и выполните: pip install -r requirements.txt
        popd
        exit /b 1
    )
    set "PY_CMD=py -3"
)

%PY_CMD% -c "import PySide6" 2>nul
if errorlevel 1 (
    echo PySide6 не найден, выполняется установка...
    %PY_CMD% -m pip install -r requirements.txt || goto :error
)

echo Запуск PipeAlign из исходников...
echo.
%PY_CMD% main.py
if errorlevel 1 goto :error

popd
endlocal
exit /b 0

:error
echo.
echo [ОШИБКА] Не удалось запустить приложение.
echo Убедитесь, что зависимости установлены: pip install -r requirements.txt
popd
endlocal
exit /b 1