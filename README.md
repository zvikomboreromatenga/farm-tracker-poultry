# 🎈 Blank app template

A simple Streamlit app template for you to modify!

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://blank-app-template.streamlit.app/)

### How to run it on your own machine

1. Install the requirements

   ```bash
   pip install -r requirements.txt
   ```

2. Run the app

   ```bash
   streamlit run streamlit_app.py
   ```

Google Sheets persistence (two options)

1) Service account (server-to-server)

- Create a Google Cloud service account with the `Google Sheets API` enabled and generate a JSON key.
- Add the JSON key to Streamlit secrets as `gcp_service_account`. Example `secrets.toml` snippet:

```toml
[gcp_service_account]
# Paste fields from the service account JSON here, for example:
type = "service_account"
project_id = "your-project-id"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@...gserviceaccount.com"
client_id = "..."
# and the rest of the JSON fields as key = "value"

gs_spreadsheet_name = "FarmTrackerData"
gs_auto_load = false
```

Notes:
- Share the spreadsheet with the service account email if you want it to access an existing sheet.
- The app will auto-load if you set `gs_auto_load = true`.

2) OAuth2 (user-specific access)

- Create an OAuth 2.0 Client ID in Google Cloud (Desktop app / Other). Download the `client_secret.json`.
- Add the client JSON to Streamlit secrets as `gcp_oauth_client`. Example `secrets.toml` snippet:

```toml
[gcp_oauth_client]
# Copy the full JSON contents of the downloaded client_secret.json here.
# The structure should match Google's client_secret.json, for example:
"installed" = {client_id = "YOUR_CLIENT_ID", project_id = "...", auth_uri = "https://accounts.google.com/o/oauth2/auth", token_uri = "https://oauth2.googleapis.com/token", auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs", client_secret = "YOUR_CLIENT_SECRET", redirect_uris = ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"] }

gs_spreadsheet_name = "FarmTrackerData"
```

How the OAuth flow works in the app:
- Open the `Persistence` section in the app and choose `OAuth2 (User)`.
- Click `Start OAuth flow` to generate an authorization URL.
- Open the URL, grant access, copy the authorization code, paste it into the app and click `Complete OAuth flow`.
- The app stores credentials in the session for the current run and will then use your user credentials to read/write the spreadsheet.

Security & notes
- Never commit service account keys or OAuth client secrets to source control.
- Use Streamlit Cloud secrets or environment-backed secrets for production.
- The app stores user OAuth credentials only in the running session (not persisted to repo). If you need persistent per-user tokens, add secure storage (vault, encrypted sheet, etc.).

Questions or next steps
- I can add a sample `secrets.toml` file, automated token storage, or switch charts to Altair with date axes—which would you prefer?
