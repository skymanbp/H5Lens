@echo off
echo.
echo  Removing H5 Lens file associations...
echo.
for %%x in (.h5 .hdf5 .hdf .he5 .nc) do (
    reg delete "HKCU\Software\Classes\%%x" /f >nul 2>&1
)
reg delete "HKCU\Software\Classes\H5Lens.HDF5" /f >nul 2>&1
echo  Done. Associations removed.
echo.
pause
