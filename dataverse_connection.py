import os

from dotenv import load_dotenv
from azure.identity import ClientSecretCredential
from PowerPlatform.Dataverse.client import DataverseClient

load_dotenv()


def get_dataverse_client():

    required_variables = [
        "TENANT_ID",
        "CLIENT_ID",
        "CLIENT_SECRET",
        "DATAVERSE_URL"
    ]

    missing = [
        variable for variable in required_variables
        if not os.getenv(variable)
    ]

    if missing:
        raise EnvironmentError(
            f"Missing environment variables: {', '.join(missing)}"
        )

    credential = ClientSecretCredential(
        tenant_id=os.environ["TENANT_ID"],
        client_id=os.environ["CLIENT_ID"],
        client_secret=os.environ["CLIENT_SECRET"]
    )

    client = DataverseClient(
        os.environ["DATAVERSE_URL"],
        credential
    )

    return client