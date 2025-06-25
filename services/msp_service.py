import sys
from typing import List

from cdo_sdk_python import CdoTransaction, ApiTokenInfo, ApiException
from scc_firewall_manager_sdk import (
    MSPApi,
    MspManagedTenant,
    UserPage,
    MspAddUsersToTenantInput,
    UserInput,
    UserRole,
    User,
)

from services.transaction_service import TransactionService


class MspService:
    def __init__(self, api_client):
        self.msp_api: MSPApi = MSPApi(api_client)
        self.transaction_service: TransactionService = TransactionService(api_client)

    def get_managed_tenants(self) -> List[MspManagedTenant]:
        return self.do_get_managed_tenants(limit=50, offset=0)

    def do_get_managed_tenants(
        self, limit: int = 50, offset: int = 0, managed_tenants=None
    ) -> List[MspManagedTenant]:
        if managed_tenants is None:
            managed_tenants = []
        managed_tenants_response = self.msp_api.get_msp_managed_tenants(
            limit=str(limit), offset=str(offset)
        )
        if managed_tenants_response.count > offset + limit:
            return self.do_get_managed_tenants(
                limit, offset + limit, managed_tenants + managed_tenants_response.items
            )
        else:
            return managed_tenants + managed_tenants_response.items

    def create_api_only_user(self, tenant_uid: str, username: str) -> None:
        msp_add_users_to_tenant_input: MspAddUsersToTenantInput = (
            MspAddUsersToTenantInput(
                users=[
                    UserInput(
                        api_only_user=True,
                        username=username,
                        role=UserRole.ROLE_SUPER_ADMIN,
                    )
                ]
            )
        )
        cdo_transaction: CdoTransaction = (
            self.msp_api.add_users_to_tenant_in_msp_portal(
                tenant_uid=tenant_uid,
                msp_add_users_to_tenant_input=msp_add_users_to_tenant_input,
            )
        )
        self.transaction_service.wait_for_transaction_to_finish(
            cdo_transaction.transaction_uid
        )

    def get_user_by_name_in_tenant_in_msp_portal(
        self, tenant_uid: str, username: str
    ) -> User | None:
        user_page: UserPage
        user_page: UserPage = self.msp_api.get_api_only_users_in_msp_managed_tenant(
            tenant_uid=tenant_uid,
            limit="1",
            offset="0",
            q=f"name:{username}",
        )

        if user_page.count > 0:
            return user_page.items[0]
        return None

    def get_token_for_api_only_user(
        self, tenant_uid: str, tenant_name: str, username: str = "cli_user"
    ) -> str:
        user: User | None = self.get_user_by_name_in_tenant_in_msp_portal(
            tenant_uid=tenant_uid,
            username=f"{username}@{tenant_name}",
        )
        if user is None:
            self.create_api_only_user(
                tenant_uid=tenant_uid, username=f"{username}@{tenant_name}"
            )
            user = self.get_user_by_name_in_tenant_in_msp_portal(
                tenant_uid=tenant_uid, username=f"{username}@{tenant_name}"
            )

        api_token_info: ApiTokenInfo = (
            self.msp_api.generate_api_token_for_user_in_tenant(
                tenant_uid=tenant_uid, api_user_uid=user.uid
            )
        )
        return api_token_info.api_token

    def add_tenant(self, tenant_uid: str):
        """
        Add a tenant to the MSP portal.
        """
        try:
            cdo_transaction = self.msp_api.add_tenant_to_msp_portal(
                tenant_uid=tenant_uid
            )
            self.transaction_service.wait_for_transaction_to_finish(
                cdo_transaction.transaction_uid
            )
        except Exception as e:
            if e.reason != "Conflict":
                raise e
