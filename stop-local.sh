#!/usr/bin/env bash
pkill -f "uvicorn (gateway|catalog|pricing).main:app" 2>/dev/null || true
pkill -f "loadgen/main.py" 2>/dev/null || true
echo "已停止"
