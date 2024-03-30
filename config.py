import psycopg2
from psycopg2 import OperationalError
import time
import logging
import yaml

LOG_EVENTS = [
    'guild_channel_create',
    'guild_channel_delete',
    'guild_channel_update',
    'guild_emojis_update',
    'guild_role_create',
    'guild_role_delete',
    'guild_role_update',
    'guild_update',
    'invite_create',
    'invite_delete',
    'member_ban',
    'member_join',
    'member_kick',
    'member_remove',
    'member_remove_timeout',
    'member_timeout',
    'member_unban',
    'member_update',
    'message_delete',
    'message_edit',
    'reaction_add',
    'reaction_remove',
    'voice_state_update',
    'webhooks_update'
]

def load_config():
    with open('config.yaml', 'r') as file:
        config = yaml.safe_load(file)
    return config

config = load_config()

DISCORD_TOKEN = config['discord_token']
DB_HOST = config['db_host']
DB_USER = config['db_user']
DB_PASSWORD = config['db_password']
DB_NAME = config['db_name']

conn = None

def create_config_table():
    conn = create_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS config
                 (guild_id BIGINT PRIMARY KEY,
                  log_channel_name TEXT,
                  log_events TEXT,
                  webhook_url TEXT)''')
    conn.commit()

def create_db_connection():
    global conn
    if conn is None or conn.closed:
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME
            )
            logging.info("Connected to the database.")
        except OperationalError as e:
            logging.error(f"Error connecting to the database: {str(e)}")
            conn = None
            
            # Retry the connection
            max_retries = 3
            retry_delay = 5  # seconds
            for retry in range(max_retries):
                logging.info(f"Retrying connection (attempt {retry + 1})...")
                time.sleep(retry_delay)
                try:
                    conn = psycopg2.connect(
                        host=DB_HOST,
                        user=DB_USER,
                        password=DB_PASSWORD,
                        database=DB_NAME
                    )
                    logging.info("Connected to the database after retry.")
                    break
                except OperationalError as e:
                    logging.error(f"Error connecting to the database (attempt {retry + 1}): {str(e)}")
                    conn = None
            
            if conn is None:
                raise Exception("Failed to establish a database connection.")
    
    return conn

def close_db_connection():
    global conn
    if conn is not None and not conn.closed:
        conn.close()
        logging.info("Closed the database connection.")

def get_config(guild_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT log_channel_name, log_events, webhook_url FROM config WHERE guild_id = %s", (guild_id,))
    result = c.fetchone()
    if result:
        log_channel_name, log_events, webhook_url = result
        if not log_events:
            log_events = ""
        return log_channel_name, log_events, webhook_url
    else:
        return None, "", None

def set_config(guild_id, log_channel_name, log_events):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO config (guild_id, log_channel_name, log_events) VALUES (%s, %s, %s) ON CONFLICT (guild_id) DO UPDATE SET log_channel_name = EXCLUDED.log_channel_name, log_events = EXCLUDED.log_events",
              (guild_id, log_channel_name, log_events))
    conn.commit()

def remove_config(guild_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM config WHERE guild_id = %s", (guild_id,))
    conn.commit()

def set_webhook_url(guild_id, webhook_url):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("UPDATE config SET webhook_url = %s WHERE guild_id = %s", (webhook_url, guild_id))
    conn.commit()

def get_webhook_url(guild_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT webhook_url FROM config WHERE guild_id = %s", (guild_id,))
    result = c.fetchone()
    return result[0] if result else None