# OAuth 2.0 Setup Guide for SAP Datasphere MCP Server

This guide walks you through setting up authentication for the SAP Datasphere MCP Server. There are two modes:

| Mode | `DATASPHERE_AUTH_MODE` | Datasphere sees | Setup |
|---|---|---|---|
| **Service propagation** (default) | `service` | one shared Technical User | Steps 1–4 below |
| **Principal propagation** | `principal` | the logged-in person, with their own space permissions | [Part 2](#-part-2-principal-propagation-call-datasphere-as-the-logged-in-user) |

To run the server on SAP BTP Cloud Foundry (deployable from Business Application Studio), see [Part 3](#️-part-3-deploy-on-sap-btp-cloud-foundry-from-sap-business-application-studio).

Part 1 (Steps 1–4) sets up the Technical User. Skip to Part 2 if every user should run with their own permissions. Part 3 deploys the result to Cloud Foundry.

# Part 1: Service Propagation (Technical User)

---

## 📋 Prerequisites

- SAP Datasphere account with administrative access
- Python 3.10 or higher installed
- Access to create OAuth clients in SAP Datasphere

---

## 🔐 Step 1: Create Technical User in SAP Datasphere

### 1.1 Navigate to App Integration

1. Log into your SAP Datasphere tenant
2. Click the **System** menu (☰) in the top-left
3. Select **Administration** → **App Integration**

### 1.2 Create OAuth Client

1. Click **Add a New OAuth Client**
2. Fill in the following details:

   **OAuth Client Name:**
   ```
   MCP Server Technical User
   ```

   **Purpose:**
   ```
   Model Context Protocol server for AI assistant integration
   ```

   **OAuth Client Type:**
   - Select **"Open Authentication 2.0"**
   - Select **"Client Credentials"** grant type

   **Authorization Scope:**
   - ✅ Enable **"Read"** access
   - ✅ Enable **"Write"** access (if you need query execution)
   - ✅ Enable **"Manage"** access (if you need administrative operations)

3. Click **Create**

### 1.3 Save OAuth Credentials

After creation, SAP Datasphere will display:

- **OAuth Client ID** (e.g., `sb-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx!xxxxx`)
- **Client Secret** (e.g., `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)

⚠️ **IMPORTANT:**
- Copy these credentials immediately
- The Client Secret is only shown once
- Store them securely (you'll need them in Step 2)

### 1.4 Note Your Token URL

The token URL follows this pattern:
```
https://<tenant-id>.authentication.<region>.hana.ondemand.com/oauth/token
```

**Example:**
```
https://<your-tenant-id>.authentication.eu10.hana.ondemand.com/oauth/token
```

**How to find your token URL:**
1. Look at your Datasphere URL: `https://<tenant-id>.<region>.hcs.cloud.sap`
2. Extract `<tenant-id>` and `<region>`
3. Build token URL: `https://<tenant-id>.authentication.<region>.hana.ondemand.com/oauth/token`

---

## ⚙️ Step 2: Configure MCP Server

### 2.1 Create `.env` File

Navigate to your MCP server directory and create a `.env` file:

```bash
cd sap-datasphere-mcp
cp .env.example .env
```

### 2.2 Edit `.env` File

Open `.env` in your text editor and paste your credentials:

```bash
# SAP Datasphere Connection
DATASPHERE_BASE_URL=https://your-tenant.eu10.hcs.cloud.sap
DATASPHERE_TENANT_ID=your-tenant-id

# OAuth 2.0 Credentials (Technical User)
DATASPHERE_CLIENT_ID=sb-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx!xxxxx
DATASPHERE_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DATASPHERE_TOKEN_URL=https://your-tenant.authentication.eu10.hana.ondemand.com/oauth/token

# Optional: OAuth Scope (leave empty for default)
DATASPHERE_SCOPE=

# Server Configuration
LOG_LEVEL=INFO
SERVER_PORT=8080

# Development Mode (set to false for production)
USE_MOCK_DATA=false
```

### 2.3 Replace Placeholder Values

Replace the following placeholders with your actual values:

| Placeholder | Replace With | Example |
|-------------|--------------|---------|
| `your-tenant.eu10.hcs.cloud.sap` | Your Datasphere URL | `your-tenant.eu10.hcs.cloud.sap` |
| `your-tenant-id` | Your tenant identifier | `<your-tenant-id>` |
| `sb-xxx...` | OAuth Client ID from Step 1.3 | `sb-12345678-xxxx-xxxx-xxxx-xxxxxxxxxxxx!b12345` |
| `xxxx...` | Client Secret from Step 1.3 | `aBcDeFgHiJkLmNoPqRsTuVwXyZ123456` |
| `your-tenant.authentication...` | Token URL from Step 1.4 | `<your-tenant-id>.authentication.eu10.hana.ondemand.com/oauth/token` |

### 2.4 Verify Configuration

**Security Checklist:**
- [ ] `.env` file is in `.gitignore` (already configured)
- [ ] Never commit `.env` to version control
- [ ] Client Secret is kept private
- [ ] File permissions are restricted: `chmod 600 .env` (Linux/Mac)

---

## 🧪 Step 3: Test OAuth Connection

### 3.1 Install Dependencies

```bash
pip install -r requirements.txt
```

### 3.2 Test Configuration

Run the configuration validator:

```bash
python -c "from config import get_settings; settings = get_settings(); print('✅ Configuration valid!')"
```

**Expected output:**
```
2025-10-29 14:00:00 - config.settings - INFO - Configuration loaded successfully
✅ Configuration valid!
```

### 3.3 Test OAuth Token Acquisition

Create a simple test script to verify OAuth works:

```bash
python -c "
import asyncio
from auth.oauth_handler import create_oauth_handler
from config import get_settings

async def test():
    settings = get_settings()
    handler = await create_oauth_handler(
        client_id=settings.datasphere_client_id,
        client_secret=settings.datasphere_client_secret,
        token_url=settings.datasphere_token_url
    )
    print('✅ OAuth token acquired successfully!')
    print(f'Token expires in: {handler._token.expires_in} seconds')

asyncio.run(test())
"
```

**Expected output:**
```
2025-10-29 14:00:00 - auth.oauth_handler - INFO - OAuth handler initialized for token URL: https://...
2025-10-29 14:00:00 - auth.oauth_handler - INFO - Access token acquired successfully (expires in 3600s)
✅ OAuth token acquired successfully!
Token expires in: 3600 seconds
```

### 3.4 Test API Connection

Test the full Datasphere connector:

```bash
python -c "
import asyncio
from auth.datasphere_auth_connector import DatasphereAuthConnector, DatasphereConfig
from config import get_settings

async def test():
    settings = get_settings()
    config = DatasphereConfig(**settings.get_datasphere_config())

    async with DatasphereAuthConnector(config) as connector:
        status = await connector.test_connection()
        if status['connected']:
            print('✅ Successfully connected to SAP Datasphere!')
            print(f'OAuth Status: {status[\"oauth_status\"][\"has_token\"]}')
        else:
            print(f'❌ Connection failed: {status[\"error\"]}')

asyncio.run(test())
"
```

---

## 🚀 Step 4: Start MCP Server

### 4.1 Start the Server

```bash
python sap_datasphere_mcp_server.py
```

**Expected output:**
```
2025-10-29 14:00:00 - __main__ - INFO - Starting SAP Datasphere MCP Server
2025-10-29 14:00:00 - auth.oauth_handler - INFO - OAuth handler initialized
2025-10-29 14:00:00 - auth.oauth_handler - INFO - Access token acquired successfully
2025-10-29 14:00:00 - __main__ - INFO - MCP Server initialized successfully
2025-10-29 14:00:00 - __main__ - INFO - Waiting for MCP client connections...
```

### 4.2 Configure Claude Desktop

Add to your Claude Desktop `claude_desktop_config.json`:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "sap-datasphere": {
      "command": "python",
      "args": ["sap_datasphere_mcp_server.py"],
      "cwd": "/absolute/path/to/sap-datasphere-mcp"
    }
  }
}
```

⚠️ **Important:**
- Use absolute path for `cwd`
- The `.env` file must be in the `cwd` directory
- Restart Claude Desktop after configuration

### 4.3 Verify in Claude Desktop

1. Restart Claude Desktop
2. Look for the 🔌 icon (MCP tools available)
3. Click it to see available tools
4. You should see:
   - `list_spaces`
   - `get_space_info`
   - `search_tables`
   - `get_table_schema`
   - etc.

---

# 🔑 Part 2: Principal Propagation (call Datasphere as the logged-in user)

With a Technical User every question runs with the same, usually too broad, authorization. With `DATASPHERE_AUTH_MODE=principal` the server calls Datasphere **as the person who asked**, and Datasphere applies that person's own space permissions.

Based on the SAP Community blog *MCP server for SAP Datasphere: access data as the logged-in user with principal propagation* (saved as [MCP server for SAP Datasphere.html](MCP%20server%20for%20SAP%20Datasphere.html)) and SAP's *Integrating with SAP Datasphere Consumption APIs using SAML Bearer Assertion*.

## How it works

```
MCP client ──(1) XSUAA access token as "Authorization: Bearer"──▶ this server (HTTP transport)
  this server validates the token (signature, issuer, audience, expiry, user_name, group "sac")
  this server ──(2) service token + X-user-token──▶ BTP Destination service
  Destination service builds + signs a SAML assertion and exchanges it at Datasphere
  this server ◀──(3) Datasphere token with the user's own scopes──
  this server ──(4) Consumption API call with that token──▶ Datasphere
```

The server holds no signing key and does no SAML itself. The **MCP client** performs the XSUAA login (OIDC authorization code flow) and sends the access token with every request.

## 📋 Prerequisites (Part 2)

- SAP Datasphere tenant with admin rights (System → Administration, Security → Users)
- BTP subaccount with admin rights (Trust Configuration, Destinations, service instances)
- SAP Cloud Identity Services (IAS) tenant. Admin rights are needed for Step 7; otherwise ask an IAS admin for that one step.
- A corporate identity provider connected to IAS (tested with Microsoft Entra ID; any IdP supported by IAS works)
- An MCP client that can log in at XSUAA and send the bearer token
- `pip install "sap-datasphere-mcp[http]"` (adds PyJWT for token validation)

Two details decide whether this works:

1. Datasphere only grants permissions if the SAML assertion contains the group **`sac`**.
2. Datasphere finds the user by a unique identifier, here the **e-mail address**. It must be identical in the identity provider, in IAS and in Datasphere (it ends up in the `user_name` claim of the XSUAA token).

Placeholders used below:

| Placeholder | Meaning |
|---|---|
| `<ias-tenant>` | your IAS tenant, e.g. `abc12345.accounts.ondemand.com` |
| `<subaccount-subdomain>` | subdomain of your BTP subaccount |
| `<dsp-host>` | host of your Datasphere tenant, e.g. `mytenant.eu20.hcs.cloud.sap` |

## Step 5: Datasphere user and roles

1. Datasphere → **Security → Users**. Find (or create) your user and check the **Email** column. It must equal the e-mail in IAS, otherwise the SAML assertion cannot be matched (401).
2. Select the user → **Roles**. Assign the **Consumption API User** permission through a role in your space, plus **Data Warehouse Cloud Consumer** (single space) or **Scoped Data Warehouse Cloud Consumer** (several spaces).

> Without the Consumption API permission every data query fails with **403 Forbidden**, even for administrators. Authentication is fine at that point, so it is easy to look in the wrong place.

## Step 6: Trust between BTP and IAS

BTP cockpit → subaccount → **Security → Trust Configuration**. Your IAS tenant must be listed and available for user logon. If it is missing, choose **Establish Trust** and select your IAS tenant (OpenID Connect, no SAML metadata exchange). This also creates an application in IAS named `SAP BTP subaccount <subaccount-subdomain>`.

If the corporate IdP is not yet trusted by IAS, set that up first (e.g. *Establish trust between Microsoft Entra ID and IAS*).

## Step 7: Add the attribute `Groups = sac` in IAS

1. IAS admin console → **Applications & Resources → Applications**.
2. Open `SAP BTP subaccount <subaccount-subdomain>` → **Attributes**.
3. Add attribute **Groups** with value **`sac`**. Save.

XSUAA copies the IAS groups into its token (`xs.system.attributes.xs.saml.groups`); the Destination service later passes them on in the SAML assertion.

## Step 8: Trust the BTP subaccount in Datasphere

1. BTP cockpit → subaccount → **Connectivity → Destination Trust → SAML IDP Trust Configuration → Export**. The XML contains the provider name and signing certificate of the subaccount.
2. Datasphere → **System → Administration → App Integration → Trusted Identity Providers → Add a Trusted Identity Provider**. Enter a name, copy **Provider Name** and **Signing Certificate** from the XML. Save.

## Step 9: Create the Datasphere OAuth client

Datasphere → **System → Administration → App Integration → OAuth Clients → Add a New OAuth Client**:

| Field | Value |
|---|---|
| Name | e.g. `mcp-datasphere` |
| Purpose | **API Access** |
| Access | Data Export Service |
| Authorization Grant | **SAML2.0 Bearer** |

Save and copy **Client ID** and **Secret** immediately (shown once). Then copy the two URLs shown above the client list: **OAuth2SAMLTokenURL** (ends in `/oauth/token/alias/<...>`) and **OAuth2SAMLAudience**.

> Purpose *Interactive Usage* does not work: it only offers the Authorization Code grant and the exchange fails with `Unauthorized grant type`.

## Step 10: Create the BTP destination

BTP cockpit → subaccount → **Connectivity → Destinations → Create Destination**:

| Property | Value | Note |
|---|---|---|
| Name | `Datasphere_Token_Exchange_MCP` | must equal `DESTINATION_NAME` |
| Type | `HTTP` | |
| URL | `https://<dsp-host>` | host only, no API path |
| Proxy Type | `Internet` | |
| Authentication | `OAuth2SAMLBearerAssertion` | |
| Audience | `OAuth2SAMLAudience` from Step 9 | exactly this one URL, not a list |
| AuthnContextClassRef | `urn:oasis:names:tc:SAML:2.0:ac:classes:PreviousSession` | |
| Client Key | Client ID from Step 9 | |
| Token Service URL | `OAuth2SAMLTokenURL` from Step 9 | must be the `/alias/...` URL |
| Token Service User | Client ID from Step 9 | |
| Token Service Password | Client secret from Step 9 | re-enter if you get `Bad credentials`; editing can clear it |

Additional properties:

| Property | Value | Note |
|---|---|---|
| `HTML5.DynamicDestination` | `true` | |
| `HTML5.SetXForwardedHeaders` | `false` | |
| `userIdSource` | `user_name` | claim that holds the e-mail |
| `nameIdFormat` | `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified` | passes `user_name` on unchanged |

`userIdSource` and `nameIdFormat` depend on where your IdP puts the user identifier. If it delivers another identifier (e.g. a login name), check which token claim holds it, adjust both properties and set `PP_USER_CLAIM` accordingly. The same identifier must exist in Datasphere.

## Step 11: BTP service instances

BTP cockpit → subaccount → **Instances and Subscriptions → Create**:

1. **Authorization and Trust Management Service**, plan `application`, e.g. `xsuaa-instance-mcp`, parameters:
   ```json
   {"xsappname": "mcp-datasphere", "tenant-mode": "dedicated"}
   ```
   Open the instance → **Service Keys → Create**. Note `url` and `clientid`. Your MCP client's login needs a redirect URI registered in the instance (parameter `oauth2-configuration.redirect-uris`), e.g. its callback URL.
2. **Destination Service**, plan `lite`. Open the instance → **Service Keys → Create**. Note `url`, `uri`, `clientid`, `clientsecret`.

## Step 12: Configure this server

Put the service-key values into `.env` (see `.env.example`). Keep them out of version control.

| Variable | Source |
|---|---|
| `DATASPHERE_AUTH_MODE=principal` | |
| `DATASPHERE_BASE_URL` | `https://<dsp-host>` |
| `XSUAA_URL`, `XSUAA_CLIENT_ID` | XSUAA service key `url`, `clientid` |
| `DESTINATION_SERVICE_URL`, `DESTINATION_SERVICE_URI` | Destination service key `url`, `uri` |
| `DESTINATION_CLIENT_ID`, `DESTINATION_CLIENT_SECRET` | Destination service key |
| `DESTINATION_NAME` | name from Step 10 |
| `PP_REQUIRED_GROUP` (default `sac`), `PP_USER_CLAIM` (default `user_name`) | must match Steps 7 and 10 |

The Technical User values (`DATASPHERE_CLIENT_ID/SECRET/TOKEN_URL`) are **not used** in this mode.

## Step 13: Start the server and connect the client

```bash
DATASPHERE_AUTH_MODE=principal sap-datasphere-mcp --transport http --host 0.0.0.0 --port 8080
```

The MCP client logs the user in at XSUAA (authorization code flow) and sends `Authorization: Bearer <XSUAA access token>` on every request to `/mcp`. `/health` and `/.well-known/oauth-protected-resource*` stay open. Note: if the XSUAA login fails with 401, send the client credentials in the request body (`client_secret_post`); with HTTP Basic the `!` and `|` in XSUAA client IDs get URL-encoded and break.

**Verify:** decode the access token and check that `user_name` is the user's e-mail (equal to Datasphere) and that `xs.system.attributes.xs.saml.groups` contains `sac`.

## Behaviour and guarantees

- **No Technical User fallback.** Without a valid user bound to the request the call fails; client credentials are never used in `principal` mode.
- **Fail-closed validation.** Bad signature, wrong issuer/audience, expired token or missing `user_name` → HTTP 401; missing group `sac` → HTTP 403.
- **Per-user isolation.** Datasphere tokens and all server-side caches (spaces, schemas, catalog, capability) are keyed by user.
- **Token lifetime.** Datasphere tokens are cached per user, refreshed 60 s before expiry, never kept beyond the user's XSUAA login. A 401 from Datasphere triggers one fresh exchange and a retry.
- **Startup guards.** `principal` mode refuses to start with stdio, `--stateful` (a stateful session would pin the first caller's identity), `--auth-token` (the header carries the user token instead) or `USE_MOCK_DATA=true`.

## Known limitations

- Tool *consent* state (`auth/consent_manager.py`) is still process-global, not per user. It gates MCP-level tool policy (e.g. SQL execution), not Datasphere data access, which Datasphere enforces per user.
- Tools that shell out to the Datasphere CLI (database-user management) use their own credentials, not the propagated user.
- The server validates tokens but does not perform the login; there is no local browser/callback flow (stdio). Use the HTTP transport. It publishes OAuth discovery metadata (see Part 3) so clients can find XSUAA.

## Troubleshooting (Part 2)

| Symptom | Cause | Fix |
|---|---|---|
| `Cannot determine user to propagate` | no user id found in the token | destination `userIdSource=user_name` (Step 10) |
| `None of the audiences ... matched` | several audience URLs | only `OAuth2SAMLAudience` (Step 9) |
| `No subject confirmation methods were met` | Token Service URL without `/alias/...` | use `OAuth2SAMLTokenURL` (Step 9) |
| `Bad credentials` | Token Service Password wrong or cleared | re-enter the client secret (Step 10) |
| `Unauthorized grant type` | OAuth client purpose is Interactive Usage | create an *API Access* client (Step 9) |
| 401 from Datasphere, token scope only `openid`/`uaa.user` | no `Groups=sac` in the assertion | Step 7, and log in through XSUAA |
| 403 on data queries | Consumption API permission missing | Step 5 |
| 401 from this server | invalid token, wrong audience or issuer | check `XSUAA_URL`, `XSUAA_CLIENT_ID` |
| 403 from this server | user lacks group `sac` | Step 7 |

**Tests:** `tests/test_principal_propagation.py` (validation, exchange, isolation, no fallback) and `tests/test_principal_propagation_http.py` (user identity through the real Streamable HTTP transport with concurrent callers). Neither needs a tenant.

---

---

# ☁️ Part 3: Deploy on SAP BTP Cloud Foundry (from SAP Business Application Studio)

The repository ships everything needed to run the server (in `principal` mode) as a Cloud Foundry application:

| File | Purpose |
|---|---|
| [`mta.yaml`](../mta.yaml) | MTA descriptor: app (python_buildpack, HTTP health check on `/health`) plus the `xsuaa` and `destination` service instances, bound automatically |
| [`xs-security.json`](../xs-security.json) | XSUAA configuration (`xsappname`, authorization code grant, redirect URIs) |
| [`mta-ext.mtaext.example`](../mta-ext.mtaext.example) | Extension descriptor template for your tenant values (keeps them out of git) |
| [`manifest.yml`](../manifest.yml), [`.cfignore`](../.cfignore) | Plain `cf push` alternative |
| [`requirements.txt`](../requirements.txt) | Runtime dependencies installed by the buildpack |

On Cloud Foundry the XSUAA and Destination credentials are read from the bound service instances (`VCAP_SERVICES`), so `XSUAA_*` and `DESTINATION_*` variables from Step 12 are **not** needed. Only `DATASPHERE_BASE_URL` has to be provided.

> Part 2, Steps 5–10 (Datasphere user/roles, trust, `Groups = sac`, OAuth client, destination) are still required. Steps 11–12 are replaced by this deployment.

## Prerequisites (Part 3)

- BTP subaccount with the Cloud Foundry environment enabled, a CF org and space, and the **Space Developer** role
- A SAP Business Application Studio dev space (it includes the `cf` CLI with the MultiApps plugin and the `mbt` build tool)
- Part 2, Steps 5–10 completed. The destination `Datasphere_Token_Exchange_MCP` is created **manually in the subaccount** (Step 10) because it contains the OAuth client secret. The app's Destination service instance resolves it.

## Step 14: Open the project in Business Application Studio

1. BAS → **Clone from Git** → select the repository and the branch `mcp-with-principal-propagation`.
2. Open a terminal in the project folder.

## Step 15: Set your tenant values

```bash
cp mta-ext.mtaext.example mta-ext.mtaext
```

Edit `mta-ext.mtaext` and set `DATASPHERE_BASE_URL` (`https://<dsp-host>`) and `DATASPHERE_TENANT_ID`. The file is git-ignored.

## Step 16: Log in to Cloud Foundry

In BAS use the CF sign-in (status bar / command palette *CF: Login to Cloud Foundry*) or:

```bash
cf login -a https://api.cf.<region>.hana.ondemand.com
cf target -o <org> -s <space>
```

## Step 17: Build and deploy

```bash
mbt build                                   # creates mta_archives/sap-datasphere-mcp_2.0.3.mtar
cf deploy mta_archives/sap-datasphere-mcp_2.0.3.mtar -e mta-ext.mtaext
```

This creates the `xsuaa` and `destination` instances, binds both and starts the app. (In BAS you can also right-click `mta.yaml` → *Build MTA Project* and then deploy the archive; that context-menu deploy does not take the extension descriptor, so set the tenant URL afterwards with `cf set-env sap-datasphere-mcp DATASPHERE_BASE_URL https://<dsp-host>` and `cf restage sap-datasphere-mcp`.)

**Alternative without MTA:**

```bash
cf create-service xsuaa application sap-datasphere-mcp-xsuaa -c xs-security.json
cf create-service destination lite sap-datasphere-mcp-destination
cf push --no-start
cf set-env sap-datasphere-mcp DATASPHERE_BASE_URL https://<dsp-host>
cf start sap-datasphere-mcp
```

## Step 18: Check the deployment

```bash
cf app sap-datasphere-mcp            # note the route, e.g. https://sap-datasphere-mcp-xyz.cfapps.<region>.hana.ondemand.com
curl https://<route>/health          # {"status":"ok","transport":"streamable-http"}
curl -i https://<route>/mcp          # 401: authentication is enforced
cf logs sap-datasphere-mcp --recent
```

## Step 19: Connect the MCP client

1. Register the client's callback URL in `xs-security.json` under `oauth2-configuration.redirect-uris` (the default only allows `http://localhost:*/**`), then redeploy or run `cf update-service sap-datasphere-mcp-xsuaa -c xs-security.json`.
2. Create a service key and note `url`, `clientid`, `clientsecret`:
   ```bash
   cf create-service-key sap-datasphere-mcp-xsuaa mcp-client
   cf service-key sap-datasphere-mcp-xsuaa mcp-client
   ```
3. Configure the client with the MCP URL `https://<route>/mcp` and the service key's `clientid`/`clientsecret`. A client with OAuth discovery finds XSUAA by itself (`curl https://<route>/.well-known/oauth-protected-resource/mcp` shows what it sees). Otherwise configure the endpoints manually: authorization code flow with `<url>/oauth/authorize` and `<url>/oauth/token` (credentials in the request body).
4. The client sends `Authorization: Bearer <access token>` to `https://<route>/mcp`.

The access token's audience must contain this XSUAA instance's `clientid`; tokens from another application are rejected with 401.

## Notes for Cloud Foundry

- The route is public. Every request except `/health` needs a valid user token; do not use `--auth-token`.
- The server is stateless. More than one instance works; each keeps its own in-memory token cache (just a few extra token exchanges).
- The `mta.yaml` and `manifest.yml` were written against SAP's documented formats but were **not built or deployed from this repository yet**. Expect to adjust on the first deployment (e.g. buildpack Python version: check with `cf buildpacks`).
- **OAuth discovery (RFC 9728).** The server publishes `/.well-known/oauth-protected-resource` (and `.../mcp`) without authentication. It names XSUAA as the authorization server, and every 401 carries `WWW-Authenticate: Bearer ..., resource_metadata="https://<route>/.well-known/oauth-protected-resource/mcp"`. The public URL comes from `MCP_PUBLIC_URL`, else the app's CF route (`VCAP_APPLICATION`), else the request's Host header. Set `MCP_PUBLIC_URL` if you use a custom domain.
- **Limitation: no dynamic client registration.** XSUAA does not support it. A client can discover *where* to log in, but it must be configured with the `clientid`/`clientsecret` of the service key (Step 19), and its callback URL must be in `redirect-uris`. Clients that only work with dynamic registration cannot be used.
- Discovery against a real XSUAA tenant has not been tested here. If a strict client rejects the metadata, set `MCP_AUTHORIZATION_SERVER` to the issuer URL your client expects.

## Troubleshooting (Part 3)

| Symptom | Cause | Fix |
|---|---|---|
| App crashes: `DATASPHERE_BASE_URL is not set` | tenant value missing | extension descriptor (Step 15) or `cf set-env` |
| App crashes: `... these variables are not set: XSUAA_URL ...` | service instances not bound | `cf services`; bind with `cf bind-service` and restage |
| Staging fails on `pip install` | Python version of the buildpack too old for `mcp>=2` | `cf buildpacks`; pick a newer buildpack or add `runtime.txt` |
| Health check fails | app not listening on `$PORT` | keep `--host 0.0.0.0 --port $PORT` in the start command |
| 401 on `/mcp` with a token | wrong audience or issuer | log in via this app's XSUAA instance (Step 19) |
| `Destination lookup failed (HTTP 404)` | destination missing or misnamed | create it in the subaccount, name equals `DESTINATION_NAME` (Step 10) |

# Troubleshooting & Reference (Part 1)

## 🔧 Troubleshooting

### Error: "Configuration validation failed"

**Problem:** Missing or invalid environment variables

**Solution:**
```bash
# Check which variables are missing
python -c "from config import get_settings; get_settings()"

# Verify .env file exists and has correct format
cat .env
```

### Error: "Token acquisition failed: HTTP 401"

**Problem:** Invalid client credentials

**Solutions:**
1. Verify Client ID is correct (copy-paste from SAP Datasphere)
2. Verify Client Secret is correct
3. Check if OAuth client is still active in SAP Datasphere
4. Ensure no extra spaces in `.env` file values

### Error: "Token acquisition failed: HTTP 404"

**Problem:** Incorrect token URL

**Solutions:**
1. Verify tenant ID in token URL matches your Datasphere URL
2. Verify region (e.g., `eu10`, `us10`) matches
3. Check URL format: `https://<tenant>.authentication.<region>.hana.ondemand.com/oauth/token`

### Error: "Network error during token acquisition"

**Problem:** Network connectivity or firewall

**Solutions:**
1. Check internet connection
2. Verify firewall allows HTTPS to `*.hana.ondemand.com`
3. Check proxy settings if behind corporate firewall
4. Try accessing token URL in browser

### Token Expires Too Quickly

**Problem:** Need longer token lifetime

**Solution:**
1. In SAP Datasphere, edit OAuth client
2. Increase "Token Validity" duration
3. Note: Tokens auto-refresh 60 seconds before expiration

---

## 🔒 Security Best Practices

### DO ✅

- ✅ Store credentials in `.env` file
- ✅ Add `.env` to `.gitignore`
- ✅ Use environment variables in production
- ✅ Rotate Client Secret periodically
- ✅ Use different OAuth clients for dev/prod
- ✅ Monitor OAuth client usage in SAP Datasphere
- ✅ Set appropriate scopes (least privilege)

### DON'T ❌

- ❌ Commit `.env` file to Git
- ❌ Share Client Secret via email/chat
- ❌ Use production credentials in development
- ❌ Store credentials in command-line arguments
- ❌ Log credentials in application logs
- ❌ Hard-code credentials in source code

---

## 📚 Additional Resources

- [SAP Datasphere OAuth Documentation](https://help.sap.com/docs/SAP_DATASPHERE/9f804b8efa8043539289f42f372c4862/df7bbca2b73f4418881eeca39b9e0a3d.html)
- [OAuth 2.0 Client Credentials Flow](https://datatracker.ietf.org/doc/html/rfc6749#section-4.4)
- [MCP Protocol Specification](https://modelcontextprotocol.io/specification/2025-03-26)

---

## 🆘 Getting Help

If you encounter issues:

1. Check the troubleshooting section above
2. Review logs in `mcp_server.log`
3. Verify configuration with test scripts
4. Open an issue on [GitHub](https://github.com/MarioDeFelipe/sap-datasphere-mcp/issues)

---

**Last Updated:** 2025-10-29
**Version:** 1.0.0
**Status:** Production Ready
