import os
import logging
import time
import json
import hashlib
import configparser
import argparse
import socket
from pathlib import Path
from datetime import datetime
from croniter import croniter
from p123client import P123Client


# 屏蔽 httpx / httpcore 的 HTTP 请求 INFO 日志（避免每个请求刷一行，污染日志）
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
# ======================== 配置文件路径 ======================== 
# 配置文件路径：基于脚本所在目录，避免在不同工作目录下找不到 settings.ini
CONF_DIR = Path(__file__).resolve().parent / "conf"
CONF_FILE = CONF_DIR / "settings.ini"

# ======================== 全局状态 ======================== 
# 强制同步状态标识
is_force_sync_running = False

# ======================== 默认配置 ========================
DEFAULT_CONFIG = {
    "General": {
        "seconds_upload_min_size": "500",  # 500MB
        "duplicate_handling": "2",
        "cron_expression": "0 * * * *",   # 每小时执行一次
        "force_upload_large_file": "false",  # 强制同步时，大文件秒传失败是否转为分片上传
    },
    "Account": {
        "passport": "您的手机号或邮箱",
        "password": "您的密码",
        "client_id": "",
        "client_secret": "",
    },
    "SyncRules": {
        "rule1": "upload/AAA, 我的备份/AAA",
        "rule2": "upload/BBB, strm/BBB",
    }
}

# ======================== 配置管理 ========================
def load_or_create_config():
    """加载或创建配置文件"""
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    
    if not CONF_FILE.exists():
        print(f"⚠️ 配置文件不存在: {CONF_FILE}")
        print("正在创建默认配置文件...")
        
        config = configparser.ConfigParser()
        for section, options in DEFAULT_CONFIG.items():
            config[section] = options
        
        with open(CONF_FILE, "w", encoding="utf-8") as f:
            config.write(f)
        
        print(f"✅ 已创建默认配置文件: {CONF_FILE}")
        print("请修改配置文件后重新运行程序")
        return None
    
    config = configparser.ConfigParser()
    config.read(CONF_FILE, encoding="utf-8")
    
    # 验证必需部分
    for section in ["General", "Account"]:
        if section not in config:
            print(f"❌ 配置文件缺少部分: [{section}]")
            return None
    
    return config

class ConfigManager:
    """实时更新的配置文件管理器（忽略账号密码变更）"""
    def __init__(self, config_file):
        self.config_file = config_file
        self.config = self.load_config()
        self.last_mtime = os.path.getmtime(config_file)
        print("⚠️ 注意: 账号密码变更需要手动重启程序才能生效")
    
    def load_config(self):
        """安全加载配置文件"""
        try:
            config = configparser.ConfigParser()
            config.read(self.config_file, encoding="utf-8")
            print("✅ 配置文件已加载")
            return config
        except Exception as e:
            print(f"❌ 配置文件加载失败: {str(e)}")
            # 返回当前有效配置作为回退
            return self.config if hasattr(self, 'config') else None
    
    def check_and_reload(self):
        """检查并重新加载配置文件（如果需要）"""
        try:
            current_mtime = os.path.getmtime(self.config_file)
            
            if current_mtime > self.last_mtime:
                print("⚠️ 检测到配置文件修改")
                self.last_mtime = current_mtime
                
                # 加载新配置
                new_config = self.load_config()
                
                # 基础验证
                if not self.validate_config(new_config):
                    print("❌ 新配置验证失败，保持当前配置")
                    return False
                
                # 应用新配置
                self.config = new_config
                return True
        except Exception as e:
            print(f"配置检查错误: {str(e)}")
        
        return False
    
    def validate_config(self, config):
        """基础配置验证（忽略账号密码变更）"""
        # 确保必须的配置项存在
        required_sections = ["General", "Account"]
        for section in required_sections:
            if not config.has_section(section):
                print(f"❌ 缺少必须的配置段: [{section}]")
                return False
        
        # 验证定时表达式
        cron_expr = config.get("General", "cron_expression", fallback="")
        try:
            croniter(cron_expr, datetime.now())
        except Exception:
            print(f"❌ 无效的定时表达式: {cron_expr}")
            return False
        
        return True

