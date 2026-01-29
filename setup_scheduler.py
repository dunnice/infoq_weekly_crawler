#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定时任务配置脚本
支持 macOS launchd 和 Linux crontab
"""

import os
import sys
import stat
import subprocess
from pathlib import Path


# 获取当前脚本目录
SCRIPT_DIR = Path(__file__).parent.absolute()
CRAWLER_SCRIPT = SCRIPT_DIR / "infoq_crawler.py"
WRAPPER_SCRIPT = SCRIPT_DIR / "run_crawler.sh"

# launchd 配置
LAUNCHD_PLIST_NAME = "com.user.infoq-weekly-crawler.plist"
LAUNCHD_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / LAUNCHD_PLIST_NAME


def create_wrapper_script():
    """创建 Shell 包装脚本"""
    
    wrapper_content = f'''#!/bin/bash
# InfoQ 周刊爬虫包装脚本
# 自动激活虚拟环境并运行爬虫

SCRIPT_DIR="{SCRIPT_DIR}"
cd "$SCRIPT_DIR"

# 检查并激活虚拟环境
if [ -d "$SCRIPT_DIR/venv" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
elif [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# 运行爬虫
python3 "$SCRIPT_DIR/infoq_crawler.py"

# 发送完成通知（macOS）
if [[ "$OSTYPE" == "darwin"* ]]; then
    if [ $? -eq 0 ]; then
        osascript -e 'display notification "InfoQ 周刊已成功更新！" with title "InfoQ 周刊爬虫"'
    else
        osascript -e 'display notification "更新失败，请检查日志" with title "InfoQ 周刊爬虫" sound name "Basso"'
    fi
fi
'''
    
    with open(WRAPPER_SCRIPT, 'w') as f:
        f.write(wrapper_content)
    
    # 添加执行权限
    os.chmod(WRAPPER_SCRIPT, os.stat(WRAPPER_SCRIPT).st_mode | stat.S_IEXEC)
    print(f"✓ 创建包装脚本: {WRAPPER_SCRIPT}")


def create_launchd_plist():
    """创建 macOS launchd 配置文件"""
    
    plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.infoq-weekly-crawler</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>{WRAPPER_SCRIPT}</string>
    </array>
    
    <key>StartCalendarInterval</key>
    <dict>
        <!-- 每周一早上 8:00 执行 -->
        <key>Weekday</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    
    <key>StandardOutPath</key>
    <string>{SCRIPT_DIR}/launchd_stdout.log</string>
    
    <key>StandardErrorPath</key>
    <string>{SCRIPT_DIR}/launchd_stderr.log</string>
    
    <key>WorkingDirectory</key>
    <string>{SCRIPT_DIR}</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
'''
    
    # 确保目录存在
    LAUNCHD_PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with open(LAUNCHD_PLIST_PATH, 'w') as f:
        f.write(plist_content)
    
    print(f"✓ 创建 launchd 配置: {LAUNCHD_PLIST_PATH}")


def install_launchd():
    """安装 launchd 定时任务"""
    
    # 先卸载旧的（如果存在）
    subprocess.run(['launchctl', 'unload', str(LAUNCHD_PLIST_PATH)], 
                   capture_output=True, check=False)
    
    # 加载新配置
    result = subprocess.run(['launchctl', 'load', str(LAUNCHD_PLIST_PATH)], 
                           capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✓ launchd 定时任务已安装")
        print(f"  任务将在每周一 08:00 自动执行")
    else:
        print(f"✗ 安装失败: {result.stderr}")
        return False
    
    return True


def uninstall_launchd():
    """卸载 launchd 定时任务"""
    
    result = subprocess.run(['launchctl', 'unload', str(LAUNCHD_PLIST_PATH)], 
                           capture_output=True, text=True)
    
    if LAUNCHD_PLIST_PATH.exists():
        LAUNCHD_PLIST_PATH.unlink()
    
    print("✓ launchd 定时任务已卸载")


def show_crontab_command():
    """显示 crontab 命令（用于 Linux 系统）"""
    
    cron_line = f"0 8 * * 1 {WRAPPER_SCRIPT}"
    
    print("\n" + "="*50)
    print("Linux 系统请使用 crontab:")
    print("="*50)
    print("\n1. 编辑 crontab:")
    print("   crontab -e")
    print("\n2. 添加以下行（每周一 08:00 执行）:")
    print(f"   {cron_line}")
    print("\n3. 保存并退出")
    print("="*50)


def run_now():
    """立即运行一次爬虫"""
    print("\n正在执行爬虫...")
    result = subprocess.run(['bash', str(WRAPPER_SCRIPT)], cwd=str(SCRIPT_DIR))
    return result.returncode == 0


def check_status():
    """检查定时任务状态"""
    
    print("\n" + "="*50)
    print("定时任务状态")
    print("="*50)
    
    # 检查 launchd
    result = subprocess.run(['launchctl', 'list'], capture_output=True, text=True)
    if 'infoq-weekly-crawler' in result.stdout:
        print("✓ launchd 任务已安装并运行中")
        
        # 获取详细信息
        result2 = subprocess.run(['launchctl', 'list', 'com.user.infoq-weekly-crawler'], 
                                capture_output=True, text=True)
        if result2.returncode == 0:
            print(f"  {result2.stdout.strip()}")
    else:
        print("✗ launchd 任务未安装")
    
    # 检查文件
    print(f"\n配置文件: {LAUNCHD_PLIST_PATH}")
    print(f"  存在: {'是' if LAUNCHD_PLIST_PATH.exists() else '否'}")
    
    print(f"\n包装脚本: {WRAPPER_SCRIPT}")
    print(f"  存在: {'是' if WRAPPER_SCRIPT.exists() else '否'}")


def setup_virtualenv():
    """设置虚拟环境"""
    
    venv_path = SCRIPT_DIR / "venv"
    
    if venv_path.exists():
        print(f"✓ 虚拟环境已存在: {venv_path}")
        return True
    
    print("正在创建虚拟环境...")
    result = subprocess.run([sys.executable, '-m', 'venv', str(venv_path)], 
                           capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"✗ 创建虚拟环境失败: {result.stderr}")
        return False
    
    print(f"✓ 创建虚拟环境: {venv_path}")
    
    # 安装依赖
    pip_path = venv_path / "bin" / "pip"
    requirements_file = SCRIPT_DIR / "requirements.txt"
    
    if requirements_file.exists():
        print("正在安装依赖...")
        result = subprocess.run([str(pip_path), 'install', '-r', str(requirements_file)], 
                               capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✓ 依赖安装完成")
        else:
            print(f"✗ 依赖安装失败: {result.stderr}")
            return False
    
    return True


def print_help():
    """打印帮助信息"""
    
    print("""
