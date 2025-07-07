#!/bin/bash

# =================================
# 记忆驱动型AI Agent - 一键启动脚本
# =================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查基本环境
check_dependencies() {
    log_info "检查基本环境..."
    
    # 检查必要命令是否存在
    local missing_commands=()
    
    for cmd in docker python3 curl; do
        if ! command -v $cmd &> /dev/null; then
            missing_commands+=($cmd)
        fi
    done
    
    if [ ${#missing_commands[@]} -ne 0 ]; then
        log_error "缺少必要命令: ${missing_commands[*]}"
        log_error "请确保已安装 Docker、Python3 和 curl"
        exit 1
    fi
    
    # 检查Neo4j是否运行
    if ! check_port 7687; then
        log_warning "Neo4j 未在本地运行 (localhost:7687)"
        log_warning "请确保 Neo4j 服务已启动"
    fi
    
    log_success "环境检查完成"
}

# 检查端口是否被占用
check_port() {
    local port=$1
    if command -v nc &> /dev/null; then
        nc -z localhost $port &> /dev/null
    elif command -v netcat &> /dev/null; then
        netcat -z localhost $port &> /dev/null
    else
        # 备用方法：使用 ss 或 netstat
        if command -v ss &> /dev/null; then
            ss -ln | grep ":$port " &> /dev/null
        elif command -v netstat &> /dev/null; then
            netstat -ln | grep ":$port " &> /dev/null
        else
            # 最后备用：尝试连接
            timeout 1 bash -c "</dev/tcp/localhost/$port" &> /dev/null
        fi
    fi
}

# 启动Redis Docker
start_redis() {
    log_info "启动 Redis Docker 容器..."
    
    # 检查Redis容器是否正在运行
    if sudo docker ps | grep -q "agent-redis"; then
        log_warning "Redis 容器已在运行"
        return
    fi
    
    # 检查容器是否存在但已停止
    if sudo docker ps -a | grep -q "agent-redis"; then
        log_info "发现已存在的 Redis 容器，正在启动..."
        sudo docker start agent-redis
        log_success "Redis 容器已启动"
    else
        log_error "未找到名为 agent-redis 的 Docker 容器"
        log_info "请先创建 Redis 容器或检查容器名称"
        exit 1
    fi
    
    # 等待Redis启动
    log_info "等待 Redis 启动..."
    for i in {1..30}; do
        if sudo docker exec agent-redis redis-cli ping &> /dev/null 2>&1; then
            log_success "Redis 启动成功"
            break
        fi
        if [ $i -eq 30 ]; then
            log_error "Redis 启动超时"
            exit 1
        fi
        sleep 1
    done
}

# 启动Neo4j服务
start_neo4j() {
    log_info "启动 Neo4j 服务..."
    
    # 检查Neo4j服务状态
    if systemctl is-active --quiet neo4j; then
        log_warning "Neo4j 服务已在运行"
    else
        sudo systemctl start neo4j
        log_success "Neo4j 服务启动命令已执行"
    fi
    
    # 等待Neo4j启动
    log_info "等待 Neo4j 启动..."
    for i in {1..60}; do
        if check_port 7687; then
            log_success "Neo4j 启动成功"
            break
        fi
        if [ $i -eq 60 ]; then
            log_error "Neo4j 启动超时"
            exit 1
        fi
        sleep 2
    done
}

# 设置环境变量
setup_environment() {
    log_info "设置环境变量..."
    
    # 确保conda python路径在PATH中
    export PATH="/home/root123/miniconda3/bin:$PATH"
    
    # 模型路径
    if [ -d "/aml/xiaowangge" ]; then
        export MODEL_PATH="/aml/xiaowangge"
        log_info "使用模型路径: $MODEL_PATH"
    elif [ -d "./xiaowangge" ]; then
        export MODEL_PATH="$(pwd)/xiaowangge"
        log_info "使用本地模型路径: $MODEL_PATH"
    elif [ -d "./models" ]; then
        export MODEL_PATH="$(pwd)/models"
        log_info "使用本地模型路径: $MODEL_PATH"
    else
        log_warning "未找到模型目录，请确保模型文件在 /aml/xiaowangge、./xiaowangge 或 ./models 目录下"
        export MODEL_PATH="/aml/xiaowangge"  # 默认使用绝对路径
        log_info "使用默认模型路径: $MODEL_PATH"
    fi
    
    # Redis连接信息
    export REDIS_HOST="localhost"
    export REDIS_PORT="6379"
    
    # Neo4j连接信息
    export NEO4J_URI="bolt://localhost:7687"
    export NEO4J_USER="neo4j"
    export NEO4J_PASSWORD="*****"
    
    # 嵌入服务URL
    export EMBEDDING_SERVICE_URL="http://localhost:7999"
    
    log_success "环境变量设置完成"
}

# 启动嵌入服务
start_embedding_service() {
    log_info "启动嵌入服务..."
    
    # 检查端口是否已被占用
    if check_port 7999; then
        log_warning "端口 7999 已被占用，跳过启动嵌入服务"
        return
    fi
    
    # 检查必要文件
    if [ ! -f "embedding_service.py" ]; then
        log_error "embedding_service.py 文件不存在"
        exit 1
    fi
    
    # 后台启动嵌入服务
    nohup python -m uvicorn embedding_service:app --host 0.0.0.0 --port 7999 > embedding_service.log 2>&1 &
    EMBEDDING_PID=$!
    echo $EMBEDDING_PID > embedding_service.pid
    
    # 等待服务启动
    log_info "等待嵌入服务启动..."
    for i in {1..60}; do
        if curl -s http://localhost:7999/health | grep -q '"status":"healthy"'; then
            log_success "嵌入服务启动成功 (PID: $EMBEDDING_PID)"
            break
        fi
        if [ $i -eq 60 ]; then
            log_error "嵌入服务启动超时"
            log_info "请检查日志: tail -f embedding_service.log"
            exit 1
        fi
        sleep 2
    done
}

# 启动记忆服务
start_memory_service() {
    log_info "启动记忆服务..."
    
    # 检查端口是否已被占用
    if check_port 8000; then
        log_warning "端口 8000 已被占用，跳过启动记忆服务"
        return
    fi
    
    # 检查必要文件
    if [ ! -f "agent_memory_system.py" ]; then
        log_error "agent_memory_system.py 文件不存在"
        exit 1
    fi
    
    # 后台启动记忆服务
    nohup python -m uvicorn agent_memory_system:app --host 0.0.0.0 --port 8000 > memory_service.log 2>&1 &
    MEMORY_PID=$!
    echo $MEMORY_PID > memory_service.pid
    
    # 等待服务启动
    log_info "等待记忆服务启动..."
    for i in {1..60}; do
        if curl -s http://localhost:8000/health | grep -q '"status":"healthy"'; then
            log_success "记忆服务启动成功 (PID: $MEMORY_PID)"
            break
        fi
        if [ $i -eq 60 ]; then
            log_error "记忆服务启动超时"
            log_info "请检查日志: tail -f memory_service.log"
            exit 1
        fi
        sleep 2
    done
}

# 检查服务状态
check_services() {
    log_info "检查所有服务状态..."
    
    echo "======================================"
    echo "           服务状态检查"
    echo "======================================"
    
    # Redis
    if docker ps | grep -q "agent-redis"; then
        echo -e "Redis (Docker):     ${GREEN}✓ 运行中${NC} (localhost:6379)"
    else
        echo -e "Redis (Docker):     ${RED}✗ 未运行${NC}"
    fi
    
    # Neo4j
    if check_port 7687; then
        echo -e "Neo4j (本地):       ${GREEN}✓ 运行中${NC} (localhost:7687)"
    else
        echo -e "Neo4j (本地):       ${YELLOW}? 未检测到${NC} (localhost:7687)"
    fi
    
    # 嵌入服务
    if check_port 7999; then
        if [ -f "embedding_service.pid" ]; then
            PID=$(cat embedding_service.pid)
            if kill -0 $PID 2>/dev/null; then
                echo -e "嵌入服务:           ${GREEN}✓ 运行中${NC} (localhost:7999, PID: $PID)"
            else
                echo -e "嵌入服务:           ${YELLOW}? 端口占用但PID无效${NC} (localhost:7999)"
            fi
        else
            echo -e "嵌入服务:           ${YELLOW}? 运行中但无PID文件${NC} (localhost:7999)"
        fi
    else
        echo -e "嵌入服务:           ${RED}✗ 未运行${NC}"
    fi
    
    # 记忆服务
    if check_port 8000; then
        if [ -f "memory_service.pid" ]; then
            PID=$(cat memory_service.pid)
            if kill -0 $PID 2>/dev/null; then
                echo -e "记忆服务:           ${GREEN}✓ 运行中${NC} (localhost:8000, PID: $PID)"
            else
                echo -e "记忆服务:           ${YELLOW}? 端口占用但PID无效${NC} (localhost:8000)"
            fi
        else
            echo -e "记忆服务:           ${YELLOW}? 运行中但无PID文件${NC} (localhost:8000)"
        fi
    else
        echo -e "记忆服务:           ${RED}✗ 未运行${NC}"
    fi
    
    echo "======================================"
    
    # 显示端口占用情况
    echo ""
    echo "端口占用详情:"
    if command -v ss &> /dev/null; then
        ss -tlnp | grep -E ":(6379|7687|7999|8000) " | while read line; do
            echo "  $line"
        done
    elif command -v netstat &> /dev/null; then
        netstat -tlnp | grep -E ":(6379|7687|7999|8000) " | while read line; do
            echo "  $line"
        done
    fi
}

# 停止服务
stop_services() {
    log_info "停止所有服务..."
    
    # 停止记忆服务
    if [ -f "memory_service.pid" ]; then
        PID=$(cat memory_service.pid)
        if kill -0 $PID 2>/dev/null; then
            kill $PID
            log_success "记忆服务已停止"
        fi
        rm -f memory_service.pid
    fi
    
    # 停止嵌入服务
    if [ -f "embedding_service.pid" ]; then
        PID=$(cat embedding_service.pid)
        if kill -0 $PID 2>/dev/null; then
            kill $PID
            log_success "嵌入服务已停止"
        fi
        rm -f embedding_service.pid
    fi
    
    # 停止Redis Docker
    if sudo docker ps | grep -q "agent-redis"; then
        sudo docker stop agent-redis
        log_success "Redis Docker 已停止"
    fi
    
    # 停止Neo4j服务（可选，通常不需要停止系统服务）
    # sudo systemctl stop neo4j
    # log_info "Neo4j 服务已停止（如需要）"
}

# 注入测试数据
inject_test_data() {
    log_info "注入测试数据..."
    
    if [ -f "inject_massive_data.py" ]; then
        python3 inject_massive_data.py
        log_success "测试数据注入完成"
    else
        log_warning "inject_massive_data.py 文件不存在，跳过数据注入"
    fi
}

# 主函数
main() {
    case "${1:-start}" in
        "start")
            echo "========================================"
            echo "    记忆驱动型AI Agent - 服务启动"
            echo "========================================"
            
            check_dependencies
            start_redis
            start_neo4j
            setup_environment
            start_embedding_service
            start_memory_service
            
            echo ""
            check_services
            
            echo ""
            log_success "所有服务启动完成！"
            echo ""
            echo "接下来您可以："
            echo "1. 运行 Agent 客户端: python3 agent_client3_memory_driven.py"
            echo "2. 注入测试数据: ./start_services.sh inject"
            echo "3. 检查服务状态: ./start_services.sh status"
            echo "4. 停止所有服务: ./start_services.sh stop"
            echo ""
            ;;
            
        "stop")
            echo "========================================"
            echo "    记忆驱动型AI Agent - 服务停止"
            echo "========================================"
            stop_services
            ;;
            
        "restart")
            echo "========================================"
            echo "    记忆驱动型AI Agent - 服务重启"
            echo "========================================"
            stop_services
            sleep 2
            main start
            ;;
            
        "status")
            check_services
            ;;
            
        "inject")
            inject_test_data
            ;;
            
        "logs")
            echo "========================================"
            echo "           服务日志查看"
            echo "========================================"
            echo ""
            echo "Redis 日志:"
            docker logs agent-redis --tail 20
            echo ""
            echo "嵌入服务日志:"
            if [ -f "embedding_service.log" ]; then
                tail -20 embedding_service.log
            else
                echo "日志文件不存在"
            fi
            echo ""
            echo "记忆服务日志:"
            if [ -f "memory_service.log" ]; then
                tail -20 memory_service.log
            else
                echo "日志文件不存在"
            fi
            ;;
            
        "sysinfo")
            echo "========================================"
            echo "           系统信息"
            echo "========================================"
            echo "操作系统: $(uname -s) $(uname -r)"
            echo "架构: $(uname -m)"
            if [ -f /etc/os-release ]; then
                echo "发行版: $(grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '\"')"
            fi
            echo "Python版本: $(python3 --version)"
            echo "Docker版本: $(docker --version)"
            if command -v docker-compose &> /dev/null; then
                echo "Docker Compose版本: $(docker-compose --version)"
            fi
            echo ""
            echo "内存使用:"
            free -h
            echo ""
            echo "磁盘使用:"
            df -h .
            echo ""
            ;;
            
        "help"|"--help"|"-h")
            echo "记忆驱动型AI Agent - 服务管理脚本 (Linux版)"
            echo ""
            echo "用法: $0 [命令]"
            echo ""
            echo "命令:"
            echo "  start    启动所有服务 (默认)"
            echo "  stop     停止所有服务"
            echo "  restart  重启所有服务"
            echo "  status   检查服务状态"
            echo "  inject   注入测试数据"
            echo "  logs     查看服务日志"
            echo "  sysinfo  显示系统信息"
            echo "  help     显示此帮助信息"
            echo ""
            echo "服务架构:"
            echo "  - Redis: Docker容器运行 (localhost:6379)"
            echo "  - Neo4j: 本地服务运行 (localhost:7687)"
            echo "  - 嵌入服务: Python本地运行 (localhost:7999)"
            echo "  - 记忆服务: Python本地运行 (localhost:8000)"
            echo ""
            echo "前置要求:"
            echo "  - Docker 和 Docker Compose 已安装"
            echo "  - Neo4j 服务已安装并运行"
            echo "  - Python3 环境已配置"
            echo "  - SQLite 已安装"
            echo ""
            ;;
            
        *)
            log_error "未知命令: $1"
            echo "使用 '$0 help' 查看可用命令"
            exit 1
            ;;
    esac
}

# 捕获中断信号
trap 'echo ""; log_info "收到中断信号，正在停止服务..."; stop_services; exit 0' INT TERM

# 执行主函数
main "$@"