# ======================== 客户端管理 ========================
class ClientManager:
    """管理客户端连接和登录状态（忽略账号密码变更）"""
    def __init__(self, config):
        self.config = config
        self.client = None
        self.last_login_time = None
        self.login_interval = 3600 * 12  # 每12小时强制重新登录一次
        self.reconnect()  # 初始登录
    
    def reconnect(self):
        """重新连接并登录"""
        # 关闭旧连接（如果存在）
        if self.client:
            try:
                # 如果客户端有close方法则调用
                if hasattr(self.client, 'close'):
                    self.client.close()
            except Exception:
                pass
            self.client = None
        
        passport = self.config.get("Account", "passport")
        password = self.config.get("Account", "password")
        client_id = self.config.get("Account", "client_id")
        client_secret = self.config.get("Account", "client_secret")
        
        try:
            if client_id and client_secret:
                print("使用 client_id/client_secret 登录")
                self.client = P123Client(client_id=client_id, client_secret=client_secret)
            elif passport and password:
                print("使用账号密码登录")
                self.client = P123Client(passport=passport, password=password)
            else:
                print("❌ 错误: 未配置有效的登录凭证")
                return None
            
            self.last_login_time = datetime.now()
            print(f"✅ 登录成功! 登录时间: {self.last_login_time.strftime('%Y-%m-%d %H:%M:%S')}  登录域名: login.123pan.com")
            return self.client
        except Exception as e:
            print(f"❌ 客户端登录失败: {str(e)}")
            return None
    
    def get_client(self):
        """获取有效的客户端，如果当前客户端无效则重新登录"""
        # 检查是否超过强制重新登录时间
        if self.last_login_time and (datetime.now() - self.last_login_time).total_seconds() > self.login_interval:
            print("⚠️ 登录会话超时，需要重新登录")
            return self.reconnect()
        
        # 如果客户端不存在或无效，重新登录
        if not self.client or not self.is_client_valid():
            return self.reconnect()
        
        print("✔️ 使用现有登录会话")
        return self.client
    
    def is_client_valid(self):
        """检查客户端是否仍然有效"""
        # 尝试执行一个简单的API调用验证登录状态
        try:
            # 尝试获取根目录列表
            result = self.client.fs_list_v2(parent_file_id=0)
            if result.get("code") == 0:
                return True
            
            # 如果返回未授权错误
            if result.get("code") == 401 or "未授权" in result.get("message", ""):
                print("⚠️ 登录会话已过期")
                return False
        except Exception as e:
            print(f"⚠️ 登录状态检查失败: {str(e)}")
        
        # 默认认为无效
        return False
    
    def update_config(self, new_config):
        """更新配置（忽略账号密码变更）"""
        # 只更新非账号相关的配置
        self.config = new_config
        print("⚙️ 配置已更新（账号密码变更需要重启生效）")

# ======================== 工具函数 ========================
def fast_md5(file_path: Path) -> str:
    """快速计算文件MD5"""
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()

def is_large_file(file_path: Path, min_size_mb: int) -> bool:
    """检查是否是大文件（超过阈值）"""
    min_size_bytes = min_size_mb * 1024 * 1024
    return file_path.stat().st_size >= min_size_bytes

def find_file_by_name(client, parent_id: int, file_name: str):
    """
    在指定目录下查找同名文件
    返回: 文件信息 (如果存在), 否则返回None
    """
    try:
        # 获取目录列表
        list_result = client.fs_list_v2(parent_file_id=parent_id)
        
        if list_result.get("code") == 0:
            for item in list_result["data"].get("list", []):
                if item.get("FileName") == file_name and item.get("Type") == 0:  # Type=0 表示文件
                    return item
    except Exception as e:
        print(f"查找文件异常: {str(e)}")
    
    return None