InfoQ 周刊爬虫 - 定时任务配置工具
=====================================

用法: python setup_scheduler.py [命令]

命令:
    install     安装定时任务（创建配置并启用）
    uninstall   卸载定时任务
    status      查看定时任务状态
    run         立即执行一次爬虫
    setup       仅设置虚拟环境和配置文件
    help        显示此帮助信息

示例:
    python setup_scheduler.py install   # 安装定时任务
    python setup_scheduler.py run       # 手动执行一次
    python setup_scheduler.py status    # 查看状态
""")


def main():
    """主函数"""
    
    if len(sys.argv) < 2:
        print_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == 'help':
        print_help()
        
    elif command == 'setup':
        print("\n设置虚拟环境和配置文件...")
        setup_virtualenv()
        create_wrapper_script()
        create_launchd_plist()
        show_crontab_command()
        print("\n✓ 设置完成！使用 'python setup_scheduler.py install' 安装定时任务")
        
    elif command == 'install':
        print("\n安装定时任务...")
        setup_virtualenv()
        create_wrapper_script()
        create_launchd_plist()
        
        if sys.platform == 'darwin':
            install_launchd()
        else:
            show_crontab_command()
        
        print("\n✓ 安装完成！")
        check_status()
        
    elif command == 'uninstall':
        print("\n卸载定时任务...")
        if sys.platform == 'darwin':
            uninstall_launchd()
        else:
            print("请手动编辑 crontab 删除相关行: crontab -e")
        
    elif command == 'status':
        check_status()
        
    elif command == 'run':
        create_wrapper_script()
        run_now()
        
    else:
        print(f"未知命令: {command}")
        print_help()


if __name__ == "__main__":
    main()
