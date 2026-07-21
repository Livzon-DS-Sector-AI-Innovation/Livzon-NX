#!/bin/bash
cd /home/wangtao/Livzon/dazah-frontend

# 杀死已存在的进程
pkill -f "next dev" 2>/dev/null
sleep 2

# 启动开发服务器
nohup npm run dev > /tmp/next-dev.log 2>&1 &

# 等待服务器启动
echo "正在启动开发服务器..."
for i in {1..30}; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/rd/route-development | grep -q "200"; then
        IP=$(hostname -I | awk '{print $1}')
        echo "✓ 服务器已启动"
        echo "访问地址: http://$IP:3000/rd/route-development"
        exit 0
    fi
    sleep 1
done

echo "✗ 启动失败，请检查 /tmp/next-dev.log"
exit 1
