#!/bin/bash
set -e

cd "$(dirname "$0")"

VERSION=${VERSION:-v1.0.4}
IMAGE_NAME=${IMAGE_NAME:-aitools:$VERSION}

echo "=== 构建镜像: $IMAGE_NAME ==="
#docker build -t $IMAGE_NAME .

echo "=== 创建 Docker 网络 ==="
docker network create aitools-net 2>/dev/null || true

echo "=== 启动 Ollama ==="
if docker ps -a --format '{{.Names}}' | grep -q '^ollama$'; then
    echo "发现已有 ollama 容器，将其加入网络..."
    docker network connect aitools-net ollama 2>/dev/null || true
    docker start ollama 2>/dev/null || true
else
    docker run -d \
        --name ollama \
        --network aitools-net \
        -p 6001:11434 \
        -v ollama_data:/root/.ollama \
        ollama/ollama:latest
    echo "Ollama 已启动，等待就绪..."
    sleep 3
fi

echo "=== 检查 Ollama 模型 ==="
MODEL_COUNT=$(docker exec ollama ollama list 2>/dev/null | tail -n +2 | wc -l || echo "0")
if [ "$MODEL_COUNT" -eq "0" ]; then
    echo "Ollama 中没有模型，正在拉取 qwen3:0.6b..."
    docker exec ollama ollama pull qwen3:0.6b
fi

echo "=== 将 toolserver 加入网络 ==="
if docker ps -a --format '{{.Names}}' | grep -q '^toolsever'; then
    docker network connect aitools-net toolsever-v1.0.1 2>/dev/null || true
    echo "toolserver 已加入 aitools-net"
fi

echo "=== 停止旧容器 ==="
docker rm -f aitools 2>/dev/null || true

echo "=== 启动 AITools ==="
docker run -d -p 6002:8000 \
    --network aitools-net \
    -e LLM_PROVIDER=all \
    -e OLLAMA_API_BASE=http://ollama:11434 \
    --name aitools $IMAGE_NAME

echo ""
echo "=== 启动成功 ==="
echo "访问: http://localhost:6002"
echo ""
echo "查看 Ollama 模型列表:"
echo "  docker exec ollama ollama list"