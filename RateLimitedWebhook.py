import asyncio
import requests
import time

class RateLimitedWebhook:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url
        self.lock = asyncio.Lock()
        self.reset_time = 0
        self.remaining_requests = 0
        self.session = requests.Session()

    async def send(self, content=None, embed=None):
        async with self.lock:
            if self.remaining_requests == 0 and time.time() < self.reset_time:
                delay = self.reset_time - time.time()
                await asyncio.sleep(delay)

            payload = {}
            if content:
                payload['content'] = content
            if embed:
                payload['embeds'] = [embed.to_dict()]

            response = self.session.post(self.webhook_url, json=payload)
            if response.status_code == 429:
                retry_after = float(response.headers.get('Retry-After', 1))
                self.reset_time = time.time() + retry_after
                self.remaining_requests = 0
                await asyncio.sleep(retry_after)
                return await self.send(content=content, embed=embed)
            else:
                self.remaining_requests = int(response.headers.get('X-RateLimit-Remaining', 0))
                self.reset_time = float(response.headers.get('X-RateLimit-Reset', 0))
                return response