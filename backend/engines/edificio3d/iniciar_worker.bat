@echo off
REM ConstruPilot - posto Edificio 3D (Blender + ArcGIS Pro). Ajuste os caminhos e o token.
set CONSTRUPILOT_API=https://construpilot.pt/api
set EDIFICIO3D_WORKER_TOKEN=COLOCAR_O_TOKEN_AQUI
set BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 4.2\blender.exe
set ARCGIS_PROPY=C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\propy.bat
set ARCGIS_APRX=
"%ARCGIS_PROPY%" "%~dp0worker_local.py"
pause
