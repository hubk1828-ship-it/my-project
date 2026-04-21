#!/bin/bash
cd /home/drpcsa/repositories/my-project/backend
source venv311/bin/activate
exec python -m uvicorn app.main:app --host 127.0.0.1 --port 33442
