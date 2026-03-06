#!/usr/bin/env python3
"""
Gemini Agent Manager CLI
A tool to manage Discovery Engine agents, supporting backup, restore, and basic CRUD operations.
"""
import argparse
import subprocess
import json
import os
import sys
from datetime import datetime

def get_access_token():
    """
    Retrieves the Google Cloud access token using the gcloud CLI.
    Requires Google Cloud SDK to be installed and authenticated.
    """
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to get gcloud access token. Ensure you are logged in (gcloud auth login).", file=sys.stderr)
        if e.stderr:
            print(f"Details: {e.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: 'gcloud' command not found. Please install the Google Cloud SDK.", file=sys.stderr)
        sys.exit(1)

def load_config(env_file="agent-config.env"):
    """
    Loads configuration from an environment file or system environment variables.
    Provides defaults for certain keys.
    """
    config = {
        "LOCATION": "global",
        "COLLECTION_ID": "default_collection",
        "ASSISTANT_ID": "default_assistant",
        "API_VERSION": "v1alpha"
    }
    
    # Try to load from file first
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        config[key.strip()] = value.strip().strip('"')
    
    # Merge with system environment variables
    # Only keys we care about
    env_keys = ["PROJECT_ID", "LOCATION", "COLLECTION_ID", "ENGINE_ID", "ASSISTANT_ID", "API_VERSION"]
    for key in env_keys:
        env_val = os.environ.get(key)
        if env_val:
            config[key] = env_val
    
    return config

def run_curl(method, url, access_token, data_file=None, output_file=None, debug=False, silent=False):
    """
    Executes a curl command against the Discovery Engine API.
    
    Args:
        method: HTTP method (GET, POST, PATCH, DELETE)
        url: The full API endpoint
        access_token: Authentication token
        data_file: Path to a JSON file to send in the request body
        output_file: Path to save the response body to (disables header capture)
        debug: If True, prints the full curl command and raw response
        silent: If True, suppresses error printing to stderr
        
    Returns:
        (success: bool, response_body: str)
    """
    # Build core curl command
    # -s: Silent mode (no progress bar)
    # -i: Include protocol response headers in the output (unless writing to output_file)
    cmd = [
        "curl", "-s", "-X", method,
        "-H", f"Authorization: Bearer {access_token}",
        "-H", "Content-Type: application/json",
        url
    ]
    
    # If we aren't writing directly to a file, we want to see the headers to check status
    if not output_file:
        cmd.insert(2, "-i")

    if data_file:
        cmd += ["--data", f"@{data_file}"]
    
    if output_file:
        cmd += ["-o", output_file]

    if debug:
        print(f"\n[DEBUG] API Request: {method} {url}", file=sys.stderr)
        if data_file:
            print(f"[DEBUG] Data file: {data_file}", file=sys.stderr)

    # Execute the command
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if debug and result.stderr:
        print(f"[DEBUG] Curl Stderr: {result.stderr.strip()}", file=sys.stderr)

    if result.returncode != 0:
        if not silent:
            print(f"Error: Curl command execution failed. {result.stderr}", file=sys.stderr)
        return False, result.stderr
    
    # Handle the response
    if output_file:
        # Response body was saved to a file, we assume success of the curl command itself
        return True, ""

    # Split headers from body (curl -i separates them with a double newline)
    raw_output = result.stdout
    if "\r\n\r\n" in raw_output:
        headers, body = raw_output.split("\r\n\r\n", 1)
    elif "\n\n" in raw_output:
        headers, body = raw_output.split("\n\n", 1)
    else:
        headers, body = raw_output, ""

    if debug:
        print(f"[DEBUG] Response Headers:\n{headers.strip()}", file=sys.stderr)
        if body.strip() and len(body) < 1000: # Don't flood terminal with giant JSON
            print(f"[DEBUG] Response Body: {body.strip()}", file=sys.stderr)

    # Simple status code check from the first line of headers
    # Example: HTTP/1.1 200 OK
    status_line = headers.splitlines()[0] if headers else ""
    is_success = any(code in status_line for code in ["200", "201", "204"])

    if not is_success:
        if not silent:
            print(f"API Error: {status_line}", file=sys.stderr)
            if body.strip():
                print(body.strip(), file=sys.stderr)
        return False, body

    # For non-GET requests, we optionally print the body to stdout for user visibility
    if not silent and method != "GET" and body.strip():
        print(body)
    
    return True, body

