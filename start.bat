@echo off
chcp 65001 >nul 2>&1
echo ====================================
echo   求人マッチングツール 起動中...
echo ====================================
echo.
echo ブラウザが自動で開きます。
echo 閉じるにはこのウィンドウで Ctrl+C を押してください。
echo.
streamlit run app.py --server.port 8501
