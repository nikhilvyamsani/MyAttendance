#!/bin/bash

# Start the Docker container in detached mode (optional)
docker run -d -p 8501:8501 nikhilvyamsani/myattendance-app:latest

# Wait briefly for container to boot
sleep 3

# Open Streamlit app in browser (platform-specific)
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
  xdg-open http://localhost:8501
elif [[ "$OSTYPE" == "darwin"* ]]; then
  open http://localhost:8501
elif [[ "$OSTYPE" == "cygwin" || "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
  start http://localhost:8501
else
  echo "Please open http://localhost:8501 manually in your browser."
fi
