#!/usr/bin/env python3
"""
数据库修复脚本 - 一键修复 "no such column: platform" 错误

使用方法：
1. 停止 AstrBot
2. 进入 AstrBot 根目录
3. 运行：python3 data/plugins/astrbot_plugin_random_number/fix_db.py
4. 启动 AstrBot
"""

import os
import sqlite3
import sys

def find_db_files():
    """查找所有可能的数据库文件"""
    possible_paths = [
        # AstrBot 标准数据目录
        "data/plugin_data/astrbot_plugin_random_number/random_number.db",
        # 插件目录下的 data 文件夹
        "data/plugins/astrbot_plugin_random_number/data/random_number.db",
        "plugins/astrbot_plugin_random_number/data/random_number.db",
        # 当前目录
        "data/random_number.db",
        "random_number.db",
    ]
    
    found = []
    for path in possible_paths:
        if os.path.exists(path):
            found.append(path)
    
    return found

def check_and_fix_db(db_path):
    """检查并修复数据库"""
    print(f"\n检查数据库: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # 检查表是否存在
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='records'")
        if not c.fetchone():
            print("  ✗ records 表不存在，跳过")
            conn.close()
            return False
        
        # 检查列结构
        c.execute("PRAGMA table_info(records)")
        columns = [row[1] for row in c.fetchall()]
        print(f"  当前列: {columns}")
        
        if "platform" in columns:
            print("  ✓ platform 列已存在，无需修复")
            conn.close()
            return True
        
        print("  ! 检测到缺少 platform 列，正在修复...")
        
        # 备份旧数据
        c.execute("SELECT * FROM records")
        old_data = c.fetchall()
        old_columns = [desc[0] for desc in c.description] if c.description else []
        print(f"  备份了 {len(old_data)} 条记录")
        
        # 删除旧表
        print("  删除旧表...")
        c.execute("DROP TABLE records")
        conn.commit()
        
        # 创建新表
        print("  创建新表...")
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
            print(f"  恢复 {len(old_data)} 条记录...")
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
        print("  创建索引...")
        c.execute("CREATE INDEX IF NOT EXISTS idx_records_module ON records(module)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_records_user ON records(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_records_date ON records(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_records_platform ON records(platform)")
        conn.commit()
        
        # 验证
        c.execute("PRAGMA table_info(records)")
        new_columns = [row[1] for row in c.fetchall()]
        print(f"  新表结构: {new_columns}")
        
        if "platform" in new_columns:
            print("  ✓ 修复成功！")
            conn.close()
            return True
        else:
            print("  ✗ 修复失败，platform 列仍然不存在")
            conn.close()
            return False
            
    except Exception as e:
        print(f"  ✗ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 60)
    print("随机数插件数据库修复工具")
    print("=" * 60)
    
    # 查找数据库文件
    db_files = find_db_files()
    
    if not db_files:
        print("\n未找到数据库文件")
        print("\n请确保：")
        print("1. 插件已正确安装")
        print("2. 至少使用过一次插件（会创建数据库）")
        print("\n如果问题仍然存在，请手动删除数据库文件：")
        print("  rm data/plugin_data/astrbot_plugin_random_number/random_number.db")
        return 1
    
    print(f"\n找到 {len(db_files)} 个数据库文件:")
    for i, db_file in enumerate(db_files, 1):
        print(f"  {i}. {db_file}")
    
    # 修复所有找到的数据库
    success_count = 0
    for db_file in db_files:
        if check_and_fix_db(db_file):
            success_count += 1
    
    print("\n" + "=" * 60)
    print(f"修复完成: {success_count}/{len(db_files)} 个数据库修复成功")
    print("=" * 60)
    
    if success_count == len(db_files):
        print("\n请重启 AstrBot")
        return 0
    else:
        print("\n部分数据库修复失败，请检查日志")
        return 1

if __name__ == "__main__":
    sys.exit(main())
