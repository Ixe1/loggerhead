import asyncio
import requests
import time
import logging

class RateLimitedWebhook:
    def __init__(self, webhook_url, update_request_count_callback=None):
        self.webhook_url = webhook_url
        self.lock = asyncio.Lock()
        self.reset_time = 0.0
        self.remaining_requests = 0
        self.session = requests.Session()
        self.update_request_count_callback = update_request_count_callback

    async def send(self, content=None, embed=None):
        async with self.lock:
            if self.remaining_requests == 0 and time.time() < self.reset_time:
                delay = self.reset_time - time.time()
                logging.debug(f"RateLimitedWebhook: Waiting for {delay:.2f} seconds due to rate limit")
                await asyncio.sleep(delay)

            payload = {}
            if content:
                payload['content'] = content
            if embed:
                payload['embeds'] = [embed.to_dict()]

            logging.debug(f"RateLimitedWebhook: Sending payload: {payload}")
            response = self.session.post(self.webhook_url, json=payload)
            logging.debug(f"RateLimitedWebhook: Response status code: {response.status_code}")

            # Call the update_request_count_callback if it's provided
            if self.update_request_count_callback:
                self.update_request_count_callback()

            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After')
                if retry_after is not None:
                    retry_after = float(retry_after + 1.0)
                else:
                    retry_after = 1.0 # Default value if 'Retry-After' is not provided
                logging.error(f"RateLimitedWebhook encountered error 429, retrying after {float(retry_after)} seconds")
                self.reset_time = time.time() + retry_after
                self.remaining_requests = 0
                await asyncio.sleep(retry_after)
                return await self.send(content=content, embed=embed)
            else:
                self.remaining_requests = int(response.headers.get('X-RateLimit-Remaining', 0))
                reset_time_header = response.headers.get('X-RateLimit-Reset')
                if reset_time_header is not None:
                    self.reset_time = float(reset_time_header)
                else:
                    self.reset_time = 0.0 # Default value if 'X-RateLimit-Reset' is not provided
                return response
