from py_eureka_client.eureka_client import EurekaClient
import asyncio

class DiscoveryUtils:
    instance = None
    client = None

    @classmethod
    def get_instance(cls):
        if cls.instance is None:
            cls.instance = DiscoveryUtils()

        return cls.instance
    def __init__(self):
        self.client = EurekaClient(eureka_server="http://localhost:8010/eureka",
                                   app_name="field-identifier-service", instance_ip="127.0.0.1",
                                   instance_host="127.0.0.1", instance_port=5000)

        asyncio.run(self.start_client())

    async def start_client(self):
        await self.client.start()

    async def stop_client(self):
        await self.client.stop()

    def get_client(self):
        return self.client
