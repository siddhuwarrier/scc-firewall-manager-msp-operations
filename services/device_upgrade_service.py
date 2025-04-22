import sys

from rich.progress import SpinnerColumn, TextColumn, Progress
from scc_firewall_manager_sdk import DeviceUpgradesApi, FtdVersionsResponse
from scc_firewall_manager_sdk.exceptions import NotFoundException, ServiceException


class DeviceUpgradeService:
    def __init__(self, api_client):
        self.device_upgrades_api: DeviceUpgradesApi = DeviceUpgradesApi(api_client)

    def get_suggested_compatible_version(self, device_uid: str):
        try:
            ftd_versions_response: FtdVersionsResponse = (
                self.device_upgrades_api.get_compatible_ftd_versions(
                    device_uid=device_uid
                )
            )
        except ServiceException:
            print(
                "Working around known issue fixed in https://github.com/cisco-lockhart/cdo-jvm-modules/pull/3903 - this catch can be removed after 25/4/2025"
            )
            return None
        except NotFoundException:
            return None
        suggested_ftd_version = None
        for ftd_version in ftd_versions_response.items:
            if ftd_version.is_suggested_version:
                suggested_ftd_version = ftd_version
                break

        return suggested_ftd_version
