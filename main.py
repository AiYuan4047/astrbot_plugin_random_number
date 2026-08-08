import os
import random
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import AstrBotConfig
from astrbot.api.web import error_response, json_response, request
from astrbot.api import logger


# ========== 插件常量 ==========
PLUGIN_NAME = "astrbot_plugin_random_number"
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
# 数据存储于 AstrBot data/plugin_data/ 目录，防止插件更新时数据丢失
DATA_DIR = os.path.join(os.path.dirname(PLUGIN_DIR), "data", "plugin_data", PLUGIN_NAME)

# 表示"不限制"的特殊字符
SKIP_CHARS = {'-', '_', '/', '#', '*'}

# 板块名称映射
MODULE_NAMES = {
    "random_number": "随机数",
    "coin_flip": "抛硬币",
    "member_lottery": "成员抽奖",
}


# ========== 本地 SQLite 数据库管理 ==========
class DatabaseManager:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "random_number.db")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
        logger.info(f"[随机数] 数据库初始化完成: {self.db_path}")

    def _init_tables(self):
        """初始化数据库表"""
        c = self.conn.cursor()
        
        # 创建表（如果不存在）
        c.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                user_name TEXT DEFAULT '',
                module TEXT,
                request TEXT DEFAULT '',
                result TEXT DEFAULT '',
                source_group TEXT DEFAULT '',
                platform TEXT DEFAULT '',
                created_at TEXT
            )
        """)
        self.conn.commit()
        
        # 检查并添加 platform 列（兼容旧版本）
        c.execute("PRAGMA table_info(records)")
        columns = [row["name"] for row in c.fetchall()]
        
        if "platform" not in columns:
            logger.info("[随机数] 检测到旧版数据库，正在添加 platform 列...")
            c.execute("ALTER TABLE records ADD COLUMN platform TEXT DEFAULT ''")
            self.conn.commit()
            logger.info("[随机数] platform 列添加成功")
        
        # 创建索引
        c.execute("CREATE INDEX IF NOT EXISTS idx_records_module ON records(module)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_records_user ON records(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_records_date ON records(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_records_platform ON records(platform)")
        self.conn.commit()
        
        # 验证表结构
        c.execute("PRAGMA table_info(records)")
        final_columns = [row["name"] for row in c.fetchall()]
        logger.info(f"[随机数] 数据库表结构: {final_columns}")

    def add_record(self, user_id: str, user_name: str, module: str,
                   request: str, result: str, source_group: str, platform: str = ""):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO records (user_id, user_name, module, request, result, source_group, platform, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, user_name, module,
             request[:500] if request else "",
             result[:1000] if result else "",
             source_group, platform, now),
        )
        self.conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        c = self.conn.cursor()
        stats = {}
        for module, name in MODULE_NAMES.items():
            c.execute("SELECT COUNT(*) as cnt FROM records WHERE module = ?", (module,))
            stats[module] = c.fetchone()["cnt"]
        c.execute("SELECT COUNT(*) as cnt FROM records")
        stats["total"] = c.fetchone()["cnt"]
        return stats

    def get_platform_stats(self, platforms: List[str]) -> Dict[str, Any]:
        """获取各平台的统计数据"""
        c = self.conn.cursor()
        result = {}

        # 平台映射（QQ包含napcat和qq_official）
        platform_mapping = {
            "qq": ["napcat", "qq_official"],
            "telegram": ["telegram"],
            "feishu": ["feishu"]
        }

        for platform_key in platforms:
            platform_list = platform_mapping.get(platform_key, [platform_key])
            placeholders = ",".join(["?" for _ in platform_list])

            # 总次数
            c.execute(f"SELECT COUNT(*) as cnt FROM records WHERE platform IN ({placeholders})", platform_list)
            total = c.fetchone()["cnt"]

            # 各模块次数
            module_stats = {}
            for module in MODULE_NAMES.keys():
                c.execute(f"SELECT COUNT(*) as cnt FROM records WHERE platform IN ({placeholders}) AND module = ?",
                         platform_list + [module])
                module_stats[module] = c.fetchone()["cnt"]

            result[platform_key] = {
                "total": total,
                "modules": module_stats
            }

        return result

    def get_records(self, limit: int = 100, offset: int = 0,
                    module: Optional[str] = None, platform: Optional[str] = None) -> List[sqlite3.Row]:
        c = self.conn.cursor()

        # 平台映射（QQ包含napcat和qq_official）
        platform_mapping = {
            "qq": ["napcat", "qq_official"],
            "telegram": ["telegram"],
            "feishu": ["feishu"]
        }

        conditions = []
        params = []

        if module:
            conditions.append("module = ?")
            params.append(module)

        if platform:
            platform_list = platform_mapping.get(platform, [platform])
            placeholders = ",".join(["?" for _ in platform_list])
            conditions.append(f"platform IN ({placeholders})")
            params.extend(platform_list)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"SELECT * FROM records WHERE {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        c.execute(query, params)
        return c.fetchall()

    def get_record(self, record_id: int) -> Optional[sqlite3.Row]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM records WHERE id = ?", (record_id,))
        return c.fetchone()

    def delete_record(self, record_id: int) -> bool:
        c = self.conn.cursor()
        c.execute("DELETE FROM records WHERE id = ?", (record_id,))
        success = c.rowcount > 0
        self.conn.commit()
        return success

    def clear_all(self) -> int:
        c = self.conn.cursor()
        c.execute("DELETE FROM records")
        deleted = c.rowcount
        self.conn.commit()
        return deleted

    def cleanup_old_records(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")
        c = self.conn.cursor()
        c.execute("DELETE FROM records WHERE created_at < ?", (cutoff,))
        deleted = c.rowcount
        self.conn.commit()
        return deleted

    def close(self):
        self.conn.close()


# ========== 插件主类 ==========
@register(PLUGIN_NAME, "user", "随机数生成插件 - 支持自定义范围、批量生成、抛硬币和群成员抽奖，带WebUI管理面板", "2.0.0", "https://github.com/user/astrbot_plugin_random_number")
class RandomNumberPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 使用绝对路径，确保数据库位置一致
        self.db = DatabaseManager(DATA_DIR)

        # 启动时清理旧记录
        retention = config.get("history_retention_days", 30)
        if retention > 0 and config.get("store_history", True):
            deleted = self.db.cleanup_old_records(retention)
            if deleted > 0:
                logger.info(f"[随机数] 清理过期历史记录: {deleted} 条")

        # 注册 WebUI 后端 API
        self._register_web_apis()

    def _register_web_apis(self):
        """注册 WebUI 面板后端 API"""
        routes = [
            (f"/{PLUGIN_NAME}/stats", self.api_get_stats, ["GET"], "获取各板块使用统计"),
            (f"/{PLUGIN_NAME}/records", self.api_get_records, ["GET"], "获取使用记录列表"),
            (f"/{PLUGIN_NAME}/records/detail", self.api_get_record_detail, ["GET"], "获取单条记录详情"),
            (f"/{PLUGIN_NAME}/records/delete", self.api_delete_record, ["POST"], "删除使用记录"),
            (f"/{PLUGIN_NAME}/records/clear", self.api_clear_records, ["POST"], "清空所有记录"),
        ]
        for path, handler, methods, desc in routes:
            try:
                self.context.register_web_api(path, handler, methods, desc)
            except Exception as e:
                logger.error(f"[随机数] 注册API失败 {path}: {e}")

    # ========== WebUI API 处理 ==========

    async def api_get_stats(self):
        try:
            stats = self.db.get_stats()
            return json_response(stats)
        except Exception as e:
            logger.error(f"[随机数] 获取统计失败: {e}")
            return error_response(f"获取统计失败: {e}")

    async def api_get_records(self):
        try:
            module = request.query.get("module", "")
            limit = int(request.query.get("limit", "100"))
            offset = int(request.query.get("offset", "0"))
            rows = self.db.get_records(limit=limit, offset=offset,
                                       module=module if module else None)
            records = []
            for row in rows:
                platform = row["platform"] if row["platform"] else "napcat"
                # 根据平台设置标签
                if platform in ["napcat", "qqbot"]:
                    platform_label = "QQ"
                elif platform == "telegram":
                    platform_label = "Telegram"
                elif platform == "feishu":
                    platform_label = "飞书"
                else:
                    platform_label = "未知"
                
                records.append({
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "user_name": row["user_name"] or row["user_id"],
                    "module": row["module"],
                    "module_name": MODULE_NAMES.get(row["module"], row["module"]),
                    "request": row["request"],
                    "result": row["result"],
                    "source_group": row["source_group"] if row["source_group"] else "私聊",
                    "platform": platform,
                    "platform_label": platform_label,
                    "created_at": row["created_at"],
                })
            return json_response(records)
        except Exception as e:
            logger.error(f"[随机数] 获取记录列表失败: {e}")
            return error_response(f"获取记录列表失败: {e}")

    async def api_get_record_detail(self):
        try:
            record_id = int(request.query.get("id", "0"))
            if not record_id:
                return error_response("缺少 id 参数")
            row = self.db.get_record(record_id)
            if not row:
                return error_response("记录不存在")
            
            platform = row["platform"] if row["platform"] else "napcat"
            # 根据平台设置标签
            if platform in ["napcat", "qqbot"]:
                platform_label = "QQ"
            elif platform == "telegram":
                platform_label = "Telegram"
            elif platform == "feishu":
                platform_label = "飞书"
            else:
                platform_label = "未知"
            
            record = {
                "id": row["id"],
                "user_id": row["user_id"],
                "user_name": row["user_name"] or row["user_id"],
                "module": row["module"],
                "module_name": MODULE_NAMES.get(row["module"], row["module"]),
                "request": row["request"],
                "result": row["result"],
                "source_group": row["source_group"] if row["source_group"] else "私聊",
                "platform": platform,
                "platform_label": platform_label,
                "created_at": row["created_at"],
            }
            return json_response(record)
        except Exception as e:
            logger.error(f"[随机数] 获取记录详情失败: {e}")
            return error_response(f"获取记录详情失败: {e}")

    async def api_delete_record(self):
        try:
            data = await request.get_json()
            record_id = data.get("record_id")
            if record_id is None:
                return error_response("缺少 record_id")
            success = self.db.delete_record(int(record_id))
            if success:
                return json_response({"message": "记录已删除"})
            return error_response("记录不存在")
        except Exception as e:
            logger.error(f"[随机数] 删除记录失败: {e}")
            return error_response(f"删除记录失败: {e}")

    async def api_clear_records(self):
        try:
            deleted = self.db.clear_all()
            return json_response({"message": f"已清空 {deleted} 条记录"})
        except Exception as e:
            logger.error(f"[随机数] 清空记录失败: {e}")
            return error_response(f"清空记录失败: {e}")

    # ========== 辅助方法 ==========

    def _parse_int_or_default(self, val, default):
        """解析整数，如果是特殊字符则返回默认值"""
        if val is None:
            return default
        if val in SKIP_CHARS:
            return default
        return int(val)

    def _get_platform_name(self, event: AstrMessageEvent) -> str:
        """获取平台名称"""
        try:
            # 从 unified_msg_origin 获取
            umo = getattr(event, "unified_msg_origin", None)
            if umo:
                platform = str(umo).split(":")[0].lower()
                # 标准化平台名称
                if platform in ["napcat", "onebot", "go-cqhttp"]:
                    return "napcat"
                elif platform in ["qqbot", "qq_official", "qq_official_bot"]:
                    return "qqbot"
                elif platform in ["telegram", "tg"]:
                    return "telegram"
                elif platform in ["feishu", "lark"]:
                    return "feishu"
                elif platform in ["gewechat", "wechat_lobster"]:
                    return "gewechat"
                elif platform in ["wechat_personal", "wechat_personal_bot"]:
                    return "wechat_personal"
                elif platform in ["wecom", "wechat_work"]:
                    return "wecom"
                # 如果无法识别，默认返回 napcat（QQ平台）
                return "napcat"
        except Exception as e:
            logger.error(f"[随机数] 获取平台名称失败: {e}")
        # 默认返回 napcat（QQ平台）
        return "napcat"

    def _get_source_group(self, event: AstrMessageEvent) -> str:
        """获取消息来源群信息，支持多平台"""
        try:
            platform = self._get_platform_name(event)
            msg_obj = getattr(event, "message_obj", None)

            # NapCat (OneBot)
            if platform == "napcat":
                if msg_obj:
                    if hasattr(msg_obj, "group_id") and msg_obj.group_id:
                        return f"群:{msg_obj.group_id}"
                    if hasattr(msg_obj, "type"):
                        msg_type = str(msg_obj.type).lower()
                        if "group" in msg_type:
                            return f"群:{msg_obj.session_id}"
                        elif "friend" in msg_type or "private" in msg_type:
                            return "私聊"

            # QQ开放平台Bot
            elif platform == "qqbot":
                if msg_obj:
                    # QQ官方Bot的群信息
                    if hasattr(msg_obj, "group_id") and msg_obj.group_id:
                        return f"群:{msg_obj.group_id}"
                    if hasattr(msg_obj, "guild_id") and msg_obj.guild_id:
                        return f"频道:{msg_obj.guild_id}"
                    if hasattr(msg_obj, "channel_id") and msg_obj.channel_id:
                        return f"子频道:{msg_obj.channel_id}"

            # Telegram (纸飞机)
            elif platform == "telegram":
                if msg_obj:
                    if hasattr(msg_obj, "chat") and msg_obj.chat:
                        chat = msg_obj.chat
                        chat_type = getattr(chat, "type", "")
                        chat_id = getattr(chat, "id", "")
                        chat_title = getattr(chat, "title", "")
                        if chat_type in ["group", "supergroup"]:
                            return f"群:{chat_title or chat_id}"
                        elif chat_type == "private":
                            return "私聊"

            # 飞书
            elif platform == "feishu":
                if msg_obj:
                    # 飞书的群聊信息
                    if hasattr(msg_obj, "chat_id") and msg_obj.chat_id:
                        chat_name = getattr(msg_obj, "chat_name", "") or msg_obj.chat_id
                        return f"群:{chat_name}"
                    if hasattr(msg_obj, "group_id") and msg_obj.group_id:
                        return f"群:{msg_obj.group_id}"

            # 通用回退
            if msg_obj:
                if hasattr(msg_obj, "group_id") and msg_obj.group_id:
                    return f"群:{msg_obj.group_id}"
                if hasattr(msg_obj, "type"):
                    msg_type = str(msg_obj.type).lower()
                    if "group" in msg_type:
                        return f"群:{msg_obj.session_id}"
                    elif "friend" in msg_type or "private" in msg_type:
                        return "私聊"

            return "未知"
        except Exception as e:
            logger.error(f"[随机数] 获取来源群失败: {e}")
            return "未知"

    def _get_sender_info(self, event: AstrMessageEvent) -> tuple:
        """获取发送者ID和昵称"""
        try:
            user_id = str(event.get_sender_id())
        except Exception:
            user_id = "未知"
        user_name = ""
        try:
            msg_obj = event.message_obj
            if msg_obj and hasattr(msg_obj, "sender") and msg_obj.sender:
                sender = msg_obj.sender
                user_name = getattr(sender, "nickname", "") or getattr(sender, "name", "") or ""
        except Exception:
            pass
        return user_id, user_name

    def _is_qq_platform(self, event: AstrMessageEvent) -> bool:
        """判断是否为QQ平台（napcat 或 qqbot），只有QQ平台才存储记录"""
        platform = self._get_platform_name(event)
        return platform in ("napcat", "qqbot")

    def _record_usage(self, event: AstrMessageEvent, module: str,
                      request_text: str, result_text: str):
        """记录使用情况到数据库（仅QQ平台）"""
        if not self.config.get("store_history", True):
            return
        # 只存储QQ平台的数据
        if not self._is_qq_platform(event):
            return
        try:
            user_id, user_name = self._get_sender_info(event)
            source_group = self._get_source_group(event)
            platform = self._get_platform_name(event)
            self.db.add_record(user_id, user_name, module, request_text, result_text, source_group, platform)
        except Exception as e:
            logger.error(f"[随机数] 记录使用情况失败: {e}")

    def _extract_group_id(self, event: AstrMessageEvent) -> Optional[str]:
        """从事件中提取群ID，支持多平台"""
        try:
            platform = self._get_platform_name(event)
            msg_obj = getattr(event, "message_obj", None)

            # NapCat (OneBot)
            if platform == "napcat":
                if msg_obj:
                    if hasattr(msg_obj, "group_id") and msg_obj.group_id:
                        return str(msg_obj.group_id)

            # QQ开放平台Bot
            elif platform == "qqbot":
                if msg_obj:
                    # QQ官方Bot的群信息
                    if hasattr(msg_obj, "group_id") and msg_obj.group_id:
                        return str(msg_obj.group_id)
                    # 频道信息
                    if hasattr(msg_obj, "guild_id") and msg_obj.guild_id:
                        return str(msg_obj.guild_id)
                    if hasattr(msg_obj, "channel_id") and msg_obj.channel_id:
                        return str(msg_obj.channel_id)

            # Telegram (纸飞机)
            elif platform == "telegram":
                if msg_obj:
                    if hasattr(msg_obj, "chat") and msg_obj.chat:
                        chat = msg_obj.chat
                        chat_type = getattr(chat, "type", "")
                        chat_id = getattr(chat, "id", "")
                        if chat_type in ["group", "supergroup"]:
                            return str(chat_id)

            # 飞书
            elif platform == "feishu":
                if msg_obj:
                    if hasattr(msg_obj, "chat_id") and msg_obj.chat_id:
                        return str(msg_obj.chat_id)
                    if hasattr(msg_obj, "group_id") and msg_obj.group_id:
                        return str(msg_obj.group_id)

            # 通用回退
            if msg_obj:
                if hasattr(msg_obj, "group_id") and msg_obj.group_id:
                    return str(msg_obj.group_id)

            # 从 unified_msg_origin 提取
            umo = getattr(event, "unified_msg_origin", None)
            if umo:
                origin = str(umo)
                parts = origin.split(":")
                if len(parts) >= 3 and "group" in parts[1].lower():
                    return parts[2]
        except Exception:
            pass
        return None

    async def _get_group_members(self, event: AstrMessageEvent, group_id: str):
        """获取群成员列表，兼容多平台"""
        try:
            platform = self._get_platform_name(event)
            logger.info(f"[随机数] 尝试获取群成员列表，平台: {platform}, 群ID: {group_id}")

            # 方式1: 通过 event.bot.api.call_action (参考 astrbot_plugin_AtTool 实际代码)
            event_bot = getattr(event, "bot", None)
            if event_bot:
                bot_api = getattr(event_bot, "api", None)
                if bot_api and hasattr(bot_api, "call_action"):
                    logger.info(f"[随机数] 使用 event.bot.api.call_action")
                    try:
                        resp = await bot_api.call_action("get_group_member_list", group_id=group_id)
                        logger.info(f"[随机数] 响应类型: {type(resp)}")
                        if isinstance(resp, list):
                            logger.info(f"[随机数] 成功获取 {len(resp)} 个成员")
                            return resp
                        if isinstance(resp, dict) and "data" in resp:
                            data = resp["data"]
                            if isinstance(data, list):
                                logger.info(f"[随机数] 从 data 字段获取 {len(data)} 个成员")
                                return data
                    except Exception as e:
                        logger.debug(f"[随机数] event.bot.api.call_action 失败: {e}")

            # 方式2: 通过 platform_manager.get_insts() 获取客户端 (参考 astrbot_plugin_daily_qun 实际代码)
            platform_manager = getattr(self.context, "platform_manager", None)
            if platform_manager and hasattr(platform_manager, "get_insts"):
                insts = platform_manager.get_insts()
                if insts:
                    logger.info(f"[随机数] platform_manager.get_insts() 返回 {len(insts)} 个实例")
                    for inst in insts:
                        if hasattr(inst, "get_client"):
                            client = inst.get_client()
                            if client:
                                logger.info(f"[随机数] 通过 inst.get_client() 获取客户端, 类型: {type(client)}")
                                if hasattr(client, "call_action"):
                                    try:
                                        resp = await client.call_action("get_group_member_list", group_id=group_id)
                                        logger.info(f"[随机数] 响应类型: {type(resp)}")
                                        if isinstance(resp, list):
                                            logger.info(f"[随机数] 成功获取 {len(resp)} 个成员")
                                            return resp
                                        if isinstance(resp, dict) and "data" in resp:
                                            data = resp["data"]
                                            if isinstance(data, list):
                                                logger.info(f"[随机数] 从 data 字段获取 {len(data)} 个成员")
                                                return data
                                    except Exception as e:
                                        logger.debug(f"[随机数] client.call_action 失败: {e}")

            # 方式3: 从 context.bots 获取
            bots = getattr(self.context, "bots", None)
            if not bots and hasattr(self.context, "get_bots"):
                bots = self.context.get_bots()

            if bots and isinstance(bots, dict) and bots:
                logger.info(f"[随机数] context.bots 键: {list(bots.keys())}")
                for key, bot_inst in bots.items():
                    actual_client = getattr(bot_inst, "bot", None) or bot_inst
                    if actual_client and hasattr(actual_client, "call_action"):
                        try:
                            resp = await actual_client.call_action("get_group_member_list", group_id=group_id)
                            logger.info(f"[随机数] 响应类型: {type(resp)}")
                            if isinstance(resp, list):
                                logger.info(f"[随机数] 成功获取 {len(resp)} 个成员")
                                return resp
                            if isinstance(resp, dict) and "data" in resp:
                                data = resp["data"]
                                if isinstance(data, list):
                                    logger.info(f"[随机数] 从 data 字段获取 {len(data)} 个成员")
                                    return data
                        except Exception as e:
                            logger.debug(f"[随机数] context.bots['{key}'].call_action 失败: {e}")

            logger.warning(f"[随机数] 所有方式均无法获取群成员列表")
        except Exception as e:
            logger.error(f"[随机数] 获取群成员列表异常: {e}")
            import traceback
            logger.error(f"[随机数] 异常详情: {traceback.format_exc()}")

        return []

    # ========== 命令处理 ==========

    @filter.command("随机数")
    async def random_number(self, event: AstrMessageEvent,
                            count: str = None, min_val: str = None, max_val: str = None):
        """生成随机数。用法: 随机数 [数量] [最小值] [最大值]
        最小值或最大值位置可用 - _ / # * 表示使用默认值
        """
        # 确保参数是字符串类型
        count = str(count) if count is not None else None
        min_val = str(min_val) if min_val is not None else None
        max_val = str(max_val) if max_val is not None else None
        
        # 帮助指令处理
        if count and count.lower() in ["帮助", "help"]:
            help_text = (
                "随机数插件使用帮助\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "随机数命令\n"
                "格式: /随机数 [数量] [最小值] [最大值]\n"
                "提示: 最小值/最大值可用 - _ / # * 表示使用默认值\n"
                "\n"
                "抛硬币命令\n"
                "格式: /抛硬币\n"
                "\n"
                "成员抽奖命令\n"
                "格式: /成员抽奖 [人数] [y/n]\n"
                "y: 排除管理员和群主（默认）\n"
                "n: 不排除"
            )
            yield event.plain_result(help_text)
            return

        request_text = f"数量={count or '默认'} 最小值={min_val or '默认'} 最大值={max_val or '默认'}"
        try:
            cnt = int(count) if count else self.config.get("default_count", 1)
            min_v = self._parse_int_or_default(min_val, self.config.get("default_min", 1))
            max_v = self._parse_int_or_default(max_val, self.config.get("default_max", 100))
        except ValueError:
            result_text = "参数格式错误，请输入数字。"
            yield event.plain_result(
                f"{result_text}\n"
                "用法: 随机数 [数量] [最小值] [最大值]\n"
                "输入「随机数 帮助」查看详细使用说明"
            )
            self._record_usage(event, "random_number", request_text, result_text)
            return

        max_count = self.config.get("max_count", 100)
        if min_v > max_v:
            result_text = "最小值不能大于最大值。"
            yield event.plain_result(result_text)
            self._record_usage(event, "random_number", request_text, result_text)
            return

        if cnt < 1 or cnt > max_count:
            result_text = f"生成数量需在 1~{max_count} 之间。"
            yield event.plain_result(result_text)
            self._record_usage(event, "random_number", request_text, result_text)
            return

        numbers = [random.randint(min_v, max_v) for _ in range(cnt)]

        if cnt == 1:
            result_text = f"随机数: {numbers[0]}"
        else:
            result_text = f"在 {min_v}~{max_v} 范围内生成 {cnt} 个随机数:\n" + \
                          "\n".join(f"  {i + 1}. {n}" for i, n in enumerate(numbers))

        yield event.plain_result(result_text)
        self._record_usage(event, "random_number", request_text, result_text)

    @filter.command("抛硬币")
    async def coin_flip(self, event: AstrMessageEvent):
        """抛硬币。正面49.5%，反面49.5%，立起来1%"""
        request_text = "抛硬币"
        
        # 生成0-999的随机数，0-494为正面(49.5%)，495-989为反面(49.5%)，990-999为立起来(1%)
        roll = random.randint(0, 999)
        
        if roll < 495:
            result_text = "🪙 硬币落地，结果是: 正面"
        elif roll < 990:
            result_text = "🪙 硬币落地，结果是: 反面"
        else:
            result_text = "🪙 哇！硬币竟然立起来了没有倒下！\n今天运气爆棚，快去刮彩票吧！"
        
        yield event.plain_result(result_text)
        self._record_usage(event, "coin_flip", request_text, result_text)

    @filter.command("成员抽奖")
    async def member_lottery(self, event: AstrMessageEvent,
                             count: str = None, exclude_admin: str = None):
        """群成员抽奖。用法: /成员抽奖 [人数] [y排除管理/n不排除]"""
        count = str(count) if count is not None else None
        exclude_admin = str(exclude_admin) if exclude_admin is not None else None
        request_text = f"人数={count or '默认'} 排除管理员={exclude_admin or '默认'}"
        group_id = self._extract_group_id(event)
        if not group_id:
            result_text = "该命令只能在群聊中使用。"
            yield event.plain_result(result_text)
            self._record_usage(event, "member_lottery", request_text, result_text)
            return

        try:
            cnt = int(count) if count else self.config.get("lottery_default_count", 1)
        except ValueError:
            result_text = "人数格式错误，请输入数字。"
            yield event.plain_result(result_text)
            self._record_usage(event, "member_lottery", request_text, result_text)
            return

        if cnt < 1:
            result_text = "抽奖人数至少为1。"
            yield event.plain_result(result_text)
            self._record_usage(event, "member_lottery", request_text, result_text)
            return

        # 解析是否排除管理员
        if exclude_admin is None:
            do_exclude = self.config.get("lottery_exclude_admin", True)
        else:
            # 兼容字符串和布尔值
            if isinstance(exclude_admin, bool):
                do_exclude = exclude_admin
            else:
                do_exclude = str(exclude_admin).lower() != 'n'

        # 获取群成员列表
        try:
            members = await self._get_group_members(event, group_id)
        except Exception as e:
            result_text = f"获取群成员列表失败: {e}"
            yield event.plain_result(result_text)
            self._record_usage(event, "member_lottery", request_text, result_text)
            return

        if not members:
            result_text = "获取群成员列表失败，当前平台可能不支持此功能。"
            yield event.plain_result(result_text)
            self._record_usage(event, "member_lottery", request_text, result_text)
            return

        # 过滤成员
        if do_exclude:
            candidates = [m for m in members if m.get("role") == "member"]
        else:
            candidates = members

        if not candidates:
            result_text = "没有符合条件的成员可以抽奖。"
            yield event.plain_result(result_text)
            self._record_usage(event, "member_lottery", request_text, result_text)
            return

        if cnt > len(candidates):
            result_text = f"符合条件的成员只有 {len(candidates)} 人，无法抽取 {cnt} 人。"
            yield event.plain_result(result_text)
            self._record_usage(event, "member_lottery", request_text, result_text)
            return

        # 随机抽取
        winners = random.sample(candidates, cnt)

        exclude_text = "（已排除管理员和群主）" if do_exclude else "（包含所有成员）"
        result_text = f"🎉 抽奖结果 {exclude_text}\n"
        for i, w in enumerate(winners):
            name = w.get("nickname") or w.get("user_id") or "未知"
            uid = w.get("user_id") or "未知"
            result_text += f"  {i + 1}. {name}（{uid}）\n"

        yield event.plain_result(result_text.strip())
        self._record_usage(event, "member_lottery", request_text, result_text)
