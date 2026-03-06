# Google Cloud Discovery Engine - Agent CLI

A command-line interface tool to manage Gemini Agents (from Vertex AI Agent Engine/Discovery Engine) via Google Cloud's REST APIs. It allows for full lifecycle management including creation, listing, deployment, backup, and restoration of your AI agents.

## Prerequisites

1.  **Python 3.7+**
2.  **Google Cloud SDK (`gcloud`)**: Must be installed and authenticated to a user account or service account that has `Discovery Engine Admin` permissions.
    *   To install: `brew install --cask google-cloud-sdk` (Mac) or visit the [Cloud SDK Install Page](https://cloud.google.com/sdk/docs/install)
    *   Authenticate by running: `gcloud auth login`
    *   Set your default project (optional but recommended): `gcloud config set project YOUR_PROJECT_ID`

## Configuration

The script requires access to several Google Cloud identifiers. You can provide these in three ways (in order of precedence):

**1. Command-Line Arguments**: e.g., `--project-id my-project`
**2. Environment Variables**: e.g., `export PROJECT_ID=my-project`
**3. `agent-config.env` File**: Place this file in the same directory as the script.

### `.env` File Example (`agent-config.env`)
```env
# Required identifying information
PROJECT_ID=my-gcp-project-id
LOCATION=global
COLLECTION_ID=default_collection
ENGINE_ID=my-engine-id
ASSISTANT_ID=default_assistant

# Optional Overrides
API_VERSION=v1alpha
```

## Installation & Standalone Usage

You can use the script directly via python, or use the provided release script to create a standalone executable binary.

```bash
# Option 1: Run directly with Python
python3 agent_cli.py list

# Option 2: Generate standalone executable
chmod +x update_release.sh
./update_release.sh
./release/agent-cli list
```

## Commands & Usage

Below is a list of all available commands and their purpose.

### Global Options
*   `--debug`: Show verbose output including the raw `curl` commands being executed.
*   `--yes`, `-y`: Skip the interactive configuration confirmation prompt.
*   `--project-id`, `--location`, `--collection-id`, `--engine-id`, `--api-version`: Override the respective configuration values.

### 1. `list`
Lists agents associated with the configured assistant.
*   **Usage**: `agent-cli list [--all] [--verbose]`
*   **Options**:
    *   `--all`: Show all system agents as well. (By default, only user-created agents are returned).
    *   `--verbose`: Output the raw JSON response.

### 2. `get`
Retrieves a specific agent's JSON configuration.
*   **Usage**: `agent-cli get <agent_id> [--output file.json]`

### 3. `save`
Updates an existing agent using a local JSON configuration file (PATCH).
*   **Usage**: `agent-cli save <agent_id> <file.json>`

### 4. `create`
Creates a new agent from a local JSON configuration file (POST).
*   **Usage**: `agent-cli create <file.json> [--agent-id ID] [--deploy]`
*   **Options**:
    *   `--agent-id`: Specify a custom ID for the new agent, otherwise GCP generates one.
    *   `--deploy`: Automatically publish the agent immediately after creation (takes it out of draft mode).

### 5. `deploy`
Transitions an agent from "Draft" mode to "Published" mode, making it live.
*   **Usage**: `agent-cli deploy <agent_id>`

### 6. `backup-all`
Downloads all user-created agents into a newly created timestamped directory.
*   **Usage**: `agent-cli backup-all`

### 7. `restore-all`
Uploads all agent JSON files from a specified local directory to Google Cloud.
*   **Usage**: `agent-cli restore-all <directory_path> [--create] [--deploy]`
*   **Options**:
    *   `--create`: If an agent in the backup doesn't exist remotely, attempt to create it.
    *   `--deploy`: Automatically transition restored/created agents out of draft mode into published mode.

### 8. `delete`
Deletes a specific agent permanently.
*   **Usage**: `agent-cli delete <agent_id>`
