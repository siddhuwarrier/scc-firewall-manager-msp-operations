import csv
from idlelib.pyparse import trans
from typing import List, Tuple

import click
import questionary
from click_option_group import optgroup, AllOptionGroup, MutuallyExclusiveOptionGroup
from rich.console import Console, Group
from rich.live import Live
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TaskID,
    SpinnerColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from scc_firewall_manager_sdk import (
    ApiClient,
    Configuration,
    MSPApi,
    Device,
    MspManagedTenant,
)
from scc_firewall_manager_sdk.exceptions import (
    UnauthorizedException,
    ForbiddenException,
)

from services.device_upgrade_service import DeviceUpgradeService
from services.inventory_api_service import InventoryApiService
from services.msp_service import MspService
from services.scc_credentials_service import SccCredentialsService
from utils.region_mapping import supported_regions

console = Console()
overall_progress: Progress = Progress(
    TextColumn("[progress.description]{task.description}({task.fields[tenant_name]})"),
    BarColumn(),
    TimeElapsedColumn(),
    TextColumn("{task.percentage:>3.0f}%"),
)
per_tenant_progress: Progress = Progress(
    TextColumn("[progress.description]{task.description}"),
    SpinnerColumn(),
    transient=True,
)
group = Group(overall_progress, per_tenant_progress)
live = Live(group)


@click.group()
@optgroup.group("API Credentials", cls=AllOptionGroup)
@optgroup.option(
    "--region",
    help="The region for the API.",
    type=click.Choice(supported_regions),
)
@optgroup.option("--api-token", type=str, help="The API token for the MSP Portal.")
@optgroup.group("Tenants", cls=MutuallyExclusiveOptionGroup)
@optgroup.option(
    "--tenant-uids",
    help="The UIDs of the managed tenant to perform operations on, separated by commas",
    type=str,
)
@optgroup.option(
    "--all",
    help="Perform operation on all managed tenants. This may take a while...",
    type=bool,
    is_flag=True,
)
@click.pass_context
def cli(ctx: any, api_token: str, region: str, tenant_uids: str, all: bool) -> None:
    tenant_uid_list = tenant_uids.split(",") if tenant_uids else []

    credentials_service = SccCredentialsService(region=region, api_token=api_token)
    credentials_service.load_or_prompt_credentials()
    retrieved_api_token, base_url = credentials_service.get_credentials()
    ctx.obj["base_url"] = base_url
    ctx.obj["api_token"] = retrieved_api_token
    ctx.obj["tenant_uids"] = tenant_uids
    ctx.obj["all"] = all

    with ApiClient(
        configuration=Configuration(host=base_url, access_token=retrieved_api_token)
    ) as api_client:
        msp_tenants_service = MspService(api_client)
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            SpinnerColumn(),
            transient=True,
        ) as progress:
            get_managed_tenants_task: TaskID = progress.add_task(
                "Getting managed tenants....", start=True
            )
            msp_managed_tenants = msp_tenants_service.get_managed_tenants()
            progress.stop_task(task_id=get_managed_tenants_task)

    if all:
        ctx.obj["managed_tenants"] = msp_managed_tenants
    elif len(tenant_uid_list) > 0:
        ctx.obj["managed_tenants"] = [
            msp_managed_tenant
            for msp_managed_tenant in msp_managed_tenants
            if msp_managed_tenant.uid in tenant_uid_list
        ]
    else:
        ctx.obj["managed_tenants"] = msp_managed_tenants


def get_api_token_for_user_in_tenant(
    msp_service: MspService, tenant: MspManagedTenant
) -> str | None:
    try:
        return msp_service.get_token_for_api_only_user(
            tenant_uid=tenant.uid, tenant_name=tenant.name
        )
    except UnauthorizedException as e:
        console.print(
            f"\nThe token used to connect tenant {tenant.display_name} to the MSSP portal is invalid. Please delete and re-onboard this tenant using the SCC Firewall MSSP portal.",
            style="red",
        )
        return None
    except ForbiddenException as e:
        console.print(
            f"\nThe token used to connect tenant {tenant.display_name} to the MSSP portal is not a super-admin token. Please delete and re-onboard this tenant using the SCC Firewall MSSP portal.",
            style="red",
        )


def select_tenants_using_cli(
    managed_tenants: List[MspManagedTenant],
) -> List[MspManagedTenant]:
    # Prepare the choices for the multi-select
    choices = [f"{tenant.display_name} ({tenant.uid})" for tenant in managed_tenants]

    # Prompt the user to select tenants
    selected_tenant_strs = questionary.checkbox(
        "Select tenants:", choices=choices
    ).ask()

    # Extract the tenant UIDs from the selected options
    selected_tenants = []
    for choice in selected_tenant_strs:
        tenant_uid = choice.split("(")[-1].strip(")")
        selected_tenants.append(
            next(
                (tenant for tenant in managed_tenants if tenant.uid == tenant_uid),
                None,
            )
        )

    return selected_tenants


def prepare_table() -> Table:
    """Prepare the table for displaying results."""
    table = Table(title="Suggested FTD versions")
    table.add_column("Tenant Name", justify="center")
    table.add_column("Tenant UID", justify="center")
    table.add_column("Device Name", justify="center")
    table.add_column("Device UID", justify="center")
    table.add_column("Version", justify="center")
    table.add_column("Upgrade Package UID", justify="center")
    return table


