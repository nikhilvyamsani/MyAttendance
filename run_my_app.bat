@echo off
echo Checking for existing container named myattendance-app...

REM Stop the container if it is running
docker stop myattendance-app >nul 2>&1

REM Remove the container if it exists
docker rm myattendance-app >nul 2>&1

echo Starting MyAttendance app in Docker (detached mode)...
docker run -d -p 8501:8501 --name myattendance-app nikhilvyamsani/myattendance-app

echo Waiting for Streamlit to start...
timeout /t 5 >nul

echo Launching browser to http://localhost:8501 ...
start http://localhost:8501

echo App is running in background.
pause
