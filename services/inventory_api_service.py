from typing import List

from scc_firewall_manager_sdk import (
    InventoryApi,
    ApiClient,
    Device,
    DevicePage,
)


class InventoryApiService:
    def __init__(self, api_client: ApiClient):
        self.api_client = api_client
        self.inventory_api = InventoryApi(api_client)

    def get_devices(self, q: str = None) -> List[Device]:
        devices: List[Device] = []
        offset: int = 0
        limit: int = 200
        while True:
            device_page: DevicePage = self.inventory_api.get_devices(
                limit=str(limit), offset=str(offset), q=q
            )
            devices.extend(device_page.items)
            count = device_page.count
            offset += limit
            if len(devices) >= count:
                break

        return devices