def handle_duplicate_file(client, local_file: Path, parent_id: int, duplicate_handling: int):
    """
    处理同名文件冲突
    返回: True=需要上传, False=跳过上传
    """
    # 在网盘查找同名文件
    pan_file = find_file_by_name(client, parent_id, local_file.name)
    
    if not pan_file:
        return True  # 没有同名文件，需要上传
    
    # 获取文件大小
    local_size = local_file.stat().st_size
    pan_size = pan_file.get("Size", 0)
    
    print(f"⚠️ 发现同名文件: {local_file.name}")
    print(f"  本地文件大小: {local_size/1024/1024:.2f}MB")
    print(f"  网盘文件大小: {pan_size/1024/1024:.2f}MB")
    
    # 根据处理策略决定操作
    if duplicate_handling == 0:  # 跳过
        print("⏩ 跳过策略: 保留网盘文件，跳过上传")
        return False
    
    elif duplicate_handling == 1:  # 保留两者
        print("📁 保留策略: 保留两个版本的文件")
        return True
    
    elif duplicate_handling == 2:  # 替换
        print("🔄 替换策略: 删除网盘文件并上传新版本")
        # 删除网盘文件
        delete_result = client.fs_delete(pan_file["FileId"])
        if delete_result.get("code") == 0:
            print(f"✅ 已删除网盘文件: {pan_file['FileName']} (ID: {pan_file['FileId']})")
            return True
        else:
            print(f"❌ 删除文件失败: {delete_result.get('message', '未知错误')}")
            return False
    
    elif duplicate_handling == 3:  # 保留较大的文件
        print("🔍 同名策略[3]=保留较大的文件：开始大小比对")
        if local_size > pan_size:
            print(f"📊 大小比较：本地 {local_size/1024/1024:.2f}MB > 网盘 {pan_size/1024/1024:.2f}MB → 本地文件较大")
            print("🗑️ 删除原网盘较小文件...")
            delete_result = client.fs_delete(pan_file["FileId"])
            if delete_result.get("code") == 0:
                print(f"✅ 已删除原网盘文件: {pan_file['FileName']} (ID: {pan_file['FileId']})")
                print("⬆️ 将上传新（本地较大）文件以替换")
                return True
            else:
                print(f"❌ 删除原网盘较小文件失败: {delete_result.get('message', '未知错误')}，放弃上传")
                return False
        elif local_size < pan_size:
            print(f"📊 大小比较：本地 {local_size/1024/1024:.2f}MB < 网盘 {pan_size/1024/1024:.2f}MB → 网盘文件较大")
            print("✅ 保留网盘较大文件，跳过本次上传")
            return False
        else:
            print(f"📊 大小比较：两者大小相同 ({local_size/1024/1024:.2f}MB)")
            print("✅ 大小一致，保留网盘文件，跳过本次上传")
            return False
    
    return True  # 默认需要上传

def _lib_duplicate(project_strategy: int) -> int:
    """将项目同名策略映射为 p123client 库支持的 duplicate 值（库仅支持 0/1/2）。

    - 0=跳过, 1=保留两者, 2=替换 与库一致，直接透传；
    - 3=保留较大的文件 由本项目的 handle_duplicate_file 在上传前完成“删除较小/跳过”
      决策，库本身并不认识 3，这里映射为 2（替换），避免库因收到非法值而报错。
    """
    return 2 if project_strategy == 3 else project_strategy


def seconds_upload(client, file_path: Path, parent_id: int, duplicate: int):
    """
    尝试秒传文件
    返回:
        True  -> 秒传成功
        "skip"-> 按同名策略应跳过（不应继续上传）
        False -> 秒传失败（调用方可以发起真实上传）
    """
    try:
        file_name = file_path.name
        file_size = file_path.stat().st_size
        
        # 处理同名文件冲突（策略决策；返回 False 表示按策略跳过，不应继续上传）
        if duplicate in [0, 1, 2, 3]:
            should_upload = handle_duplicate_file(client, file_path, parent_id, duplicate)
            if not should_upload:
                return "skip"
        
        # 计算MD5
        print(f"计算文件MD5: {file_name} ({file_size/1024/1024:.1f}MB)")
        file_md5 = fast_md5(file_path)
        print(f"MD5计算完成: {file_md5}")
        
        # 尝试秒传（duplicate 需映射为库支持的 0/1/2）
        upload_result = client.upload_file_fast(
            file=file_path,
            file_md5=file_md5,
            file_name=file_name,
            file_size=file_size,
            parent_id=parent_id,
            duplicate=_lib_duplicate(duplicate)
        )
        
        # 检查结果
        if upload_result.get("code") == 0 and upload_result["data"].get("Reuse"):
            print(f"✅ 秒传成功! 文件ID: {upload_result['data']['Info']['FileId']}")
            return True
        
        print(f"⚠️ 秒传失败: {upload_result.get('message', '未知原因')}")
        return False
        
    except Exception as e:
        print(f"秒传异常: {str(e)}")
        return False

