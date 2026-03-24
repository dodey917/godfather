import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # e.g., '@channel_username' or '-1001234567890'
NOTIFICATION_CHAT_ID = os.getenv('NOTIFICATION_CHAT_ID')  # Your chat ID to receive notifications

# Check interval in seconds (how often to check for new members)
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '30'))

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
