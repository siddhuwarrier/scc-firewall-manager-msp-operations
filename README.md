This is a Python script that illustrates using the SCC Firewall Manager API to perform operations on
tenants managed by an MSSP portal. It currently has a single command, `get-suggested-ftd-versions`,
which retrieves the suggested FTD version to upgrade to for each device on each tenant managed by
the MSP portal. This has been written primarily as a proof of concept to illustrate how you can use
the MSSP portal token to perform operations on the tenants managed by the MSSP portal using
the [scc-firewall-manager](https://pypi.org/project/scc-firewall-manager-sdk/) Python SDK.

# Pre-requisites
Python 3.12

# Installation
Use pip to install the requirements:

```shell
pip install -r requirements.txt
```

# Usage

The CLI provides a help function. You can use this to figure out what the CLI does.

```shell
python cli.py --help
python cli.py get-suggested-ftd-versions --help
```


