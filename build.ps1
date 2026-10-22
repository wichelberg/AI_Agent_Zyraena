# Builds dist\Zyraena.exe with PyInstaller (Windows, Python with requirements + pyinstaller installed).
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Prefer the py launcher (picks the newest Python 3); fall back to python on PATH.
$python = if (Get-Command py -ErrorAction SilentlyContinue) { @("py", "-3") } else { @("python") }
& $python[0] $python[1..9] -m PyInstaller --noconfirm --onefile --windowed --name Zyraena --icon assets\zyraena.ico `
    --add-data "assets;assets" --add-data "sounds;sounds" --add-data "voice_worker.py;." --add-data "speech_worker.py;." --add-data "tts_worker.py;." --add-data "sleep_hook.ps1;." `
    --hidden-import email.policy --hidden-import email.message --hidden-import email.utils `
    --hidden-import imaplib --hidden-import smtplib --hidden-import html --hidden-import mimetypes `
    --hidden-import secrets --hidden-import argparse --hidden-import urllib.request `
    --hidden-import send2trash --hidden-import yt_dlp --hidden-import websockets.sync.server `
    main.py

Write-Host "Built dist\Zyraena.exe. Put .env (and optionally personality.md, config.json) next to it."