def get_suggested_ftd_version_info_for_device_in_tenant(
    device: Device, tenant: MspManagedTenant, tenant_api_client: ApiClient
) -> List[str]:
    """Get the suggested FTD version information for a device in a tenant."""
    device_upgrade_service = DeviceUpgradeService(tenant_api_client)
    get_device_upgrade_versions_task = per_tenant_progress.add_task(
        f"Getting suggested upgrade version for device {device.name} in {tenant.display_name}...",
        start=True,
    )
    suggested_version = device_upgrade_service.get_suggested_compatible_version(
        device_uid=device.uid
    )
    per_tenant_progress.stop_task(task_id=get_device_upgrade_versions_task)
    per_tenant_progress.remove_task(task_id=get_device_upgrade_versions_task)

    if suggested_version:
        return [
            tenant.display_name,
            tenant.uid,
            device.name,
            device.uid,
            suggested_version.software_version,
            suggested_version.upgrade_package_uid,
        ]
    else:
        return [
            tenant.name,
            tenant.uid,
            device.name,
            device.uid,
            "Not found",
            "N/A",
        ]


def get_sugggested_ftd_versions_for_tenant(
    tenant: MspManagedTenant, base_url: str, tenant_api_token: str
) -> list[str]:
    with ApiClient(
        Configuration(host=base_url, access_token=tenant_api_token)
    ) as tenant_api_client:
        inventory_api_service = InventoryApiService(tenant_api_client)
        get_ftd_devices_task = per_tenant_progress.add_task(
            f"Getting FTD devices in {tenant.display_name}...",
            start=True,
        )
        devices: List[Device] = inventory_api_service.get_devices(
            q="deviceType:CDFMC_MANAGED_FTD"
        )
        per_tenant_progress.stop_task(task_id=get_ftd_devices_task)
        per_tenant_progress.remove_task(task_id=get_ftd_devices_task)

        tenant_rows = []
        for device in devices:
            tenant_rows.append(
                get_suggested_ftd_version_info_for_device_in_tenant(
                    device, tenant, tenant_api_client
                )
            )

        return tenant_rows


def write_output_to_csv(output_file: str, csv_rows: list) -> None:
    with open(output_file, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        # Write header
        writer.writerow(
            [
                "Tenant Name",
                "Tenant UID",
                "Device Name",
                "Device UID",
                "Version",
                "Upgrade Package UID",
            ]
        )
        # Write rows
        writer.writerows(csv_rows)
    console.print(f"Results written to {output_file}", style="green")


@click.command(name="add-tenants")
@click.option(
    "--tenant-uids",
    type=click.Path(exists=True, dir_okay=False, readable=True, resolve_path=True),
    help="Path to a file containing tenant UIDs, one per line.",
)
@click.pass_context
def add_tenants_to_msp(ctx: any, tenant_uids: str) -> None:
    if tenant_uids:
        with open(tenant_uids, "r", encoding="utf-8") as file:
            tenant_uid_list = [line.strip() for line in file if line.strip()]
        ctx.obj["tenant_uids"] = tenant_uid_list
    else:
        ctx.obj["tenant_uids"] = []

    with live:
        tenants_task = overall_progress.add_task(
            "Adding tenants...", total=len(tenant_uids), tenant_name="TBD"
        )
        with ApiClient(
            Configuration(host=ctx.obj["base_url"], access_token=ctx.obj["api_token"])
        ) as api_client:
            msp_service = MspService(api_client)
            for tenant_uid in ctx.obj["tenant_uids"]:
                overall_progress.update(task_id=tenants_task, tenant_name=tenant_uid)
                msp_service.add_tenant(tenant_uid)
                overall_progress.update(tenants_task, advance=1)


@click.command(name="get-suggested-ftd-versions")
@click.option(
    "--output-file",
    type=click.Path(dir_okay=False, writable=True, resolve_path=True),
    help="Path to the output CSV file.",
)
@click.pass_context
def get_suggested_ftd_versions(ctx: any, output_file: str) -> None:
    table: Table = prepare_table()
    csv_rows = []  # To store rows for CSV output
    """Retrieve the list of suggested versions for the selected tenants."""
    if not ctx.obj["tenant_uids"] and not ctx.obj["all"]:
        selected_tenants = select_tenants_using_cli(ctx.obj["managed_tenants"])
    else:
        selected_tenants = ctx.obj["managed_tenants"]
    console.print(
        f"Getting suggested FTD version for {len(selected_tenants)} managed tenants. This may take a while..."
    )

    with live:
        tenants_task = overall_progress.add_task(
            "Processing tenants...", total=len(selected_tenants), tenant_name="TBD"
        )
        with ApiClient(
            Configuration(host=ctx.obj["base_url"], access_token=ctx.obj["api_token"])
        ) as api_client:
            msp_service = MspService(api_client)
            for tenant in selected_tenants:
                overall_progress.update(
                    task_id=tenants_task, tenant_name=tenant.display_name
                )
                tenant_api_token = get_api_token_for_user_in_tenant(msp_service, tenant)
                if tenant_api_token is None:
                    continue
                tenant_rows = get_sugggested_ftd_versions_for_tenant(
                    tenant, ctx.obj["base_url"], tenant_api_token
                )
                for tenant_row in tenant_rows:
                    table.add_row(*tenant_row)
                    csv_rows.append(tenant_row)
                overall_progress.update(tenants_task, advance=1)

    console.print(table)
    # Write to CSV if output file is specified
    if output_file:
        write_output_to_csv(output_file, csv_rows)


cli.add_command(get_suggested_ftd_versions)
cli.add_command(add_tenants_to_msp)
if __name__ == "__main__":
    cli(obj={})