def find_folder_id(client, parent_id: int, folder_name: str) -> int:
    """
    在指定父目录下查找文件夹ID
    返回: 文件夹ID (如果存在), 否则返回None
    """
    try:
        # 获取目录列表
        list_result = client.fs_list_v2(parent_file_id=parent_id)
        
        if list_result.get("code") == 0:
            for item in list_result["data"].get("list", []):
                if item.get("FileName") == folder_name and item.get("Type") == 1:  # Type=1 表示目录
                    return item["FileId"]
    except Exception as e:
        print(f"查找目录异常: {str(e)}")
    
    return None

def ensure_directory_exists(client, parent_id: int, folder_name: str) -> int:
    """
    确保目录存在并返回其ID
    """
    # 尝试查找目录
    folder_id = find_folder_id(client, parent_id, folder_name)
    if folder_id:
        return folder_id
    
    # 目录不存在则创建
    create_result = client.fs_mkdir(folder_name, parent_id=parent_id)
    
    if create_result.get("code") != 0:
        print(f"❌ 目录创建失败: {create_result.get('message', '未知错误')}")
        return None
    
    # 从创建结果中获取FileId
    if create_result.get("data") and create_result["data"].get("Info") and create_result["data"]["Info"].get("FileId"):
        folder_id = create_result["data"]["Info"]["FileId"]
        print(f"✅ 目录创建成功: {folder_name} (ID: {folder_id})")
        return folder_id
    
    # 创建后再次查找确认
    time.sleep(1)  # 等待目录刷新
    folder_id = find_folder_id(client, parent_id, folder_name)
    
    if folder_id:
        print(f"✅ 目录创建成功: {folder_name} (ID: {folder_id})")
        return folder_id
    
    print(f"❌ 目录创建后仍无法找到: {folder_name}")
    return None

def ensure_dir_structure(client, pan_path: str) -> int:
    """
    确保网盘目录结构存在
    返回: 最末级目录ID
    """
    # 分割路径
    parts = pan_path.strip("/").split("/")
    if not parts:
        return 0  # 根目录
    
    # 从根目录开始
    current_id = 0
    
    # 逐级处理每个目录
    for folder in parts:
        folder_id = ensure_directory_exists(client, current_id, folder)
        if folder_id is None:
            return None
        current_id = folder_id
    
    return current_id

def remove_empty_dirs(root_dir: Path, preserve_root=True):
    """
    递归删除空目录
    root_dir: 要清理的根目录
    preserve_root: 是否保留根目录（即使为空）
    """
    # 使用os.walk自底向上遍历目录
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        current_dir = Path(dirpath)
        
        # 跳过根目录（如果配置为保留）
        if preserve_root and current_dir == root_dir:
            continue
            
        # 检查目录是否为空
        if not any(current_dir.iterdir()):
            try:
                current_dir.rmdir()
                print(f"✅ 删除空目录: {current_dir}")
            except Exception as e:
                print(f"❌ 删除目录失败: {current_dir}, 原因: {str(e)}")

