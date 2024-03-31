import asyncio
from asyncio import Queue
import datetime
import time
from collections import defaultdict
import logging
from RateLimitedWebhook import RateLimitedWebhook

BATCH_SEND_INTERVAL = 1  # Interval in seconds to check and send pending batches
MAX_BATCH_SIZE = 2000  # Maximum size of a batch message in characters
RAMP_UP_DURATION = 300  # Ramp-up duration in seconds (e.g. 5 minutes)

BATCH_QUEUE = Queue()
BATCH_LOCKS = defaultdict(asyncio.Lock)
REQUEST_COUNTS = defaultdict(int)
EVENT_COUNTERS = defaultdict(lambda: {'count': 0, 'last_event_time': 0})
EVENT_BATCHES = {}

LOG_CHANNELS = {}  # Dictionary to store logging channels for each server
LOG_EVENT_SETTINGS = {}
LOG_WEBHOOKS = {}  # Dictionary to store logging webhooks for each server

def is_busy_server(guild_id):
    current_time = time.time()
    time_window = 60  # Time window in seconds
    
    if current_time - EVENT_COUNTERS[guild_id]['last_event_time'] > time_window:
        EVENT_COUNTERS[guild_id]['count'] = 0
    
    event_count = EVENT_COUNTERS[guild_id]['count']
    base_threshold = 100  # Base threshold for considering a server as busy
    
    # Calculate the average event count per guild
    total_event_count = sum(counter['count'] for counter in EVENT_COUNTERS.values())
    num_guilds = len(EVENT_COUNTERS)
    avg_event_count = total_event_count / num_guilds
    
    # Adjust the threshold based on the average event count
    if avg_event_count > base_threshold:
        # If the average event count is higher than the base threshold,
        # lower the threshold for individual servers
        threshold = max(10, base_threshold - (avg_event_count - base_threshold) // 2)
    else:
        threshold = base_threshold
    
    logging.debug(f"is_busy_server: Guild ID: {guild_id}, Event Count: {event_count}, Threshold: {threshold}")
    return event_count >= threshold

def is_event_enabled(guild_id, event_name):
    logging.debug(f"is_event_enabled: Guild ID: {guild_id}, Event Name: {event_name}")
    return event_name in LOG_EVENT_SETTINGS.get(guild_id, set())

async def log_event(guild_id, event_name, embed):
    webhook_url = LOG_WEBHOOKS.get(guild_id)
    if webhook_url:
        webhook = RateLimitedWebhook(webhook_url, update_request_count_callback=update_request_count)
        if is_busy_server(guild_id):
            logging.debug(f"log_event: Guild ID: {guild_id}, Event Name: {event_name}, Batching event")
            # Batch the events for busy servers
            if guild_id not in EVENT_BATCHES:
                EVENT_BATCHES[guild_id] = []
            embed.timestamp = datetime.datetime.fromtimestamp(time.time(), datetime.timezone.utc)
            EVENT_BATCHES[guild_id].append(embed)
            
            # Check if the current batch exceeds the maximum size
            if sum(len(f"**{e.title}**\n{field.name}: {field.value}\n\n") for e in EVENT_BATCHES[guild_id] for field in e.fields) > MAX_BATCH_SIZE:
                async with BATCH_LOCKS[guild_id]:
                    batch_message = ""
                    for batch_embed in EVENT_BATCHES[guild_id]:
                        batch_message += f"**{batch_embed.title}**\n"
                        for field in batch_embed.fields:
                            batch_message += f"{field.name}: {field.value}\n"
                        batch_message += "\n"
                    
                    chunks = [batch_message[i:i+MAX_BATCH_SIZE] for i in range(0, len(batch_message), MAX_BATCH_SIZE)]
                    for chunk in chunks:
                        await webhook.send(content=chunk)
                    
                    EVENT_BATCHES[guild_id] = []
        else:
            logging.debug(f"log_event: Guild ID: {guild_id}, Event Name: {event_name}, Sending individual event")
            # Send individual embeds for light servers
            await webhook.send(embed=embed)
        
        # Update the event counter and timestamp for the server
        EVENT_COUNTERS[guild_id]['count'] += 1
        EVENT_COUNTERS[guild_id]['last_event_time'] = time.time()
    else:
        logging.warning(f"log_event: Guild ID: {guild_id}, Event Name: {event_name}, Webhook URL not found")

async def print_request_counts():
    global REQUEST_COUNTS
    while True:
        await asyncio.sleep(60)  # Print every 60 seconds, adjust as needed
        current_time = time.time()
        one_minute_ago = current_time - 60
        
        # Count the number of requests in the last minute
        requests_per_minute = sum(count for timestamp, count in REQUEST_COUNTS.items() if timestamp >= one_minute_ago)
        
        requests_per_second = requests_per_minute / 60
        logging.info(f"Estimated average Discord requests over 1 minute: {requests_per_second:.2f} per second")
        
        # Remove old entries from the request counts dictionary
        REQUEST_COUNTS = defaultdict(int, {timestamp: count for timestamp, count in REQUEST_COUNTS.items() if timestamp >= one_minute_ago})

def get_batch_interval(guild_id):
    event_count = EVENT_COUNTERS[guild_id]['count']
    base_interval = 10  # Base interval in seconds
    
    multiplier = 1 + (event_count // 10) * 0.5
    return base_interval * multiplier
        
async def ramp_up_logging():
    start_time = time.time()
    while True:
        elapsed_time = time.time() - start_time
        ramp_up_factor = min(elapsed_time / RAMP_UP_DURATION, 1.0)
        
        # Adjust the event counter threshold based on the ramp-up factor
        for guild_id in EVENT_COUNTERS:
            event_count = EVENT_COUNTERS[guild_id]['count']
            threshold = min(10 + event_count // 10, 50)
            EVENT_COUNTERS[guild_id]['threshold'] = int(threshold * ramp_up_factor)
        
        if ramp_up_factor >= 1.0:
            break
        
        await asyncio.sleep(1)  # Check every second

async def send_pending_batches():
    while True:
        try:
            current_time = datetime.datetime.now(datetime.timezone.utc)
            tasks = []
            for guild_id, batch in EVENT_BATCHES.items():
                if batch:
                    if batch[0].timestamp is not None:
                        batch_interval = get_batch_interval(guild_id)
                        if (current_time - batch[0].timestamp).total_seconds() >= batch_interval:
                            tasks.append(send_batch(guild_id, batch))
                    else:
                        # Remove the batch if the timestamp is None
                        EVENT_BATCHES[guild_id] = []
            
            if tasks:
                await asyncio.gather(*tasks)
        except Exception as e:
            logging.error(f"Error in send_pending_batches: {str(e)}")

        await asyncio.sleep(1)  # Check every second

async def send_batch(guild_id, batch):
    async with BATCH_LOCKS[guild_id]:
        batch_message = ""
        for batch_embed in batch:
            batch_message += f"**{batch_embed.title}**\n"
            for field in batch_embed.fields:
                batch_message += f"{field.name}: {field.value}\n"
            batch_message += "\n"
        
        webhook_url = LOG_WEBHOOKS.get(guild_id)
        if webhook_url:
            webhook = RateLimitedWebhook(webhook_url, update_request_count_callback=update_request_count)
            chunks = [batch_message[i:i+MAX_BATCH_SIZE] for i in range(0, len(batch_message), MAX_BATCH_SIZE)]
            for chunk in chunks:
                await webhook.send(content=chunk)
        
        EVENT_BATCHES[guild_id] = []

def update_request_count():
    current_time = time.time()
    REQUEST_COUNTS[current_time] = REQUEST_COUNTS.get(current_time, 0) + 1
