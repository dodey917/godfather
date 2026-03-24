import asyncio
import json
import os
from datetime import datetime
from typing import Set, Optional

from telegram import Bot
from telegram.error import TelegramError
from telegram.constants import ParseMode

import config

class SubscriberMonitor:
    def __init__(self):
        self.bot = Bot(token=config.BOT_TOKEN)
        self.known_members: Set[int] = set()
        self.data_file = 'known_members.json'
        self.load_known_members()
        
    def load_known_members(self):
        """Load known members from file"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.known_members = set(data.get('members', []))
                config.logger.info(f"Loaded {len(self.known_members)} known members")
            except Exception as e:
                config.logger.error(f"Error loading members: {e}")
                self.known_members = set()
        else:
            self.known_members = set()
            
    def save_known_members(self):
        """Save known members to file"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump({'members': list(self.known_members)}, f)
            config.logger.info(f"Saved {len(self.known_members)} members")
        except Exception as e:
            config.logger.error(f"Error saving members: {e}")
    
    async def get_channel_members(self) -> Set[int]:
        """Get all current channel members"""
        members = set()
        try:
            # Get chat administrators (since bot is admin)
            admins = await self.bot.get_chat_administrators(config.CHANNEL_ID)
            for admin in admins:
                members.add(admin.user.id)
                config.logger.debug(f"Found admin: {admin.user.id}")
            
            # Note: For channels, you can't get all subscribers directly via bot API
            # This is a limitation of Telegram API. You can only get admins.
            # Alternative approach: Track join events via chat member updates
            
        except TelegramError as e:
            config.logger.error(f"Error getting channel members: {e}")
            
        return members
    
    async def get_chat_member_updates(self, offset: int = None):
        """Get chat member updates (works for tracking new members)"""
        # This requires the bot to be added as an admin with appropriate permissions
        try:
            # Get updates from the bot's webhook/polling
            # Since we're running as a background worker, we'll use polling
            updates = await self.bot.get_updates(
                offset=offset,
                allowed_updates=['chat_member', 'my_chat_member']
            )
            return updates
        except TelegramError as e:
            config.logger.error(f"Error getting updates: {e}")
            return []
    
    async def send_notification(self, user_id: int, username: str = None, 
                                first_name: str = None, last_name: str = None):
        """Send notification about new subscriber"""
        user_mention = ""
        if username:
            user_mention = f"@{username}"
        elif first_name:
            user_mention = f"{first_name} {last_name if last_name else ''}".strip()
        else:
            user_mention = f"User ID: {user_id}"
        
        message = (
            f"🎉 **New Channel Subscriber!** 🎉\n\n"
            f"**User:** {user_mention}\n"
            f"**User ID:** `{user_id}`\n"
            f"**Joined:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"**Channel:** {config.CHANNEL_ID}"
        )
        
        try:
            await self.bot.send_message(
                chat_id=config.NOTIFICATION_CHAT_ID,
                text=message,
                parse_mode=ParseMode.MARKDOWN
            )
            config.logger.info(f"Notification sent for user {user_id}")
        except TelegramError as e:
            config.logger.error(f"Error sending notification: {e}")
    
    async def process_chat_member_update(self, update):
        """Process chat member updates"""
        if hasattr(update, 'chat_member') and update.chat_member:
            member_update = update.chat_member
            chat_id = member_update.chat.id
            
            # Check if this is from our channel
            if str(chat_id) == config.CHANNEL_ID or f"@{chat_id}" == config.CHANNEL_ID:
                new_member = member_update.new_chat_member
                old_member = member_update.old_chat_member
                
                # Check if user joined (wasn't a member before, now is)
                if (old_member and old_member.status in ['left', 'kicked'] and 
                    new_member and new_member.status == 'member'):
                    
                    user = new_member.user
                    user_id = user.id
                    
                    if user_id not in self.known_members:
                        self.known_members.add(user_id)
                        self.save_known_members()
                        
                        await self.send_notification(
                            user_id=user_id,
                            username=user.username,
                            first_name=user.first_name,
                            last_name=user.last_name
                        )
    
    async def monitor_subscribers(self):
        """Main monitoring loop"""
        config.logger.info("Starting subscriber monitor...")
        
        # Get initial known members (only admins for now)
        initial_members = await self.get_channel_members()
        if initial_members:
            self.known_members.update(initial_members)
            self.save_known_members()
        
        last_update_id = 0
        
        while True:
            try:
                # Get updates from Telegram
                updates = await self.bot.get_updates(
                    offset=last_update_id + 1,
                    allowed_updates=['chat_member', 'my_chat_member'],
                    timeout=30
                )
                
                for update in updates:
                    last_update_id = update.update_id
                    await self.process_chat_member_update(update)
                
                # Alternative: Check via get_chat_administrators periodically
                # This is less reliable but works as backup
                await self.check_admins_periodically()
                
            except Exception as e:
                config.logger.error(f"Error in monitoring loop: {e}")
            
            await asyncio.sleep(config.CHECK_INTERVAL)
    
    async def check_admins_periodically(self):
        """Periodically check admins (backup method)"""
        # Only check every 5th cycle to avoid rate limits
        if hasattr(self, '_admin_check_counter'):
            self._admin_check_counter += 1
        else:
            self._admin_check_counter = 0
            
        if self._admin_check_counter >= 5:
            self._admin_check_counter = 0
            current_members = await self.get_channel_members()
            new_members = current_members - self.known_members
            
            for member_id in new_members:
                self.known_members.add(member_id)
                # Try to get user info
                try:
                    user = await self.bot.get_chat(member_id)
                    await self.send_notification(
                        user_id=member_id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name
                    )
                except:
                    await self.send_notification(user_id=member_id)
            
            if new_members:
                self.save_known_members()

async def main():
    """Main function to run the bot"""
    # Validate configuration
    if not config.BOT_TOKEN:
        config.logger.error("BOT_TOKEN not set in environment variables")
        return
    
    if not config.CHANNEL_ID:
        config.logger.error("CHANNEL_ID not set in environment variables")
        return
    
    if not config.NOTIFICATION_CHAT_ID:
        config.logger.error("NOTIFICATION_CHAT_ID not set in environment variables")
        return
    
    config.logger.info("Starting Telegram Subscriber Monitor Bot...")
    config.logger.info(f"Monitoring channel: {config.CHANNEL_ID}")
    config.logger.info(f"Sending notifications to: {config.NOTIFICATION_CHAT_ID}")
    config.logger.info(f"Check interval: {config.CHECK_INTERVAL} seconds")
    
    monitor = SubscriberMonitor()
    
    try:
        # Test bot connection
        me = await monitor.bot.get_me()
        config.logger.info(f"Bot connected: @{me.username}")
        
        # Start monitoring
        await monitor.monitor_subscribers()
        
    except KeyboardInterrupt:
        config.logger.info("Bot stopped by user")
    except Exception as e:
        config.logger.error(f"Fatal error: {e}")
        raise

if __name__ == '__main__':
    asyncio.run(main())
