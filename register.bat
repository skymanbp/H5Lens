@echo off
chcp 65001 >nul 2>&1
echo.
echo  ====================================
echo   H5 Lens - Register File Association
echo  ====================================
echo.

:: Auto-detect exe path relative to this bat file
set "BATDIR=%~dp0"
set "EXEPATH="

if exist "%BATDIR%dist\H5Lens\H5Lens.exe" (
    set "EXEPATH=%BATDIR%dist\H5Lens\H5Lens.exe"
) else if exist "%BATDIR%dist\H5Lens.exe" (
    set "EXEPATH=%BATDIR%dist\H5Lens.exe"
) else if exist "%BATDIR%H5Lens.exe" (
    set "EXEPATH=%BATDIR%H5Lens.exe"
)

if "%EXEPATH%"=="" (
    echo  [ERROR] Could not find H5Lens.exe
    echo  Put this .bat in the H5Lens folder and build first.
    echo.
    pause
    exit /b 1
)

echo  Found: %EXEPATH%
echo.
echo  Will register for: .h5  .hdf5  .hdf  .he5  .nc
echo.

:: Register app class
reg add "HKCU\Software\Classes\H5Lens.HDF5" /ve /d "HDF5 Data File" /f >nul
reg add "HKCU\Software\Classes\H5Lens.HDF5\DefaultIcon" /ve /d "\"%EXEPATH%\",0" /f >nul
reg add "HKCU\Software\Classes\H5Lens.HDF5\shell\open" /ve /d "Open with H5 Lens" /f >nul
reg add "HKCU\Software\Classes\H5Lens.HDF5\shell\open\command" /ve /d "\"%EXEPATH%\" \"%%1\"" /f >nul

:: Register extensions
for %%x in (.h5 .hdf5 .hdf .he5 .nc) do (
    reg add "HKCU\Software\Classes\%%x" /ve /d "H5Lens.HDF5" /f >nul
)

echo  Done! Double-click .h5 files to open with H5 Lens.
echo.
pause
