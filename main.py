import tomllib
import aiohttp
from loguru import logger
from typing import List, Dict, Optional
from datetime import datetime
from WechatAPI import WechatAPIClient
from utils.decorators import on_text_message
from utils.plugin_base import PluginBase
from database.XYBotDB import XYBotDB

class DifyConversationManager(PluginBase):
    description = "Dify对话管理插件"
    author = "AI助手"
    version = "1.0.0"

    def __init__(self):
        super().__init__()
        # 加载配置
        with open("plugins/DifyConversationManager/config.toml", "rb") as f:
            config = tomllib.load(f)
        
        plugin_config = config["DifyConversationManager"]
        
        # 基础配置
        self.enable = plugin_config["enable"]
        self.api_key = plugin_config["api-key"]
        self.base_url = plugin_config["base-url"]
        self.http_proxy = plugin_config.get("http-proxy", "")
        
        # 命令配置
        self.command_prefix = plugin_config.get("command-prefix", "/dify")
        self.commands = plugin_config.get("commands", ["列表", "历史", "删除", "重命名", "帮助"])
        self.command_tip = plugin_config.get("command-tip", "使用 /dify 帮助 查看使用说明")
        
        # 权限配置
        self.price = plugin_config.get("price", 0)
        self.admin_ignore = plugin_config.get("admin_ignore", True)
        self.whitelist_ignore = plugin_config.get("whitelist_ignore", True)
        
        # 分页配置
        self.default_page_size = plugin_config.get("default-page-size", 20)
        self.max_page_size = plugin_config.get("max-page-size", 100)

    @on_text_message
    async def handle_text(self, bot: WechatAPIClient, message: dict) -> bool:
        if not self.enable:
            return True

        content = message["Content"].strip()
        
        # 只响应 /dify 开头的命令
        if not content.startswith(self.command_prefix):
            return True

        # 提取命令部分
        cmd_content = content[len(self.command_prefix):].strip()
        
        # 如果只输入 /dify，显示帮助菜单
        if not cmd_content:
            await bot.send_text_message(message["FromWxid"], self.command_tip)
            return False

        # 处理删除所有对话的命令
        if cmd_content == "删除对话":
            await self.handle_delete_all_conversations(bot, message)
            return False

        # 处理具体命令
        if cmd_content == "列表":
            await self.handle_list_command(bot, message)
        elif cmd_content.startswith("历史 "):
            conv_id = cmd_content[3:].strip()
            await self.handle_history_command(bot, message, conv_id)
        elif cmd_content.startswith("删除 "):
            conv_id = cmd_content[3:].strip()
            await self.handle_delete_command(bot, message, conv_id)
        elif cmd_content.startswith("重命名 "):
            params = cmd_content[3:].strip()
            await self.handle_rename_command(bot, message, params)
        else:
            # 无效命令也显示帮助菜单
            await bot.send_text_message(message["FromWxid"], self.command_tip)

        return False

    async def handle_help_command(self, bot: WechatAPIClient, message: dict):
        """处理帮助命令"""
        help_text = (
            "📝 Dify对话管理助手\n\n"
            "支持的命令：\n"
            f"1. {self.command_prefix} {self.commands[0]}\n"
            "   查看所有对话列表\n\n"
            f"2. {self.command_prefix} {self.commands[1]} <对话ID>\n"
            "   查看指定对话的历史记录\n\n"
            f"3. {self.command_prefix} {self.commands[2]} <对话ID>\n"
            "   删除指定的对话\n\n"
            f"4. {self.command_prefix} {self.commands[3]} <对话ID> <新名称>\n"
            "   重命名指定的对话\n\n"
            "示例：\n"
            f"{self.command_prefix} {self.commands[0]}\n"
            f"{self.command_prefix} {self.commands[1]} abc-123\n"
            f"{self.command_prefix} {self.commands[3]} abc-123 测试对话"
        )
        await bot.send_text_message(message["FromWxid"], help_text)

    async def handle_list_command(self, bot: WechatAPIClient, message: dict):
        """处理列表命令"""
        try:
            conversations = await self.get_conversations(message["SenderWxid"])
            if not conversations:
                await bot.send_text_message(message["FromWxid"], "暂无对话记录")
                return

            output = "📝 对话列表：\n\n"
            for conv in conversations:
                created_time = datetime.fromtimestamp(conv["created_at"]).strftime("%Y-%m-%d %H:%M")
                output += f"🆔 ID: {conv['id']}\n"
                output += f"📌 名称: {conv['name']}\n"
                output += f"⏰ 创建时间: {created_time}\n"
                output += "---------------\n"

            await bot.send_text_message(message["FromWxid"], output)

        except Exception as e:
            logger.error(f"获取对话列表失败: {e}")
            await bot.send_text_message(message["FromWxid"], "获取对话列表失败，请稍后重试")

    async def handle_history_command(self, bot: WechatAPIClient, message: dict, conversation_id: str):
        """处理历史记录命令"""
        try:
            messages = await self.get_messages(message["SenderWxid"], conversation_id)
            if not messages:
                await bot.send_text_message(message["FromWxid"], "没有找到相关的对话历史")
                return

            output = f"📝 对话 {conversation_id} 的历史记录：\n\n"
            for msg in messages:
                created_time = datetime.fromtimestamp(msg["created_at"]).strftime("%Y-%m-%d %H:%M")
                output += f"⏰ {created_time}\n"
                output += f"❓ 问：{msg['query']}\n"
                output += f"💡 答：{msg['answer']}\n"
                output += "---------------\n"

            await bot.send_text_message(message["FromWxid"], output)

        except Exception as e:
            logger.error(f"获取对话历史失败: {e}")
            await bot.send_text_message(message["FromWxid"], "获取对话历史失败，请稍后重试")

    async def handle_delete_command(self, bot: WechatAPIClient, message: dict, conversation_id: str):
        """处理删除命令"""
        try:
            if await self.delete_conversation(message["SenderWxid"], conversation_id):
                await bot.send_text_message(message["FromWxid"], f"✅ 成功删除对话 {conversation_id}")
            else:
                await bot.send_text_message(message["FromWxid"], f"❌ 删除对话 {conversation_id} 失败")
        except Exception as e:
            logger.error(f"删除对话失败: {e}")
            await bot.send_text_message(message["FromWxid"], "删除对话失败，请稍后重试")

    async def handle_rename_command(self, bot: WechatAPIClient, message: dict, params: str):
        """处理重命名命令"""
        try:
            parts = params.split(maxsplit=1)
            if len(parts) != 2:
                await bot.send_text_message(
                    message["FromWxid"], 
                    f"格式错误！正确格式：{self.command_prefix} {self.commands[3]} <对话ID> <新名称>"
                )
                return

            conversation_id, new_name = parts
            if await self.rename_conversation(message["SenderWxid"], conversation_id, new_name):
                await bot.send_text_message(
                    message["FromWxid"], 
                    f"✅ 成功将对话 {conversation_id} 重命名为「{new_name}」"
                )
            else:
                await bot.send_text_message(
                    message["FromWxid"], 
                    f"❌ 重命名对话 {conversation_id} 失败"
                )
        except Exception as e:
            logger.error(f"重命名对话失败: {e}")
            await bot.send_text_message(message["FromWxid"], "重命名对话失败，请稍后重试")

    async def handle_delete_all_conversations(self, bot: WechatAPIClient, message: dict):
        """处理删除所有对话的命令"""
        try:
            wxid = message["SenderWxid"]
            chat_id = message["FromWxid"]
            is_group = message["IsGroup"]

            # 确定要删除的用户ID
            target_user = chat_id if is_group else wxid
            
            # 获取对话列表
            conversations = await self.get_conversations(target_user)
            if not conversations:
                msg = "当前群聊没有任何对话记录" if is_group else "您没有任何对话记录"
                await bot.send_text_message(chat_id, msg)
                return

            # 记录删除结果
            success_count = 0
            failed_count = 0
            failed_ids = []

            # 逐个删除对话
            for conv in conversations:
                try:
                    if await self.delete_conversation(target_user, conv['id']):
                        success_count += 1
                    else:
                        failed_count += 1
                        failed_ids.append(conv['id'])
                except Exception as e:
                    logger.error(f"删除对话 {conv['id']} 失败: {e}")
                    failed_count += 1
                    failed_ids.append(conv['id'])

            # 生成结果报告
            output = "📝 删除对话结果：\n\n"
            if is_group:
                output += f"🔹 群聊: {chat_id}\n"
            else:
                output += f"🔹 用户: {wxid}\n"
            
            output += f"✅ 成功删除: {success_count} 个对话\n"
            if failed_count > 0:
                output += f"❌ 删除失败: {failed_count} 个对话\n"
                if failed_ids:
                    output += "失败的对话ID：\n"
                    for failed_id in failed_ids:
                        output += f"- {failed_id}\n"
            
            # 发送结果
            if is_group:
                await bot.send_at_message(chat_id, output, [wxid])
            else:
                await bot.send_text_message(chat_id, output)

        except Exception as e:
            logger.error(f"删除所有对话时发生错误: {e}")
            error_msg = "删除对话时发生错误，请稍后重试"
            if is_group:
                await bot.send_at_message(chat_id, error_msg, [wxid])
            else:
                await bot.send_text_message(chat_id, error_msg)

    async def get_conversations(self, user: str, last_id: str = "", limit: int = 100) -> List[Dict]:
        """获取对话列表"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            params = {
                "user": user,
                "last_id": last_id,
                "limit": limit,
                "sort_by": "-updated_at"
            }
            
            url = f"{self.base_url}/conversations"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, proxy=self.http_proxy) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result.get("data", [])
                    else:
                        logger.error(f"获取对话列表失败: {resp.status} - {await resp.text()}")
                        return []
                        
        except Exception as e:
            logger.error(f"获取对话列表异常: {e}")
            return []

    async def delete_conversation(self, user: str, conversation_id: str) -> bool:
        """删除对话"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {"user": user}
            url = f"{self.base_url}/conversations/{conversation_id}"
            
            async with aiohttp.ClientSession() as session:
                async with session.delete(url, headers=headers, json=data, proxy=self.http_proxy) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result.get("result") == "success"
                    else:
                        logger.error(f"删除对话失败: {resp.status} - {await resp.text()}")
                        return False
                        
        except Exception as e:
            logger.error(f"删除对话异常: {e}")
            return False

    async def get_messages(self, user: str, conversation_id: str, first_id: str = "", limit: int = 20) -> List[Dict]:
        """获取对话历史消息"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            params = {
                "conversation_id": conversation_id,
                "user": user,
                "first_id": first_id,
                "limit": limit
            }
            
            url = f"{self.base_url}/messages"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, proxy=self.http_proxy) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result.get("data", [])
                    else:
                        logger.error(f"获取对话历史失败: {resp.status} - {await resp.text()}")
                        return []
                        
        except Exception as e:
            logger.error(f"获取对话历史异常: {e}")
            return []

    async def rename_conversation(self, user: str, conversation_id: str, new_name: str) -> bool:
        """重命名对话"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "name": new_name,
                "auto_generate": False,
                "user": user
            }
            
            url = f"{self.base_url}/conversations/{conversation_id}/name"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data, proxy=self.http_proxy) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return bool(result.get("name") == new_name)
                    else:
                        logger.error(f"重命名对话失败: {resp.status} - {await resp.text()}")
                        return False
                        
        except Exception as e:
            logger.error(f"重命名对话异常: {e}")
            return False