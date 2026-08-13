from flask import Flask, render_template, request, jsonify
import configparser
import os
from pathlib import Path
import logging
import threading

# 导入123sync模块的强制同步功能（使用importlib动态导入，因为模块名以数字开头）
import importlib

# 动态导入模块
module_123sync = importlib.import_module('123sync')

# 获取模块中的变量和函数
is_force_sync_running = module_123sync.is_force_sync_running
force_sync = module_123sync.force_sync
schedule_sync = module_123sync.schedule_sync
load_or_create_config = module_123sync.load_or_create_config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# 屏蔽 httpx / httpcore 的 HTTP 请求 INFO 日志（避免每个请求刷一行）
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
# 屏蔽 werkzeug 的常规请求 INFO 日志（Web 轮询等成功请求不刷屏，仅异常保留）
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# 配置文件路径：基于本脚本所在目录，避免在不同工作目录下找不到 settings.ini
CONF_DIR = Path(__file__).resolve().parent / "conf"
CONF_FILE = CONF_DIR / "settings.ini"

# 默认配置
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

# 创建Flask应用
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# 加载或创建配置文件
def load_or_create_config():
    """加载或创建配置文件"""
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    
    if not CONF_FILE.exists():
        logger.info(f"配置文件不存在: {CONF_FILE}，正在创建默认配置")
        config = configparser.ConfigParser()
        for section, options in DEFAULT_CONFIG.items():
            config[section] = options
        
        with open(CONF_FILE, "w", encoding="utf-8") as f:
            config.write(f)
        
        return config
    
    config = configparser.ConfigParser()
    config.read(CONF_FILE, encoding="utf-8")
    return config

# 保存配置文件
def save_config(config):
    """保存配置文件"""
    try:
        with open(CONF_FILE, "w", encoding="utf-8") as f:
            config.write(f)
        return True
    except Exception as e:
        logger.error(f"保存配置文件失败: {str(e)}")
        return False

# 首页路由
@app.route('/')
def index():
    """首页"""
    config = load_or_create_config()
    
    # 转换配置为字典格式，方便前端处理
    config_dict = {
        'General': dict(config['General']),
        'Account': dict(config['Account']),
        'SyncRules': dict(config['SyncRules'])
    }
    
    return render_template('index.html', config=config_dict)

# 获取配置API
@app.route('/api/config', methods=['GET'])
def get_config():
    """获取配置"""
    config = load_or_create_config()
    
    # 转换配置为字典格式
    config_dict = {
        'General': dict(config['General']),
        'Account': dict(config['Account']),
        'SyncRules': dict(config['SyncRules'])
    }
    
    return jsonify({'success': True, 'config': config_dict})

# 更新配置API
@app.route('/api/config', methods=['POST'])
def update_config():
    """更新配置"""
    try:
        data = request.get_json()
        if not data or 'config' not in data:
            return jsonify({'success': False, 'message': '无效的请求数据'})
        
        new_config_dict = data['config']
        
        # 创建配置对象
        config = configparser.ConfigParser()
        
        # 加载现有配置
        config = load_or_create_config()
        
        # 更新General配置
        if 'General' in new_config_dict:
            config['General'] = new_config_dict['General']
        
        # 更新Account配置
        if 'Account' in new_config_dict:
            config['Account'] = new_config_dict['Account']
        
        # 更新SyncRules配置
        if 'SyncRules' in new_config_dict:
            config['SyncRules'] = new_config_dict['SyncRules']
        
        # 保存配置
        if save_config(config):
            return jsonify({'success': True, 'message': '配置更新成功'})
        else:
            return jsonify({'success': False, 'message': '配置保存失败'})
            
    except Exception as e:
        logger.error(f"更新配置失败: {str(e)}")
        return jsonify({'success': False, 'message': f'更新配置失败: {str(e)}'})

# 独立保存配置部分API
@app.route('/api/config/<section>', methods=['POST'])
def update_config_section(section):
    """更新配置的特定部分"""
    try:
        data = request.get_json()
        if not data or 'config' not in data:
            return jsonify({'success': False, 'message': '无效的请求数据'})
        
        # 验证section是否合法
        valid_sections = ['General', 'Account', 'SyncRules']
        if section not in valid_sections:
            return jsonify({'success': False, 'message': '无效的配置部分'})
        
        # 加载现有配置
        config = load_or_create_config()
        
        # 更新特定部分的配置
        config[section] = data['config']
        
        # 保存配置
        if save_config(config):
            # 根据配置类型返回不同的提示
            if section in ['General', 'SyncRules']:
                return jsonify({'success': True, 'message': '配置更新成功，将在下次同步时生效'})
            else: # Account
                return jsonify({'success': True, 'message': '账号配置更新成功，需要重启服务才能生效'})
        else:
            return jsonify({'success': False, 'message': '配置保存失败'})
            
    except Exception as e:
        logger.error(f"更新配置部分失败: {str(e)}")
        return jsonify({'success': False, 'message': f'更新配置部分失败: {str(e)}'})

