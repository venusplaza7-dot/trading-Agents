# In fv75.github.dev terminal
# Download file: drag-drop main-24-7.py to replace main.py
# Or paste:
cat > main-24-7.py << 'PY'
# (copy content from file above)
PY
cp main-24-7.py main.py

# Make it run 24/7 even when you close phone:
cat > run-24-7.sh << 'SH'
#!/bin/bash
while true; do
  echo "[$(date)] Starting 24/7 bot..."
  python main.py
  echo "[$(date)] Crashed - restarting in 5s..."
  sleep 5
done
SH
chmod +x run-24-7.sh
nohup ./run-24-7.sh > trading.log 2>&1 &
echo "✅ 24/7 RUNNING - check with: tail -f trading.log"
