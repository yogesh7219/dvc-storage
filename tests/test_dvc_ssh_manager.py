# tests/test_dvc_ssh_manager.py
#
# Unit tests for the DVC SSH Manager.
import unittest
import os
import stat
from unittest.mock import patch, MagicMock, call
from dvc_ssh_manager import (
    generate_ssh_keypair,
    install_public_key,
    configure_dvc_remote,
    dvc_add_and_push,
    dvc_pull
)

class TestKeyGeneration(unittest.TestCase):

    def setUp(self):
        """Set up the test environment."""
        self.test_key_path = os.path.expanduser("~/.ssh/test_dvc_key")
        self.public_key_path = f"{self.test_key_path}.pub"
        self._cleanup_keys()

    def tearDown(self):
        """Clean up the test environment."""
        self._cleanup_keys()

    def _cleanup_keys(self):
        """Remove the generated key files."""
        if os.path.exists(self.test_key_path):
            os.remove(self.test_key_path)
        if os.path.exists(self.public_key_path):
            os.remove(self.public_key_path)

    def test_generate_new_keypair(self):
        """Test that a new key pair is generated successfully."""
        # Ensure keys do not exist initially
        self.assertFalse(os.path.exists(self.test_key_path))
        self.assertFalse(os.path.exists(self.public_key_path))

        # Generate the key pair
        result = generate_ssh_keypair(self.test_key_path, "test-comment")
        self.assertTrue(result)

        # Verify that the private and public keys were created
        self.assertTrue(os.path.exists(self.test_key_path))
        self.assertTrue(os.path.exists(self.public_key_path))

        # Verify private key permissions
        permissions = stat.S_IMODE(os.stat(self.test_key_path).st_mode)
        self.assertEqual(permissions, 0o600)

    def test_generate_keypair_already_exists(self):
        """Test that an existing key pair is not overwritten."""
        # Create a dummy key pair first
        generate_ssh_keypair(self.test_key_path, "initial-comment")
        with open(self.public_key_path, 'r') as f:
            initial_content = f.read()

        # Attempt to generate the key pair again
        result = generate_ssh_keypair(self.test_key_path, "new-comment")
        self.assertTrue(result)

        # Verify that the key was not changed
        with open(self.public_key_path, 'r') as f:
            new_content = f.read()
        self.assertEqual(initial_content, new_content)


class TestPublicKeyInstallation(unittest.TestCase):

    def setUp(self):
        """Set up the test environment."""
        self.public_key_path = "test_key.pub"
        with open(self.public_key_path, "w") as f:
            f.write("ssh-rsa AAAA... test-comment")

    def tearDown(self):
        """Clean up the test environment."""
        if os.path.exists(self.public_key_path):
            os.remove(self.public_key_path)

    @patch('paramiko.SSHClient')
    def test_install_public_key_success(self, mock_ssh_client):
        """Test successful installation of a public key."""
        # Mock the SSHClient instance and its methods
        mock_instance = MagicMock()
        mock_ssh_client.return_value = mock_instance

        # Mock the exec_command to simulate success
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_instance.exec_command.return_value = (None, mock_stdout, None)

        # Call the function
        result = install_public_key(
            host="testhost",
            user="testuser",
            public_key_path=self.public_key_path
        )

        # Assertions
        self.assertTrue(result)
        mock_instance.connect.assert_called_once_with(
            "testhost", 22, "testuser", password=None, look_for_keys=True
        )
        self.assertEqual(mock_instance.exec_command.call_count, 2)
        mock_instance.close.assert_called_once()

    @patch('paramiko.SSHClient')
    def test_install_public_key_failure(self, mock_ssh_client):
        """Test failed installation of a public key."""
        # Mock the SSHClient instance and its methods
        mock_instance = MagicMock()
        mock_ssh_client.return_value = mock_instance

        # Mock the exec_command to simulate failure
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = 1
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b"Permission denied"
        mock_instance.exec_command.return_value = (None, mock_stdout, mock_stderr)

        # Call the function
        result = install_public_key(
            host="testhost",
            user="testuser",
            public_key_path=self.public_key_path
        )

        # Assertions
        self.assertFalse(result)
        mock_instance.connect.assert_called_once()
        mock_instance.close.assert_called_once()

    def test_install_public_key_file_not_found(self):
        """Test key installation when the public key file is not found."""
        result = install_public_key(
            host="testhost",
            user="testuser",
            public_key_path="non_existent_key.pub"
        )
        self.assertFalse(result)