def confirm_action(config, command, skip_confirmation=False):
    """
    Displays the current configuration and asks the user for confirmation.
    """
    if skip_confirmation:
        return True

    print("\n" + "="*50)
    print(" ACTION CONFIRMATION ".center(50, "="))
    print("="*50)
    print(f"COMMAND to execute: {command}")
    print("-" * 50)
    print(f"{'CONFIGURATION KEY':<20} | {'VALUE'}")
    print("-" * 50)
    
    display_keys = ["PROJECT_ID", "LOCATION", "COLLECTION_ID", "ENGINE_ID", "ASSISTANT_ID", "API_VERSION"]
    for key in display_keys:
        val = config.get(key, "NOT SET")
        print(f"{key:<20} | {val}")
    
    print("="*50)
    
    try:
        response = input("\nProceed with this configuration? (y/N): ").strip().lower()
        return response == 'y'
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)

def get_agents_list(config, token, debug=False, silent=True, user_only=True):
    """Fetches the list of agents and optionally filters for user-created agents."""
    api_url = f"{config['BASE_URL']}/agents"
    api_success, response_body = run_curl("GET", api_url, token, debug=debug, silent=silent)
    
    if not api_success:
        return None, "Failed to retrieve agent list."

    try:
        data = json.loads(response_body)
        agents = data.get("agents", [])
        
        if user_only:
            agents = [a for a in agents if "lowCodeAgentDefinition" in a]
            
        return agents, None
    except json.JSONDecodeError:
        return None, "Failed to parse API response as JSON."

def download_agent(config, token, agent_id, destination, is_resource_name=False, debug=False, silent=False):
    """Downloads an agent's configuration to a specified file."""
    if is_resource_name:
        api_url = f"https://discoveryengine.googleapis.com/{config['API_VERSION']}/{agent_id}"
    else:
        api_url = f"{config['BASE_URL']}/agents/{agent_id}"
        
    return run_curl("GET", api_url, token, output_file=destination, debug=debug, silent=silent)

def deploy_agent(config, token, agent_id, debug=False, silent=False):
    """Deploys an agent, taking it out of draft mode."""
    deploy_url = f"{config['BASE_URL']}/agents/{agent_id}:deploy"
    return run_curl("POST", deploy_url, token, debug=debug, silent=silent)

def update_agent(config, token, agent_id, file, debug=False, silent=False):
    """Updates an existing agent using a JSON configuration file (PATCH)."""
    update_url = f"{config['BASE_URL']}/agents/{agent_id}"
    return run_curl("PATCH", update_url, token, data_file=file, debug=debug, silent=silent)

def create_agent(config, token, agent_id, file, debug=False, silent=False):
    """Creates a new agent from a JSON file (POST)."""
    if agent_id:
        create_url = f"{config['BASE_URL']}/agents?agentId={agent_id}"
    else:
        create_url = f"{config['BASE_URL']}/agents"
    return run_curl("POST", create_url, token, data_file=file, debug=debug, silent=silent)

def handle_get(args, config, token):
    """Retrieves an agent's full configuration and saves it to a file."""
    destination = args.output or f"agent_{args.agent_id}.json"
    
    print(f"Retrieving agent configuration for: {args.agent_id}...")
    api_success, _ = download_agent(config, token, args.agent_id, destination, debug=args.debug)
    
    if api_success:
        print(f"Success: Agent configuration saved to {destination}")

def handle_save(args, config, token):
    """Updates an existing agent using a JSON configuration file (PATCH)."""
    if not os.path.exists(args.file):
        print(f"Error: Configuration file '{args.file}' not found.", file=sys.stderr)
        return

    print(f"Updating agent {args.agent_id} using {args.file}...")
    api_success, _ = update_agent(config, token, args.agent_id, args.file, debug=args.debug)
    
    if api_success:
        print(f"Success: Agent {args.agent_id} updated.")

