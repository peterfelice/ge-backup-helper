#!/bin/bash
# Script to update the agent-cli executable in the release folder

SOURCE_FILE="agent_cli.py"
RELEASE_DIR="release"
TARGET_FILE="${RELEASE_DIR}/agent-cli"

# Ensure release directory exists
mkdir -p "${RELEASE_DIR}"

# Copy source to target (without .py extension)
cp "${SOURCE_FILE}" "${TARGET_FILE}"

# Make it executable
chmod +x "${TARGET_FILE}"

echo "Successfully updated ${TARGET_FILE} from ${SOURCE_FILE}"
