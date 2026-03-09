#!/usr/bin/env python3
"""
BiboBot 启动脚本 - 简化开发和调试

用法:
    python start.py              # 启动服务
    python start.py --build      # 先构建沙箱镜像，再启动
    python start.py --debug      # 详细日志模式
    python start.py --no-docker  # 不使用 Docker 沙箱（原生工具）
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path

# 颜色输出
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

def run(cmd, check=True):
    """运行命令并打印"""
    print(f"{YELLOW}> {' '.join(cmd)}{RESET}")
    result = subprocess.run(cmd, check=check)
    return result.returncode == 0

def build_sandbox_image():
    """构建 Docker 沙箱镜像"""
    print(f"\n{GREEN}🔨 构建 Docker 沙箱镜像...{RESET}")
    
    # 检查 Dockerfile 是否存在
    dockerfile = Path("docker/Dockerfile.sandbox")
    if not dockerfile.exists():
        print(f"{RED}❌ 未找到 {dockerfile}{RESET}")
        return False
    
    # 构建命令
    cmd = [
        "docker", "build",
        "-f", str(dockerfile),
        "-t", "bibobot-sandbox:latest",
        "."
    ]
    
    return run(cmd, check=False)

def check_docker():
    """检查 Docker 是否可用"""
    result = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"{RED}❌ Docker 未运行或没有权限{RESET}")
        print("请确保 Docker 已启动，且当前用户在 docker 组")
        return False
    return True

def check_sandbox_image():
    """检查沙箱镜像是否存在"""
    result = subprocess.run(
        ["docker", "images", "-q", "bibobot-sandbox:latest"],
        capture_output=True,
        text=True
    )
    return result.stdout.strip() != ""

def main():
    parser = argparse.ArgumentParser(description="BiboBot 启动脚本")
    parser.add_argument("--build", action="store_true", help="构建沙箱镜像")
    parser.add_argument("--debug", action="store_true", help="详细日志模式")
    parser.add_argument("--no-docker", action="store_true", help="不使用 Docker 沙箱")
    args = parser.parse_args()
    
    # 检查虚拟环境
    if not Path("venv").exists():
        print(f"{RED}❌ 未找到 venv 目录，请先创建虚拟环境{RESET}")
        sys.exit(1)
    
    # 激活虚拟环境
    activate_script = "venv/bin/activate"
    if not Path(activate_script).exists():
        print(f"{RED}❌ 未找到 {activate_script}{RESET}")
        sys.exit(1)
    
    # 设置环境变量
    env = os.environ.copy()
    env["PATH"] = str(Path("venv/bin").absolute()) + ":" + env["PATH"]
    
    # 如果不使用 Docker，设置环境变量
    if args.no_docker:
        print(f"{YELLOW}⚠️  不使用 Docker 沙箱，使用原生工具（受黑白名单限制）{RESET}")
        env["USE_DOCKER_SANDBOX"] = "false"
    else:
        # 检查 Docker
        if not check_docker():
            print(f"{YELLOW}⚠️  Docker 不可用，自动切换到原生工具模式{RESET}")
            env["USE_DOCKER_SANDBOX"] = "false"
        else:
            # 检查沙箱镜像
            if not check_sandbox_image():
                print(f"{YELLOW}⚠️  沙箱镜像不存在{RESET}")
                if args.build:
                    if not build_sandbox_image():
                        print(f"{RED}❌ 构建失败，切换到原生工具模式{RESET}")
                        env["USE_DOCKER_SANDBOX"] = "false"
                else:
                    print(f"{YELLOW}   运行 'python start.py --build' 构建镜像{RESET}")
                    print(f"{YELLOW}   或使用 'python start.py --no-docker' 跳过 Docker{RESET}")
                    env["USE_DOCKER_SANDBOX"] = "false"
    
    # 启动服务
    print(f"\n{GREEN}🚀 启动 BiboBot 服务...{RESET}")
    print(f"{GREEN}   访问: http://localhost:8000{RESET}")
    print(f"{GREEN}   API:  http://localhost:8000/api/agent{RESET}")
    print(f"{GREEN}   文档: http://localhost:8000/docs{RESET}\n")
    
    log_level = "debug" if args.debug else "info"
    
    cmd = [
        "python", "-m", "uvicorn",
        "app.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload",
        "--log-level", log_level
    ]
    
    try:
        subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}👋 服务已停止{RESET}")

if __name__ == "__main__":
    main()