def process_sync_rule(client, local_path: Path, pan_path: str, config, force_sync=False):
    """
    处理单个同步规则
    """
    # 确保网盘目录结构存在
    parent_id = ensure_dir_structure(client, pan_path)
    if parent_id is None:
        print(f"⚠️ 无法创建网盘目录结构: {pan_path}，跳过此规则")
        return
    
    # 文件计数器
    file_count = 0
    processed_count = 0
    skipped_large_files = 0
    
    # 从配置中获取参数
    seconds_upload_min_size_mb = config.getint("General", "seconds_upload_min_size")
    duplicate_handling = config.getint("General", "duplicate_handling")
    force_upload_large_file = config.getboolean("General", "force_upload_large_file", fallback=False)
    
    # 先统计文件总数
    for root, _, files in os.walk(local_path):
        file_count += len(files)
    
    print(f"规则: {local_path} → {pan_path}")
    print(f"发现 {file_count} 个文件需要处理")
    print(f"大文件阈值: >{seconds_upload_min_size_mb}MB")
    print(f"同名文件处理策略: {duplicate_handling} (0=跳过, 1=保留两者, 2=替换, 3=保留较大的文件)")
    print(f"强制同步大文件分片上传: {'启用' if force_upload_large_file else '禁用'}")
    
    # 遍历本地目录
    for root, dirs, files in os.walk(local_path):
        # 计算相对路径
        rel_path = Path(root).relative_to(local_path)
        
        # 确保网盘子目录结构存在
        current_parent_id = parent_id
        parent_id_for_files = parent_id  # 初始化变量
        
        # 如果不是根目录，则处理子目录结构
        if rel_path != Path("."):
            # 处理相对路径中的每个目录
            for folder in rel_path.parts:
                folder_id = ensure_directory_exists(client, current_parent_id, folder)
                if folder_id is None:
                    print(f"⚠️ 无法创建子目录: {folder}，跳过此目录")
                    break
                current_parent_id = folder_id
            else:
                # 所有目录都创建成功
                parent_id_for_files = current_parent_id
        
        # 处理当前目录下的文件
        for file in files:
            processed_count += 1
            local_file = Path(root) / file
            file_size = local_file.stat().st_size
            file_size_mb = file_size / (1024 * 1024)
            
            print(f"\n[{processed_count}/{file_count}] 处理文件: {file} ({file_size_mb:.1f}MB)")
            
            # 检查是否为大文件
            # 大文件（超过 seconds_upload_min_size 阈值）默认只尝试秒传，秒传失败一律跳过。
            # 若启用 force_upload_large_file 且当前为强制同步模式，则秒传失败后转为分片上传。
            if is_large_file(local_file, seconds_upload_min_size_mb):
                print(f"⚠️ 大文件处理策略: 仅尝试秒传 (>{seconds_upload_min_size_mb}MB)")
                res = seconds_upload(client, local_file, parent_id_for_files, duplicate_handling)
                if res is True:
                    # 秒传成功，删除本地文件
                    local_file.unlink()
                    print(f"已删除本地文件: {local_file}")
                elif res == "skip":
                    # 按同名策略跳过
                    skipped_large_files += 1
                    print("⏳ 按同名策略跳过，不执行上传")
                elif force_sync and force_upload_large_file:
                    # 秒传失败，但启用了强制同步大文件分片上传
                    print(f"⏫ 强制同步模式: 秒传失败，转为分片上传 ({file_size_mb:.1f}MB)")
                    try:
                        upload_result = client.upload_file(
                            file=local_file,
                            parent_id=parent_id_for_files,
                            duplicate=_lib_duplicate(duplicate_handling)
                        )
                        if upload_result.get("code") == 0:
                            data = upload_result.get("data", {}) or {}
                            file_info = data.get("file_info", {}) if isinstance(data, dict) else {}
                            file_id = file_info.get("FileId") or file_info.get("fileId") if isinstance(file_info, dict) else None
                            if file_id:
                                print(f"✅ 上传成功: {local_file.name} (FileId: {file_id})")
                                local_file.unlink()
                                print(f"已删除本地文件: {local_file}")
                            else:
                                print(f"⚠️ 上传成功但未找到文件ID: {local_file.name}")
                        else:
                            print(f"❌ 上传失败: {upload_result.get('message', '未知错误')} ({local_file.name})")
                    except Exception as e:
                        print(f"🔥 大文件分片上传异常: {str(e)}")
                else:
                    # 秒传失败，跳过并等待下次同步
                    skipped_large_files += 1
                    print("⏳ 秒传失败，跳过此文件等待下次同步")
                continue
            
            # 普通文件处理
            print(f"普通文件处理策略: 先尝试秒传，失败则分片上传 ({file_size_mb:.1f}MB)")
            try:
                # 尝试秒传
                res = seconds_upload(client, local_file, parent_id_for_files, duplicate_handling)
                if res is True:
                    # 秒传成功，删除本地文件
                    local_file.unlink()
                    print(f"已删除本地文件: {local_file}")
                    continue
                if res == "skip":
                    # 已按同名策略跳过（handle_duplicate_file 内部已打印原因），不再上传
                    continue

                # 秒传失败，使用分片上传（duplicate 需映射为库支持的 0/1/2）
                print(f"⏫ 开始上传: {local_file.name} ({file_size_mb:.1f}MB)")
                upload_result = client.upload_file(
                    file=local_file,
                    parent_id=parent_id_for_files,
                    duplicate=_lib_duplicate(duplicate_handling)
                )

                if upload_result.get("code") == 0:
                    data = upload_result.get("data", {}) or {}
                    file_info = data.get("file_info", {}) if isinstance(data, dict) else {}
                    file_id = file_info.get("FileId") or file_info.get("fileId") if isinstance(file_info, dict) else None
                    if file_id:
                        print(f"✅ 上传成功: {local_file.name} (FileId: {file_id})")
                        # 上传成功后删除本地文件
                        local_file.unlink()
                        print(f"已删除本地文件: {local_file}")
                    else:
                        print(f"⚠️ 上传成功但未找到文件ID: {local_file.name}")
                else:
                    print(f"❌ 上传失败: {upload_result.get('message', '未知错误')} ({local_file.name})")
            except Exception as e:
                print(f"🔥 文件处理异常: {str(e)}")
            
            # 文件间延迟
            time.sleep(1)
    
    # 同步完成后清理空目录
    print("检查并清理空目录...")
    remove_empty_dirs(local_path, preserve_root=True)
    
    # 规则统计
    print(f"\n规则完成: {local_path} → {pan_path}")
    print(f"共处理 {processed_count} 个文件")
    if skipped_large_files > 0:
        print(f"⚠️ 跳过 {skipped_large_files} 个大文件（等待下次秒传）")
    print("-" * 50)

