@echo off
chcp 65001 >nul 2>&1
echo ====================================
echo   求人マッチングツール セットアップ
echo ====================================
echo.

REM Pythonの確認
python --version >nul 2>&1
if errorlevel 1 (
    echo [エラー] Pythonがインストールされていません。
    echo https://www.python.org/downloads/ からインストールしてください。
    pause
    exit /b 1
)

echo [1/2] 依存パッケージをインストール中...
pip install -r requirements.txt

echo.
echo [2/2] セットアップ完了！
echo.
echo ====================================
echo   起動方法: start.bat をダブルクリック
echo ====================================
pause
