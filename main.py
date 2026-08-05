import random
from astrbot.api.star import Context, Star
from astrbot.api import logger
from astrbot.api.event import filter

# 表示"不限制"的特殊字符
SKIP_CHARS = {'-', '_', '/', '#', '*'}


class RandomNumberPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.config = context.get_config()
        self.default_min = self.config.get("default_min", 1)
        self.default_max = self.config.get("default_max", 100)
        self.default_count = self.config.get("default_count", 1)
        self.max_count = self.config.get("max_count", 100)
        self.lottery_default_count = self.config.get("lottery_default_count", 1)
        self.lottery_exclude_admin = self.config.get("lottery_exclude_admin", True)

    def _parse_int_or_default(self, val, default):
        """解析整数，如果是特殊字符则返回None表示使用默认值"""
        if val is None:
            return default
        if val in SKIP_CHARS:
            return default
        return int(val)

    @filter.command("随机数")
    async def random_number(self, event, count: str = None, min_val: str = None, max_val: str = None):
        """生成随机数。用法: 随机数 [数量] [最小值] [最大值]
        最小值或最大值位置可用 - _ / # * 表示使用默认值
        """
        try:
            cnt = int(count) if count else self.default_count
            min_v = self._parse_int_or_default(min_val, self.default_min)
            max_v = self._parse_int_or_default(max_val, self.default_max)
        except ValueError:
            yield event.plain_result(
                "参数格式错误，请输入数字。\n"
                "用法: 随机数 [数量] [最小值] [最大值]\n"
                "最小值/最大值可用 - _ / # * 表示使用默认值"
            )
            return

        if min_v > max_v:
            yield event.plain_result("最小值不能大于最大值。")
            return

        if cnt < 1 or cnt > self.max_count:
            yield event.plain_result(f"生成数量需在 1~{self.max_count} 之间。")
            return

        numbers = [random.randint(min_v, max_v) for _ in range(cnt)]

        if cnt == 1:
            result = f"随机数: {numbers[0]}"
        else:
            result = f"在 {min_v}~{max_v} 范围内生成 {cnt} 个随机数:\n" + \
                     "\n".join(f"  {i + 1}. {n}" for i, n in enumerate(numbers))

        yield event.plain_result(result)

    @filter.command("掷骰子")
    async def roll_dice(self, event, sides: str = None):
        """掷骰子。用法: 掷骰子 [面数]（默认6面）"""
        try:
            s = int(sides) if sides else 6
        except ValueError:
            yield event.plain_result("参数格式错误，请输入数字。用法: 掷骰子 [面数]")
            return

        if s < 2:
            yield event.plain_result("骰子至少需要2面。")
            return

        result = random.randint(1, s)
        yield event.plain_result(f"🎲 掷出了一个 {s} 面骰子，结果是: {result}")

    @filter.command("成员抽奖")
    async def member_lottery(self, event, count: str = None, exclude_admin: str = None):
        """群成员抽奖。用法: /成员抽奖 [人数] [y排除管理/n不排除]"""
        group_id = event.message_obj.group_id
        if not group_id:
            yield event.plain_result("该命令只能在群聊中使用。")
            return

        # 解析参数
        try:
            cnt = int(count) if count else self.lottery_default_count
        except ValueError:
            yield event.plain_result("人数格式错误，请输入数字。")
            return

        if cnt < 1:
            yield event.plain_result("抽奖人数至少为1。")
            return

        # 解析是否排除管理员
        if exclude_admin is None:
            do_exclude = self.lottery_exclude_admin
        else:
            do_exclude = exclude_admin.lower() != 'n'

        # 获取群成员列表
        try:
            members = await self._get_group_members(event, group_id)
        except Exception as e:
            logger.error(f"获取群成员列表失败: {e}")
            yield event.plain_result(f"获取群成员列表失败: {e}")
            return

        if not members:
            yield event.plain_result("获取群成员列表为空，请确认在群聊中使用。")
            return

        # 过滤成员
        if do_exclude:
            candidates = [m for m in members if m.get("role") == "member"]
        else:
            candidates = members

        if not candidates:
            yield event.plain_result("没有符合条件的成员可以抽奖。")
            return

        if cnt > len(candidates):
            yield event.plain_result(f"符合条件的成员只有 {len(candidates)} 人，无法抽取 {cnt} 人。")
            return

        # 随机抽取
        winners = random.sample(candidates, cnt)

        exclude_text = "（已排除管理员和群主）" if do_exclude else "（包含所有成员）"
        result = f"🎉 抽奖结果 {exclude_text}\n"
        for i, w in enumerate(winners):
            name = w.get("nickname") or w.get("user_id") or "未知"
            user_id = w.get("user_id") or "未知"
            result += f"  {i + 1}. {name}（{user_id}）\n"

        yield event.plain_result(result.strip())

    async def _get_group_members(self, event, group_id):
        """获取群成员列表，兼容不同平台"""
        # 尝试通过 event 的 bot 对象获取（OneBot 协议）
        try:
            bot = event.get_bot()
            if hasattr(bot, 'get_group_member_list'):
                resp = await bot.get_group_member_list(group_id=group_id)
                if isinstance(resp, list):
                    return resp
        except Exception:
            pass

        # 尝试通过 message_handler 获取
        try:
            handler = event.message_handler
            if hasattr(handler, 'get_group_member_list'):
                return await handler.get_group_member_list(group_id)
        except Exception:
            pass

        # 尝试通过 context 获取
        try:
            provider = self.context.get_provider()
            if hasattr(provider, 'get_group_member_list'):
                return await provider.get_group_member_list(group_id)
        except Exception:
            pass

        logger.warning("无法获取群成员列表，当前平台可能不支持此功能")
        return []
