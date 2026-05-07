@echo off
echo Building Custom SQLite with B-Tree Tracing...

:: 1. Check if GCC is in PATH
where gcc >nul 2>nul
if %errorlevel% == 0 (
    echo [GCC] Found GCC compiler.
    gcc -O2 -shared -fPIC sqlite-src\src\sqlite3.c -o sqlite3_custom.dll
    gcc -O2 sqlite-src\src\shell.c.in sqlite-src\src\sqlite3.c -o sqlite3_custom.exe
    echo [SUCCESS] Built sqlite3_custom.dll and sqlite3_custom.exe
    exit /b 0
)

:: 2. Check if cl.exe is already in PATH
where cl >nul 2>nul
if %errorlevel% == 0 (
    echo [MSVC] Found MSVC compiler in PATH.
    goto msvc_compile
)

:: 3. Try to locate vcvars64.bat to initialize MSVC environment
echo [INFO] cl.exe not in PATH. Searching for Visual Studio installation...
set "VCVARS="

:: Check common paths for VS 2022 and Insiders
if exist "C:\Program Files\Microsoft Visual Studio\18\Insiders\VC\Auxiliary\Build\vcvars64.bat" set "VCVARS=C:\Program Files\Microsoft Visual Studio\18\Insiders\VC\Auxiliary\Build\vcvars64.bat"
if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" set "VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if exist "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat" set "VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat"
if exist "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat" set "VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat"

:: Check common paths for VS 2019
if exist "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvars64.bat" set "VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvars64.bat"
if exist "C:\Program Files (x86)\Microsoft Visual Studio\2019\Enterprise\VC\Auxiliary\Build\vcvars64.bat" set "VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2019\Enterprise\VC\Auxiliary\Build\vcvars64.bat"
if exist "C:\Program Files (x86)\Microsoft Visual Studio\2019\Professional\VC\Auxiliary\Build\vcvars64.bat" set "VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2019\Professional\VC\Auxiliary\Build\vcvars64.bat"

if defined VCVARS (
    echo [INFO] Found VS environment script: %VCVARS%
    call "%VCVARS%"
    goto msvc_compile
)

echo [ERROR] No C compiler found in PATH, and could not locate vcvars64.bat.
echo Please open the "Developer Command Prompt for VS" and run this script from there.
pause
exit /b 1

:msvc_compile
echo [MSVC] Compiling custom SQLite...
:: Note: The SQLite source dir changed to sqlite-src based on user repo
cl /O2 /LD sqlite-src\sqlite3.c /Fesqlite3_custom.dll
cl /O2 sqlite-src\shell.c sqlite-src\sqlite3.c /Fesqlite3_custom.exe
echo [SUCCESS] Built sqlite3_custom.dll and sqlite3_custom.exe
pause
exit /b 0