def handle_create(args, config, token):
    """Creates a new agent. If agent_id is provided, uses it; otherwise, ID is auto-generated."""
    if not os.path.exists(args.file):
        print(f"Error: Configuration file '{args.file}' not found.", file=sys.stderr)
        return

    if args.agent_id:
        print(f"Creating new agent with ID '{args.agent_id}' from {args.file}...")
    else:
        print(f"Creating new agent with auto-generated ID from {args.file}...")
    
    api_success, response_body = create_agent(config, token, args.agent_id, args.file, debug=args.debug)
    
    if api_success:
        print("Success: Agent created.")
        created_id = args.agent_id
        if not created_id:
            try:
                data = json.loads(response_body)
                new_name = data.get("name", "Unknown")
                created_id = new_name.split("/")[-1]
                print(f"Created Agent Resource: {new_name}")
            except (json.JSONDecodeError, IndexError):
                pass
        
        # Check for auto-deploy
        if getattr(args, "deploy", False) and created_id:
            print(f"Auto-deploying agent {created_id}...")
            deploy_agent(config, token, created_id, debug=args.debug)

def handle_list(args, config, token):
    """Lists agents associated with the configured assistant."""
    print("Listing agents...")
    
    show_all = getattr(args, "all", False)
    agents, error = get_agents_list(config, token, debug=args.debug, silent=True, user_only=not show_all)
    
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return

    if not agents:
        msg = "No agents found." if show_all else "No user-created agents found. Use --all to see system agents."
        print(msg)
        return

    if args.verbose:
        print(json.dumps({"agents": agents}, indent=2))
        return

    # Print a clean, formatted table
    print(f"\n{'AGENT ID':<40} {'DISPLAY NAME'}")
    print("-" * 75)
    for agent in agents:
        # Name format: 'projects/.../locations/.../agents/ID'
        resource_name = agent.get("name", "")
        agent_id = resource_name.split("/")[-1] if "/" in resource_name else "N/A"
        display_name = agent.get("displayName", "Unnamed")
        print(f"{agent_id:<40} {display_name}")
    print("-" * 75 + "\n")

