import unittest
from unittest.mock import patch, MagicMock, mock_open, ANY
import json
import io
import sys
import os
from datetime import datetime

# Import the CLI functions
# Note: Since agent_cli.py doesn't have a __init__.py, we'll ensure it's in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_cli

class TestAgentCLI(unittest.TestCase):

    def setUp(self):
        self.config = {
            "PROJECT_ID": "test-project",
            "LOCATION": "us-central1",
            "COLLECTION_ID": "default_collection",
            "ENGINE_ID": "test-engine",
            "ASSISTANT_ID": "default_assistant",
            "API_VERSION": "v1alpha",
            "BASE_URL": "https://discoveryengine.googleapis.com/v1alpha/projects/test-project/locations/us-central1/collections/default_collection/engines/test-engine/assistants/default_assistant"
        }
        self.token = "test-token"

    @patch('subprocess.run')
    def test_get_access_token_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="test-token\n", returncode=0)
        token = agent_cli.get_access_token()
        self.assertEqual(token, "test-token")

    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data="PROJECT_ID=test-p\nLOCATION=us\nAPI_VERSION=v1\nCOLLECTION_ID=c\nENGINE_ID=e\nASSISTANT_ID=a")
    def test_load_config(self, mock_file, mock_exists):
        mock_exists.return_value = True
        config = agent_cli.load_config("dummy.env")
        self.assertEqual(config["PROJECT_ID"], "test-p")

    @patch('subprocess.run')
    def test_run_curl_success(self, mock_run):
        # Mock a successful API response with headers and body
        mock_stdout = "HTTP/1.1 200 OK\r\n\r\n{\"status\": \"success\"}"
        mock_run.return_value = MagicMock(stdout=mock_stdout, returncode=0)
        
        success, body = agent_cli.run_curl("GET", "http://any", "token")
        
        self.assertTrue(success)
        self.assertEqual(json.loads(body)["status"], "success")

    @patch('agent_cli.run_curl')
    def test_handle_list_user_agents_only(self, mock_curl):
        # Mock response with mixed system and user agents
        mock_response = {
            "agents": [
                {"name": ".../agents/user1", "displayName": "User Agent", "lowCodeAgentDefinition": {}},
                {"name": ".../agents/sys1", "displayName": "System Agent", "managedAgentDefinition": {}}
            ]
        }
        mock_curl.return_value = (True, json.dumps(mock_response))
        
        args = MagicMock(debug=False, verbose=False, all=False)
        
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            agent_cli.handle_list(args, self.config, self.token)
            output = fake_out.getvalue()
            self.assertIn("user1", output)
            self.assertIn("User Agent", output)
            self.assertNotIn("sys1", output) # Should be filtered out

    @patch('os.makedirs')
    @patch('agent_cli.run_curl')
    @patch('agent_cli.datetime')
    def test_handle_backup_all(self, mock_datetime, mock_curl, mock_makedirs):
        # Mock datetime for predictable folder names
        mock_now = MagicMock()
        mock_now.strftime.return_value = "20240101_120000"
        mock_datetime.now.return_value = mock_now

        # 1. Mock list response
        list_response = {
            "agents": [
                {"name": "projects/p/locations/l/collections/c/engines/e/assistants/a/agents/agent1", 
                 "displayName": "Agent One", "lowCodeAgentDefinition": {}}
            ]
        }
        
        # 2. Mock individual agent get response (for the backup file)
        agent_response = {"id": "agent1", "data": "secret"}
        
        # Configure the mock to return list first, then agent config
        mock_curl.side_effect = [
            (True, json.dumps(list_response)), # Response for the list call
            (True, json.dumps(agent_response))  # Response for the GET agent call
        ]
        
        args = MagicMock(debug=False)
        
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            agent_cli.handle_backup_all(args, self.config, self.token)
            output = fake_out.getvalue()
            self.assertIn(f"Created backup directory: backup_{self.config['ENGINE_ID']}_20240101_120000", output)
            self.assertIn("Successfully saved 1 agents", output)
            mock_makedirs.assert_called()

    @patch('os.listdir')
    @patch('os.path.isdir')
    @patch('agent_cli.run_curl')
    def test_handle_restore_all(self, mock_curl, mock_isdir, mock_listdir):
        mock_isdir.return_value = True
        mock_listdir.return_value = ["agent1_Name_Date.json"]
        mock_curl.return_value = (True, "{}")
        
        args = MagicMock(directory="backup_dir", debug=False)
        args.deploy = False
        args.create = False
        
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            agent_cli.handle_restore_all(args, self.config, self.token)
            output = fake_out.getvalue()
            self.assertIn("Successfully restored 1 of 1 agents", output)
            # Verify it called PATCH
            mock_curl.assert_called_with("PATCH", ANY, self.token, data_file=ANY, debug=False, silent=True)

    @patch('os.listdir')
    @patch('os.path.isdir')
    @patch('agent_cli.run_curl')
    def test_handle_restore_all_with_create(self, mock_curl, mock_isdir, mock_listdir):
        mock_isdir.return_value = True
        mock_listdir.return_value = ["agent1.json"]
        # First call (PATCH) fails, second call (POST) succeeds
        mock_curl.side_effect = [
            (False, "Not Found"),
            (True, "{}")
        ]
        
        args = MagicMock(directory="backup_dir", debug=False, create=True)
        args.deploy = False
        
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            agent_cli.handle_restore_all(args, self.config, self.token)
            output = fake_out.getvalue()
            self.assertIn("Agent agent1 not found, attempting recreation...", output)
            self.assertIn("Successfully restored agent1", output)
            # Verify it called POST with query param
            mock_curl.assert_called_with("POST", f"{self.config['BASE_URL']}/agents?agentId=agent1", self.token, data_file=ANY, debug=False, silent=True)

    @patch('builtins.input')
    @patch('agent_cli.run_curl')
    def test_handle_delete_success(self, mock_curl, mock_input):
        mock_input.return_value = "agent123"
        mock_curl.return_value = (True, "")
        
        args = MagicMock(agent_id="agent123", debug=False)
        
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            agent_cli.handle_delete(args, self.config, self.token)
            output = fake_out.getvalue()
            self.assertIn("Success: Agent agent123 deleted.", output)
            mock_curl.assert_called_with("DELETE", ANY, self.token, debug=False)

    @patch('builtins.input')
    @patch('agent_cli.run_curl')
    def test_handle_delete_mismatch(self, mock_curl, mock_input):
        mock_input.return_value = "wrong_id"
        
        args = MagicMock(agent_id="agent123", debug=False)
        
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            with patch('sys.stderr', new=io.StringIO()) as fake_err:
                agent_cli.handle_delete(args, self.config, self.token)
                self.assertIn("Error: Confirmation ID mismatch. Deletion cancelled.", fake_err.getvalue())
                mock_curl.assert_not_called()

if __name__ == '__main__':
    unittest.main()
