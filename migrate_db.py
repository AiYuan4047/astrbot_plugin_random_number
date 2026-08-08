#!/usr/bin/env python3
"""
数据库迁移脚本
用于将旧版数据库升级到支持 platform 列的新版本

使用方法：
1. 停止 AstrBot
2. 进入插件目录：cd data/plugins/astrbot_plugin_random_number
3. 运行此脚本：python3 migrate_db.py
4. 启动 AstrBot
"""

import os
import sqlite3
import sys

# 数据库路径
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "random_number.db")

def migrate():
    """执行数据库迁移"""
    print(f"[迁移] 数据库路径: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print("[迁移] 数据库文件不存在，无需迁移")
        return True
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # 检查表是否存在
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='records'")
        if not c.fetchone():
            print("[迁移] records 表不存在，无需迁移")
            conn.close()
            return True
        
        # 检查列结构
        c.execute("PRAGMA table_info(records)")
        columns = [row["name"] for row in c.fetchall()]
        print(f"[迁移] 当前表结构: {columns}")
        
        if "platform" in columns:
            print("[迁移] platform 列已存在，无需迁移")
            conn.close()
            return True
        
        print("[迁移] 检测到旧版数据库，开始迁移...")
        
        # 备份旧数据
        c.execute("SELECT * FROM records")
        old_data = c.fetchall()
        old_columns = [desc[0] for desc in c.description] if c.description else []
        print(f"[迁移] 备份了 {len(old_data)} 条记录")
        print(f"[迁移] 旧表列: {old_columns}")
        
        # 删除旧表和索引
        print("[迁移] 删除旧表...")
        c.execute("DROP TABLE records")
        c.execute("DROP INDEX IF EXISTS idx_records_module")
        c.execute("DROP INDEX IF EXISTS idx_records_user")
        c.execute("DROP INDEX IF EXISTS idx_records_date")
        c.execute("DROP INDEX IF EXISTS idx_records_platform")
        conn.commit()
        
        # 创建新表
        print("[迁移] 创建新表...")
        c.execute("""
            CREATE TABLE records (
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
        conn.commit()
        
        # 恢复旧数据
        if old_data:
            print(f"[迁移] 恢复 {len(old_data)} 条记录...")
            for row in old_data:
                row_dict = dict(zip(old_columns, row))
                c.execute(
                    "INSERT INTO records (user_id, user_name, module, request, result, source_group, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (row_dict.get("user_id", ""), row_dict.get("user_name", ""),
                     row_dict.get("module", ""), row_dict.get("request", ""),
                     row_dict.get("result", ""), row_dict.get("source_group", ""),
                     row_dict.get("created_at", ""))
                )
            conn.commit()
        
        # 创建索引
        print("[迁移] 创建索引...")
        c.execute("CREATE INDEX IF NOT EXISTS idx_records_module ON records(module)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_records_user ON records(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_records_date ON records(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_records_platform ON records(platform)")
        conn.commit()
        
        # 验证
        c.execute("PRAGMA table_info(records)")
        new_columns = [row["name"] for row in c.fetchall()]
        print(f"[迁移] 新表结构: {new_columns}")
        
        conn.close()
        print("[迁移] 数据库迁移完成！")
        return True
        
    except Exception as e:
        print(f"[迁移] 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