def handle_backup_all(args, config, token):
    """Downloads all user-created agents into a timestamped directory."""
    print("Fetching agent list for backup...")
    
    agents, error = get_agents_list(config, token, debug=args.debug, silent=True, user_only=True)
    
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return

    if not agents:
        print("No user-created agents found to backup.")
        return

    # Create timestamped directory with Engine ID to identify the source
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    engine_id = config.get("ENGINE_ID", "unknown")
    backup_dir = f"backup_{engine_id}_{timestamp}"
    
    os.makedirs(backup_dir, exist_ok=True)
    print(f"Created backup directory: {backup_dir}")

    count_backups = 0
    errors = []

    for agent in agents:
        resource_name = agent.get("name", "")
        agent_id = resource_name.split("/")[-1] if "/" in resource_name else "Unknown"
        display_name = agent.get("displayName", "Unnamed").replace(" ", "_").replace("/", "-")
        
        # Format: ID_DisplayName_Timestamp.json
        filename = f"{agent_id}_{display_name}_{timestamp}.json"
        filepath = os.path.join(backup_dir, filename)
        
        print(f"  Backing up: {agent_id} ({agent.get('displayName', 'N/A')})...")
        
        ok, _ = download_agent(config, token, resource_name, filepath, is_resource_name=True, debug=args.debug, silent=True)
        
        if ok:
            count_backups += 1
        else:
            errors.append(f"Agent {agent_id} ({agent.get('displayName', 'N/A')})")

    print(f"\nBackup complete. Successfully saved {count_backups} agents to {backup_dir}.")
    
    if errors:
        print("\n[!] ERRORS ENCOUNTERED FOR:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)

def handle_restore_all(args, config, token):
    """Uploads agent JSON files from a directory to the configured assistant."""
    if not os.path.isdir(args.directory):
        print(f"Error: Resource directory '{args.directory}' not found.", file=sys.stderr)
        return

    print(f"Scanning '{args.directory}' for agent configurations...")
    
    # We look for all .json files. Filenames are typically ID_DisplayName_Timestamp.json
    json_files = sorted([f for f in os.listdir(args.directory) if f.endswith(".json")])
    
    if not json_files:
        print("No JSON configurations found in the directory.")
        return

    print(f"Found {len(json_files)} potential agent backups. Starting restore...")
    
    count_restores = 0
    errors = []

    for filename in json_files:
        filepath = os.path.join(args.directory, filename)
        
        # Extract Agent ID (assumed to be before the first underscore)
        agent_id = filename.split("_")[0] if "_" in filename else filename.replace(".json", "")
        
        print(f"Restoring: {agent_id}...")
        
        # 1. Attempt to update existing agent (PATCH)
        api_success, response_body = update_agent(config, token, agent_id, filepath, debug=args.debug, silent=True)
        
        # 2. If PATCH fails and --create is set, attempt to create new (POST)
        if not api_success and getattr(args, "create", False):
            print(f"  Agent {agent_id} not found, attempting recreation...")
            api_success, response_body = create_agent(config, token, agent_id, filepath, debug=args.debug, silent=True)

        if api_success:
            count_restores += 1
            print(f"  Successfully restored {agent_id}")
            
            # Auto-deploy if requested
            if getattr(args, "deploy", False):
                print(f"  Deploying {agent_id}...")
                deploy_agent(config, token, agent_id, debug=args.debug, silent=True)
        else:
            errors.append(f"{agent_id} from {filename} (Error: {response_body.strip()})")

    print(f"\nRestore complete. Successfully restored {count_restores} of {len(json_files)} agents.")
    
    if errors:
        print("\n[!] ERRORS ENCOUNTERED FOR:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)

def handle_deploy(args, config, token):
    """Deploys (publishes) an agent, making it live and taking it out of draft mode."""
    print(f"Deploying agent {args.agent_id}...")
    api_success, _ = deploy_agent(config, token, args.agent_id, debug=args.debug)
    
    if api_success:
        print(f"Success: Agent {args.agent_id} deployed.")
    else:
        print(f"Error: Failed to deploy agent {args.agent_id}.", file=sys.stderr)

def handle_delete(args, config, token):
    """Deletes a specific agent after user confirmation."""
    agent_id = args.agent_id
    print(f"\n[!] WARNING: You are about to DELETE agent: {agent_id}")
    print("This operation is permanent and cannot be undone.")
    
    confirmation = input(f"To confirm, please re-type the agent ID '{agent_id}': ").strip()
    
    if confirmation != agent_id:
        print("Error: Confirmation ID mismatch. Deletion cancelled.", file=sys.stderr)
        return

    api_url = f"{config['BASE_URL']}/agents/{agent_id}"
    print(f"Deleting agent {agent_id}...")
    
    api_success, _ = run_curl("DELETE", api_url, token, debug=args.debug)
    
    if api_success:
        print(f"Success: Agent {agent_id} deleted.")
    else:
        print(f"Error: Failed to delete agent {agent_id}.", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(
        description="Gemini Agent Manager - A CLI tool for Discovery Engine agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all user-created agents
  python3 agent_cli.py list
  
  # Create a backup of all agents
  python3 agent_cli.py backup-all
  
  # Restore agents from a backup folder (recreating if missing)
  python3 agent_cli.py restore-all ./backup_folder --create
  
  # Delete a specific agent
  python3 agent_cli.py delete my-agent-id
"""
    )
    parser.add_argument("--debug", action="store_true", help="Print debug information (curl commands/responses)")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--project-id", help="Google Cloud Project ID")
    parser.add_argument("--location", help="Google Cloud Location (default: global)")
    parser.add_argument("--collection-id", help="Discovery Engine Collection ID (default: default_collection)")
    parser.add_argument("--engine-id", help="Discovery Engine ID")
    parser.add_argument("--assistant-id", help="Discovery Engine Assistant ID (default: default_assistant)")
    parser.add_argument("--api-version", help="Discovery Engine API Version (default: v1alpha)")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: get
    get_p = subparsers.add_parser("get", help="Download an agent configuration to a file")
    get_p.add_argument("agent_id", help="ID of the agent to retrieve")
    get_p.add_argument("--output", "-o", help="Output filename (default: agent_<id>.json)")

    # Command: save
    save_p = subparsers.add_parser("save", help="Update an existing agent from a JSON file")
    save_p.add_argument("file", help="Path to the source JSON file")
    save_p.add_argument("agent_id", help="ID of the agent to update")

    # Command: create
    create_p = subparsers.add_parser("create", help="Create a new agent from a JSON file")
    create_p.add_argument("file", help="Path to the source JSON file")
    create_p.add_argument("agent_id", nargs="?", help="Optional custom ID (auto-generated if omitted)")
    create_p.add_argument("--deploy", action="store_true", help="Deploy the agent immediately after creation")

    # Command: list
    list_p = subparsers.add_parser("list", help="List all available agents")
    list_p.add_argument("--verbose", "-v", action="store_true", help="Show full API response for each agent")
    list_p.add_argument("--all", "-a", action="store_true", help="Include system-managed agents in the list")

    # Command: backup-all
    subparsers.add_parser("backup-all", help="Backup all user-created agents to a timestamped folder")

    # Command: restore-all
    rest_p = subparsers.add_parser("restore-all", help="Restore agents from a folder to the assistant")
    rest_p.add_argument("directory", help="Path to the directory containing agent .json files")
    rest_p.add_argument("--create", "-c", action="store_true", help="Recreate agents if they don't exist in the destination (upsert)")
    rest_p.add_argument("--deploy", action="store_true", help="Deploy each agent after successful update/creation")

    # Command: delete
    del_p = subparsers.add_parser("delete", help="Delete a specific agent (requires confirmation)")
    del_p.add_argument("agent_id", help="ID of the agent to delete")

    # Command: deploy
    deploy_p = subparsers.add_parser("deploy", help="Deploy (publish) an agent to take it out of draft mode")
    deploy_p.add_argument("agent_id", help="ID of the agent to deploy")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Core CLI Flow
    config = load_config()
    
    # Override with CLI arguments
    if args.project_id: config["PROJECT_ID"] = args.project_id
    if args.location: config["LOCATION"] = args.location
    if args.collection_id: config["COLLECTION_ID"] = args.collection_id
    if args.engine_id: config["ENGINE_ID"] = args.engine_id
    if args.assistant_id: config["ASSISTANT_ID"] = args.assistant_id
    if args.api_version: config["API_VERSION"] = args.api_version

    # Validate required keys before constructing URL
    required_keys = ["PROJECT_ID", "ENGINE_ID"]
    missing = [k for k in required_keys if k not in config]
    if missing:
        print(f"Error: Missing required configuration keys: {', '.join(missing)}", file=sys.stderr)
        print("Provide them via flags (e.g., --project-id), environment variables, or 'agent-config.env'.", file=sys.stderr)
        sys.exit(1)

    # Construct the Discovery Engine Base URL
    # Format: https://discoveryengine.googleapis.com/{version}/projects/{project}/locations/{loc}/collections/{coll}/engines/{eng}/assistants/{asst}
    base_template = (
        "https://discoveryengine.googleapis.com/{API_VERSION}/projects/{PROJECT_ID}/"
        "locations/{LOCATION}/collections/{COLLECTION_ID}/engines/{ENGINE_ID}/assistants/{ASSISTANT_ID}"
    )
    config["BASE_URL"] = base_template.format(**config)

    # Prompt for confirmation before proceeding
    if not confirm_action(config, args.command, skip_confirmation=args.yes):
        print("Aborting operation.")
        sys.exit(0)

    token = get_access_token()

    # Route to handler
    handlers = {
        "get": handle_get,
        "save": handle_save,
        "create": handle_create,
        "list": handle_list,
        "backup-all": handle_backup_all,
        "restore-all": handle_restore_all,
        "delete": handle_delete,
        "deploy": handle_deploy
    }
    
    handler = handlers.get(args.command)
    if handler:
        handler(args, config, token)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
