@echo off
rem Builds tools\mpq_extract.exe - the offline helper that pulls files out of the game
rem archives (DIABDAT.MPQ, TH4data.mor, 13cirlces.MPQ) while authoring interface assets.
rem Run from a Developer Command Prompt, or let this script find vcvars32 itself.

setlocal
if "%VCINSTALLDIR%"=="" (
	for %%V in (
		"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars32.bat"
		"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat"
		"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars32.bat"
	) do if exist %%V call %%V >nul
)

set TOOLS=%~dp0
set LIB_PKLIB=%TOOLS%..\lib\pklib

if not exist "%TOOLS%obj" mkdir "%TOOLS%obj"
cl /nologo /EHsc /O2 /I"%TOOLS%shim" /I"%LIB_PKLIB%" /Fe:"%TOOLS%mpq_extract.exe" /Fo:"%TOOLS%obj\\" ^
	"%TOOLS%mpq_extract.cpp" "%LIB_PKLIB%\explode.cpp"
endlocal
