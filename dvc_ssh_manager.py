# dvc_ssh_manager.py
#
# This script provides a set of functions to manage DVC remotes over SSH.
import os
import subprocess
import logging
import paramiko
import click
import yaml
import configparser

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def generate_ssh_keypair(path, comment="dvc-ssh-manager-key"):
    """
    Generates a new SSH keypair if one does not exist.

    Args:
        path (str): The path to the private key file.
        comment (str): The comment to add to the key.

    Returns:
        bool: True if the key was generated or already exists, False otherwise.
    """
    private_key_path = os.path.expanduser(path)
    public_key_path = f"{private_key_path}.pub"

    if os.path.exists(private_key_path):
        logging.info(f"SSH key already exists at {private_key_path}. Skipping generation.")
        return True

    logging.info(f"Generating new SSH key pair at {private_key_path}")
    try:
        command = [
            "ssh-keygen",
            "-t", "rsa",
            "-b", "4096",
            "-f", private_key_path,
            "-N", "",  # No passphrase
            "-C", comment
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        logging.info("ssh-keygen stdout: %s", result.stdout)
        logging.info("ssh-keygen stderr: %s", result.stderr)

        # Set permissions for the private key
        os.chmod(private_key_path, 0o600)
        logging.info(f"Set permissions for private key {private_key_path} to 600.")

        logging.info(f"SSH key pair generated successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logging.error("Failed to generate SSH key pair.")
        logging.error("Command: %s", " ".join(e.cmd))
        logging.error("Return code: %d", e.returncode)
        logging.error("stdout: %s", e.stdout)
        logging.error("stderr: %s", e.stderr)
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return False


def install_public_key(host, user, public_key_path, port=22, password=None):
    """
    Installs a public SSH key on a remote server.

    Args:
        host (str): The server hostname or IP address.
        user (str): The username for the SSH connection.
        public_key_path (str): The local path to the public key file.
        port (int): The SSH port on the server.
        password (str, optional): The user's password for authentication. Defaults to None.

    Returns:
        bool: True if the key was installed successfully, False otherwise.
    """
    public_key_path = os.path.expanduser(public_key_path)
    if not os.path.exists(public_key_path):
        logging.error(f"Public key file not found at {public_key_path}")
        return False

    with open(public_key_path, 'r') as f:
        public_key = f.read().strip()

    ssh = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        logging.info(f"Connecting to {user}@{host}:{port}...")
        ssh.connect(host, port, user, password=password, look_for_keys=True)

        # Ensure .ssh directory exists and has correct permissions
        ssh.exec_command("mkdir -p ~/.ssh && chmod 700 ~/.ssh")

        # Add the key to authorized_keys and set correct permissions
        command = (
            f'echo "{public_key}" >> ~/.ssh/authorized_keys && '
            f'chmod 600 ~/.ssh/authorized_keys && '
            f'sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys'
        )
        stdin, stdout, stderr = ssh.exec_command(command)

        exit_status = stdout.channel.recv_exit_status()
        if exit_status == 0:
            logging.info("Public key installed successfully.")
            return True
        else:
            error_message = stderr.read().decode().strip()
            logging.error(f"Failed to install public key. Exit status: {exit_status}")
            logging.error(f"Server error message: {error_message}")
            return False

    except Exception as e:
        logging.error(f"An error occurred while installing the public key: {e}")
        return False
    finally:
        if ssh:
            ssh.close()


def configure_dvc_remote(remote_name, ssh_url, ssh_key_path, no_scm=False):
    """
    Configures a DVC remote with SSH authentication.

    Args:
        remote_name (str): The name for the DVC remote.
        ssh_url (str): The SSH URL for the remote storage (e.g., user@host:/path).
        ssh_key_path (str): The path to the SSH private key.
        no_scm (bool): If True, initialize DVC without Git.

    Returns:
        bool: True if the remote was configured successfully, False otherwise.
    """
    ssh_key_path = os.path.expanduser(ssh_key_path)
    if not os.path.exists(ssh_key_path):
        logging.error(f"SSH private key not found at {ssh_key_path}. Cannot configure remote.")
        return False

    try:
        # 1. Check for Git repository if not in --no-scm mode
        if not no_scm and not os.path.isdir(".git"):
            logging.error("This is not a Git repository. Please run 'git init' or use the --no-scm flag.")
            return False

        # 2. Initialize DVC if not already initialized
        if not os.path.isdir(".dvc"):
            logging.info("Initializing DVC repository.")
            init_command = ["dvc", "init"]
            if no_scm:
                init_command.append("--no-scm")
            subprocess.run(init_command, check=True, capture_output=True)

        # 3. Add the remote
        logging.info(f"Adding DVC remote '{remote_name}' at '{ssh_url}'.")
        subprocess.run(
            ["dvc", "remote", "add", remote_name, ssh_url],
            check=True, capture_output=True
        )

        # 4. Configure the remote to use the specified SSH key by writing to .dvc/config.local
        logging.info(f"Configuring remote to use SSH key: {ssh_key_path}")
        config_path = os.path.join(".dvc", "config.local")
        config = configparser.ConfigParser()
        if os.path.exists(config_path):
            config.read(config_path)

        remote_section = f'remote "{remote_name}"'
        if not config.has_section(remote_section):
            config.add_section(remote_section)

        config.set(remote_section, "keyfile", ssh_key_path)

        with open(config_path, "w") as f:
            config.write(f)

        logging.info("DVC remote configured successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logging.error("Failed to configure DVC remote.")
        logging.error("Command: %s", " ".join(e.cmd))
        logging.error("Return code: %d", e.returncode)
        logging.error("stdout: %s", e.stdout)
        logging.error("stderr: %s", e.stderr)
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return False


def dvc_add_and_push(data_paths, remote_name):
    """
    Adds data to DVC and pushes it to a remote.

    Args:
        data_paths (list): A list of file or directory paths to add to DVC.
        remote_name (str): The name of the DVC remote to push to.

    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        logging.info(f"Adding data to DVC: {data_paths}")
        subprocess.run(["dvc", "add"] + data_paths, check=True, capture_output=True)

        logging.info(f"Pushing data to remote '{remote_name}'.")
        subprocess.run(["dvc", "push", "-r", remote_name], check=True, capture_output=True)

        logging.info("Data added and pushed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logging.error("DVC add or push failed.")
        logging.error("Command: %s", " ".join(e.cmd))
        logging.error("Return code: %d", e.returncode)
        logging.error("stdout: %s", e.stdout)
        logging.error("stderr: %s", e.stderr)
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return False

def dvc_pull(remote_name, target_paths=None):
    """
    Pulls data from a DVC remote.

    Args:
        remote_name (str): The name of the DVC remote to pull from.
        target_paths (list, optional): Specific files or directories to pull.
                                      If None, pulls all tracked data.

    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        command = ["dvc", "pull", "-r", remote_name]
        if target_paths:
            command.extend(target_paths)

        logging.info(f"Pulling data from remote '{remote_name}'.")
        subprocess.run(command, check=True, capture_output=True)

        logging.info("Data pulled successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logging.error("DVC pull failed.")
        logging.error("Command: %s", " ".join(e.cmd))
        logging.error("Return code: %d", e.returncode)
        logging.error("stdout: %s", e.stdout)
        logging.error("stderr: %s", e.stderr)
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        return False


def load_config(config_path='config.yaml'):
    """Loads configuration from a YAML file."""
    if not os.path.exists(config_path):
        logging.warning(f"Configuration file not found at {config_path}. Using defaults.")
        return {}
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """A CLI tool to manage DVC remotes over SSH."""
    ctx.ensure_object(dict)
    if ctx.invoked_subcommand is None:
        config = load_config()
        if not config:
            click.echo("Could not load config.yaml. Please run the setup command manually.")
            return
        password = click.prompt("Please enter the SSH password for the remote server", hide_input=True)
        run_all_steps(config, password)
    else:
        ctx.obj['config'] = load_config()


@cli.command()
@click.option('--host', help="SSH host.")
@click.option('--user', help="SSH user.")
@click.option('--port', type=int, help="SSH port.")
@click.option('--password', help="SSH password (not recommended, use keys).", prompt=True, hide_input=True, confirmation_prompt=False)
@click.option('--remote-name', help="DVC remote name.")
@click.option('--remote-path', help="Path on the remote for DVC storage.")
@click.option('--private-key-path', help="Path to the private SSH key.")
@click.option('--no-scm', is_flag=True, help="Initialize DVC without a Git repository.")
@click.pass_context
def setup(ctx, host, user, port, password, remote_name, remote_path, private_key_path, no_scm):
    """Generates keys, installs them, and configures a DVC remote."""
    config = ctx.obj['config']
    host = host or config.get('ssh', {}).get('host')
    user = user or config.get('ssh', {}).get('user')
    port = port or config.get('ssh', {}).get('port', 22)
    remote_name = remote_name or config.get('dvc', {}).get('remote_name')
    remote_path = remote_path or config.get('dvc', {}).get('remote_path')
    private_key_path = private_key_path or config.get('keys', {}).get('private_key_path')
    public_key_path = f"{private_key_path}.pub"

    if not host:
        logging.error("Missing required parameter: --host. Provide it via command line or config.yaml.")
        return
    if not user:
        logging.error("Missing required parameter: --user. Provide it via command line or config.yaml.")
        return
    if not remote_name:
        logging.error("Missing required parameter: --remote-name. Provide it via command line or config.yaml.")
        return
    if not remote_path:
        logging.error("Missing required parameter: --remote-path. Provide it via command line or config.yaml.")
        return
    if not private_key_path:
        logging.error("Missing required parameter: --private-key-path. Provide it via command line or config.yaml.")
        return

    # 1. Generate SSH key pair
    if not generate_ssh_keypair(private_key_path):
        return

    # 2. Install public key
    if not install_public_key(host, user, public_key_path, port, password):
        logging.error("Could not install public key. Aborting setup.")
        return

    # 3. Configure DVC remote
    ssh_url = f"{user}@{host}:{remote_path}"
    configure_dvc_remote(remote_name, ssh_url, private_key_path, no_scm)

@cli.command()
@click.argument('paths', nargs=-1, required=True)
@click.option('--remote', '-r', 'remote_name', help="The DVC remote to push to.")
@click.pass_context
def push(ctx, paths, remote_name):
    """Adds and pushes data to a DVC remote."""
    config = ctx.obj['config']
    remote_name = remote_name or config.get('dvc', {}).get('remote_name')
    if not remote_name:
        logging.error("Remote name not specified. Use --remote or set it in config.yaml.")
        return

    dvc_add_and_push(list(paths), remote_name)

@cli.command()
@click.argument('paths', nargs=-1)
@click.option('--remote', '-r', 'remote_name', help="The DVC remote to pull from.")
@click.pass_context
def pull(ctx, paths, remote_name):
    """Pulls data from a DVC remote."""
    config = ctx.obj['config']
    remote_name = remote_name or config.get('dvc', {}).get('remote_name')
    if not remote_name:
        logging.error("Remote name not specified. Use --remote or set it in config.yaml.")
        return

    dvc_pull(remote_name, list(paths) if paths else None)


def run_all_steps(config, password, no_scm=False):
    """Runs all steps to setup DVC and push an initial file."""
    host = config.get('ssh', {}).get('host')
    user = user or config.get('ssh', {}).get('user')
    port = config.get('ssh', {}).get('port', 22)
    remote_name = config.get('dvc', {}).get('remote_name')
    remote_path = config.get('dvc', {}).get('remote_path')
    private_key_path = config.get('keys', {}).get('private_key_path')
    public_key_path = f"{private_key_path}.pub"

    if not all([host, user, remote_name, remote_path, private_key_path]):
        logging.error("Configuration is incomplete. Please fill out config.yaml.")
        return

    # 1. Generate SSH key pair
    if not generate_ssh_keypair(private_key_path):
        return

    # 2. Install public key
    if not install_public_key(host, user, public_key_path, port, password):
        logging.error("Could not install public key. Aborting.")
        return

    # 3. Configure DVC remote
    ssh_url = f"{user}@{host}:{remote_path}"
    if not configure_dvc_remote(remote_name, ssh_url, private_key_path, no_scm=no_scm):
        return

    # 4. Add and push a sample file
    if os.path.exists("data/dummy.txt"):
        logging.info("Pushing sample data file.")
        dvc_add_and_push(["data/dummy.txt"], remote_name)
    else:
        logging.warning("No sample data file found at 'data/dummy.txt'. Skipping initial push.")

    logging.info("\nSetup complete! Your DVC remote is configured and ready to use.")


if __name__ == "__main__":
    import sys
    # If run with arguments, use the CLI. Otherwise, run all steps.
    if len(sys.argv) > 1 and sys.argv[1] != '--no-scm':
        cli()
    else:
        no_scm = '--no-scm' in sys.argv
        config = load_config()
        password = click.prompt("Please enter the SSH password for the remote server", hide_input=True)
        run_all_steps(config, password, no_scm=no_scm)