# 添加同步规则API
@app.route('/api/rules', methods=['POST'])
def add_rule():
    """添加同步规则"""
    try:
        data = request.get_json()
        if not data or 'rule' not in data:
            return jsonify({'success': False, 'message': '无效的请求数据'})
        
        rule = data['rule']
        
        # 加载现有配置
        config = load_or_create_config()
        
        # 确保SyncRules段存在
        if 'SyncRules' not in config:
            config['SyncRules'] = {}
        
        # 生成新的规则键名
        rule_count = len(config['SyncRules'])
        new_rule_key = f'rule{rule_count + 1}'
        
        # 添加新规则
        config['SyncRules'][new_rule_key] = rule
        
        # 保存配置
        if save_config(config):
            return jsonify({'success': True, 'message': '规则添加成功', 'rule_key': new_rule_key})
        else:
            return jsonify({'success': False, 'message': '规则保存失败'})
            
    except Exception as e:
        logger.error(f"添加规则失败: {str(e)}")
        return jsonify({'success': False, 'message': f'添加规则失败: {str(e)}'})

# 删除同步规则API
@app.route('/api/rules/<rule_key>', methods=['DELETE'])
def delete_rule(rule_key):
    """删除同步规则"""
    try:
        # 加载现有配置
        config = load_or_create_config()
        
        # 检查SyncRules段和规则是否存在
        if 'SyncRules' not in config or rule_key not in config['SyncRules']:
            return jsonify({'success': False, 'message': '规则不存在'})
        
        # 删除规则
        del config['SyncRules'][rule_key]
        
        # 重新排序规则键名
        new_sync_rules = {}
        for i, (key, value) in enumerate(config['SyncRules'].items(), 1):
            new_sync_rules[f'rule{i}'] = value
        
        # 更新配置
        config['SyncRules'] = new_sync_rules
        
        # 保存配置
        if save_config(config):
            return jsonify({'success': True, 'message': '规则删除成功'})
        else:
            return jsonify({'success': False, 'message': '规则保存失败'})
            
    except Exception as e:
        logger.error(f"删除规则失败: {str(e)}")
        return jsonify({'success': False, 'message': f'删除规则失败: {str(e)}'})

# 获取同步状态API
@app.route('/api/sync/status', methods=['GET'])
def get_sync_status():
    """获取同步状态"""
    try:
        return jsonify({
            'success': True,
            'is_force_sync_running': module_123sync.is_force_sync_running
        })
    except Exception as e:
        logger.error(f"获取同步状态失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取同步状态失败: {str(e)}'})

# 触发强制同步API
@app.route('/api/sync/force', methods=['POST'])
def trigger_force_sync():
    """触发强制同步"""
    try:
        # 检查是否已经在运行强制同步
        if module_123sync.is_force_sync_running:
            return jsonify({'success': False, 'message': '强制同步已在运行中'})
        
        # 在新线程中执行强制同步，避免阻塞Flask应用
        def run_force_sync():
            module_123sync.force_sync()
        
        sync_thread = threading.Thread(target=run_force_sync)
        sync_thread.daemon = True
        sync_thread.start()
        
        return jsonify({'success': True, 'message': '强制同步已启动'})
    except Exception as e:
        logger.error(f"触发强制同步失败: {str(e)}")
        return jsonify({'success': False, 'message': f'触发强制同步失败: {str(e)}'})

# ======================== 定时同步调度器自愈启动 ========================
# 必须在模块加载时启动，而非仅在 __main__ 中启动。
# 若通过 `flask run` / gunicorn / 其他 WSGI 方式启动，`if __name__ == '__main__'`
# 不会执行，调度器将永不启动、cron 永不触发。模块级启动可覆盖所有启动方式。
def _start_scheduler_once():
    try:
        _cfg = load_or_create_config()
        _cron = _cfg.get("General", "cron_expression", fallback="") if _cfg is not None else ""
        if _cron and _cron.strip():
            # start_immediately=False：Web 启动时不立即全量同步，只等 cron 到点触发
            _sched_thread = threading.Thread(
                target=schedule_sync, args=(_cfg, False), daemon=True
            )
            _sched_thread.start()
            print(f"⏱️ 已启动定时同步调度器（后台线程），Cron: '{_cron.strip()}'")
        else:
            print("⚠️ 未配置 cron_expression，不启动定时同步")
    except Exception as e:
        print(f"⚠️ 启动定时同步调度器失败: {str(e)}")

# 防止 Flask 重载器或重复导入导致启动多个调度线程（进程内仅启动一次）
if not os.environ.get("_ONETWO_SCHEDULER_STARTED"):
    os.environ["_ONETWO_SCHEDULER_STARTED"] = "1"
    _start_scheduler_once()

# 运行应用
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)