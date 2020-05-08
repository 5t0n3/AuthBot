import pickle
import os
import yaml
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Only open the spreadsheet as read-only
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Load spreadsheet information from configuration file
SPREADSHEET_ID = ""
RANGE_NAME = ""

with open("sheetsconfig.yaml", "r") as config:
    config_obj = yaml.safe_load(config)
    SPREADSHEET_ID = config_obj["spreadsheet_id"]
    RANGE_NAME = config_obj["range_name"]


class CredentialError(ValueError):
    """ Error type for when credentials are not present. """
    pass


# NOTE: This function was taken from the Google Sheets API Quickstart page
def verify_credentials():
    credentials = None

    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            credentials = pickle.load(token)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES)
            credentials = flow.run_local_server(port=0)
    # Dump credentials to pickle file for later use
        with open("token.pickle", "wb") as token:
            pickle.dump(credentials, token)

    return credentials


# End Google Sheets API Quickstart Code


def fetch_data(credentials):
    if credentials is None:
        raise CredentialError(
            "You need to supply credentials via `verify_credentials`.")
    else:
        service = build("sheets", "v4", credentials=credentials)

        # Call sheets API
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
                                    range=RANGE_NAME).execute()
        values = result.get("values") or []

        return values