class TestDvcRemoteConfiguration(unittest.TestCase):

    @patch('os.path.exists')
    @patch('subprocess.run')
    @patch('os.path.isdir')
    def test_configure_dvc_remote_no_init(self, mock_isdir, mock_run, mock_exists):
        """Test DVC remote configuration when .dvc directory does not exist."""
        mock_isdir.return_value = False
        mock_exists.return_value = True

        result = configure_dvc_remote(
            remote_name="test-remote",
            ssh_url="user@host:/path",
            ssh_key_path="~/.ssh/test_key"
        )

        self.assertTrue(result)
        mock_isdir.assert_called_once_with(".dvc")

        expected_calls = [
            call(["dvc", "init"], check=True, capture_output=True),
            call(["dvc", "remote", "add", "test-remote", "user@host:/path"], check=True, capture_output=True),
            call(["dvc", "remote", "modify", "--local", "test-remote", "keyfile", os.path.expanduser("~/.ssh/test_key")], check=True, capture_output=True)
        ]
        mock_run.assert_has_calls(expected_calls)
        self.assertEqual(mock_run.call_count, 3)

    @patch('os.path.exists')
    @patch('subprocess.run')
    @patch('os.path.isdir')
    def test_configure_dvc_remote_already_init(self, mock_isdir, mock_run, mock_exists):
        """Test DVC remote configuration when .dvc directory already exists."""
        mock_isdir.return_value = True
        mock_exists.return_value = True

        result = configure_dvc_remote(
            remote_name="test-remote",
            ssh_url="user@host:/path",
            ssh_key_path="~/.ssh/test_key"
        )

        self.assertTrue(result)
        mock_isdir.assert_called_once_with(".dvc")

        expected_calls = [
            call(["dvc", "remote", "add", "test-remote", "user@host:/path"], check=True, capture_output=True),
            call(["dvc", "remote", "modify", "--local", "test-remote", "keyfile", os.path.expanduser("~/.ssh/test_key")], check=True, capture_output=True)
        ]
        mock_run.assert_has_calls(expected_calls)
        self.assertEqual(mock_run.call_count, 2)


class TestDataOperations(unittest.TestCase):

    @patch('subprocess.run')
    def test_dvc_add_and_push_success(self, mock_run):
        """Test successful dvc add and push."""
        data_paths = ["data/file1.csv", "data/file2.csv"]
        remote_name = "my-remote"

        result = dvc_add_and_push(data_paths, remote_name)

        self.assertTrue(result)
        expected_calls = [
            call(["dvc", "add"] + data_paths, check=True, capture_output=True),
            call(["dvc", "push", "-r", remote_name], check=True, capture_output=True)
        ]
        mock_run.assert_has_calls(expected_calls)
        self.assertEqual(mock_run.call_count, 2)

    @patch('subprocess.run')
    def test_dvc_pull_success_no_targets(self, mock_run):
        """Test successful dvc pull with no specific targets."""
        remote_name = "my-remote"

        result = dvc_pull(remote_name)

        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ["dvc", "pull", "-r", remote_name],
            check=True, capture_output=True
        )

    @patch('subprocess.run')
    def test_dvc_pull_success_with_targets(self, mock_run):
        """Test successful dvc pull with specific targets."""
        remote_name = "my-remote"
        target_paths = ["data/file1.csv"]

        result = dvc_pull(remote_name, target_paths)

        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ["dvc", "pull", "-r", remote_name] + target_paths,
            check=True, capture_output=True
        )


if __name__ == '__main__':
    unittest.main()
