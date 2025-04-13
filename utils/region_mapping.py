from questionary import Choice

supported_regions = ["us", "eu", "au", "apj", "in", "int"]
supported_regions_choices = [
    Choice(value="us", title="United States"),
    Choice(value="eu", title="Europe"),
    Choice(value="aus", title="Australia"),
    Choice(value="apj", title="Asia Pacific Japan"),
    Choice(value="in", title="India"),
    Choice(value="int", title="Staging (Cisco Developers only)"),
]


def get_scc_url(region):
    if region not in supported_regions:
        raise ValueError(f"Region {region} is not supported")
    elif region == "localhost":
        return "http://localhost:3077"
    return f"https://api.{region}.security.cisco.com/firewall"
