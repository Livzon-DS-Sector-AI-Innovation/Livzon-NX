#!/bin/bash
cd /home/wangtao/Livzon/dazah-backend
export DEBUG=true
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