def perform_sync(config, client_manager, force_sync=False):
    """执行同步任务"""
    global is_force_sync_running
    
    # 设置强制同步状态
    if force_sync:
        is_force_sync_running = True
    
    try:
        print("\n" + "="*50)
        if force_sync:
            print(f"开始强制同步任务: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print(f"开始同步任务: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*50)
    
        # 获取有效的客户端
        client = client_manager.get_client()
        if not client:
            print("❌ 无法获取有效的客户端，同步任务中止")
            return
        
        # 获取同步规则
        sync_rules = {}
        if "SyncRules" in config:
            for key in config["SyncRules"]:
                value = config["SyncRules"][key]
                if "," in value:
                    local_part, pan_part = value.split(",", 1)
                    sync_rules[key] = {
                        "local_path": Path(local_part.strip()),
                        "pan_path": pan_part.strip()
                    }
        
        if not sync_rules:
            print("⚠️ 未配置任何同步规则")
            return
        
        print(f"发现 {len(sync_rules)} 个同步规则")
        
        # 处理每个同步规则
        for rule_name, rule in sync_rules.items():
            local_path = rule["local_path"]
            pan_path = rule["pan_path"]
            
            # 确保本地路径存在
            if not local_path.exists():
                print(f"⚠️ 本地路径不存在: {local_path}，跳过此规则")
                continue
            
            print(f"\n{'='*50}")
            print(f"处理规则: {rule_name}")
            print(f"本地路径: {local_path}")
            print(f"网盘路径: {pan_path}")
            print(f"{'='*50}")
            
            process_sync_rule(client, local_path, pan_path, config, force_sync)
        
        print("\n所有同步规则处理完成")
        print(f"同步任务结束: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*50 + "\n")
    except Exception as e:
        print(f"同步任务异常: {str(e)}")
    finally:
        # 重置强制同步状态
        if force_sync:
            is_force_sync_running = False

def schedule_sync(config, start_immediately=True):
    """定时执行同步任务"""
    # 初始化配置管理器
    config_manager = ConfigManager(CONF_FILE)
    
    # 初始化客户端管理器
    client_manager = ClientManager(config_manager.config)
    
    # 创建初始Cron迭代器
    cron_expr = config_manager.config.get("General", "cron_expression", fallback="0 * * * *")
    cron = croniter(cron_expr, datetime.now())
    
    print(f"定时同步已启用，Cron表达式: '{cron_expr}'")
    print("程序将在后台运行，按 Ctrl+C 退出")
    print("⚠️ 注意: 账号密码变更需要手动重启程序才能生效")

    # ======================== 启动时立即执行一次同步（可选） ========================
    if start_immediately:
        print("\n" + "="*50)
        print("执行启动同步任务...")
        print("="*50)
        try:
            perform_sync(config_manager.config, client_manager)
            print("✅ 启动同步任务完成")
        except Exception as e:
            print(f"⚠️ 启动同步任务失败: {str(e)}")
    # ======================== 启动时同步结束 ========================

    while True:
        try:
            # 检查配置文件更新
            if config_manager.check_and_reload():
                # 更新客户端管理器中的配置（忽略账号密码变更）
                client_manager.update_config(config_manager.config)
                
                # 如果定时规则变更，重新创建Cron迭代器
                new_cron_expr = config_manager.config.get("General", "cron_expression", fallback="0 * * * *")
                if new_cron_expr != cron_expr:
                    print(f"⏱️ 定时规则变更: {cron_expr} → {new_cron_expr}")
                    cron_expr = new_cron_expr
                    cron = croniter(cron_expr, datetime.now())
            
            # 计算下一次执行时间
            next_time = cron.get_next(datetime)
            wait_seconds = (next_time - datetime.now()).total_seconds()
            
            print(f"下一次同步时间: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"等待 {wait_seconds:.0f} 秒...")
            
            # 等待直到下一次执行时间
            time.sleep(wait_seconds)
            
            # 检查是否正在执行强制同步，如果是则跳过此次定时同步
            if is_force_sync_running:
                print("⚠️ 检测到强制同步正在运行，跳过此次定时同步")
                continue
            
            # 执行同步任务（使用最新配置）
            perform_sync(config_manager.config, client_manager)
            
        except KeyboardInterrupt:
            print("\n定时同步已取消")
            break
        except Exception as e:
            print(f"定时同步异常: {str(e)}")
            time.sleep(60)

def force_sync():
    """执行强制同步"""
    global is_force_sync_running
    
    if is_force_sync_running:
        print("⚠️ 强制同步已在运行中，请勿重复调用")
        return False
    
    # 加载配置文件
    config = load_or_create_config()
    if config is None:
        return False
    
    # 创建客户端管理器
    client_manager = ClientManager(config)
    
    # 执行强制同步
    perform_sync(config, client_manager, force_sync=True)
    return True

def get_local_ip() -> str:
    """获取本机局域网 IPv4 地址，用于展示对外访问地址。"""
    try:
        # 通过 UDP 探测出口网卡 IP（无需真正发包）
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def main():
    """主函数"""
    # 加载配置文件
    config = load_or_create_config()
    if config is None:  # 这里添加了冒号
        return
    
    # 检查是否启用定时同步
    cron_expr = config.get("General", "cron_expression", fallback="")
    
    # 创建客户端管理器
    client_manager = ClientManager(config)
    
    if cron_expr and cron_expr.strip():
        # 启动定时同步
        schedule_sync(config)
    else:
        # 执行单次同步
        print("\n" + "="*50)
        print("执行单次同步任务...")
        print("="*50)
        perform_sync(config, client_manager)

if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='123网盘同步工具')
    parser.add_argument('--web', '--ui', action='store_true', help='启动Web配置界面')
    parser.add_argument('--host', default='0.0.0.0', help='Web服务监听地址（默认：0.0.0.0）')
    parser.add_argument('--port', type=int, default=5000, help='Web服务监听端口（默认：5000）')
    args = parser.parse_args()
    
    if args.web:
        # 启动Web配置界面
        # 对外访问地址：自动探测本机局域网 IP + 监听端口（无需在 settings.ini 配置）
        _access_url = f"http://{get_local_ip()}:{args.port}"

        print("=" * 50)
        print("启动 123 网盘同步工具 - Web 配置界面")
        print(f"监听地址: {args.host}:{args.port}  （容器/本机内部绑定；0.0.0.0 = 监听所有网卡）")
        print(f"访问地址: {_access_url}  （在浏览器打开此地址；若以 Docker 部署，请使用 宿主机IP + 端口映射，例如 http://宿主机IP:12333）")
        print("按 Ctrl+C 退出")
        print("=" * 50)

        # 导入 Flask 应用
        from app import app

        # 屏蔽 Flask 自带的启动横幅（* Serving Flask app / * Debug mode），
        # 避免无释义的噪音；上面已用可读提示替代。
        import flask.cli as _flask_cli
        _flask_cli.show_server_banner = lambda *a, **k: None

        # 启动 Flask 应用
        try:
            app.run(host=args.host, port=args.port, debug=False)
        except KeyboardInterrupt:
            print("\nWeb服务已终止")
        except Exception as e:
            print(f"Web服务异常: {e}")
    else:
        # 执行原有同步功能
        try:
            main()
        except KeyboardInterrupt:
            print("\n程序已终止")
        except Exception as e:
            print(f"程序异常: {e}")