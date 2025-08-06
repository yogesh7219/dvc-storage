# Python DVC SSH Storage Manager

This project provides a Python-based tool to automate the setup and management of DVC (Data Version Control) remotes using SSH. It is designed to simplify the process of configuring secure, key-based authentication for DVC, especially in automated or team environments where managing credentials manually is cumbersome and insecure.

## Features

- **Automated SSH Key Generation**: Creates a new SSH key pair if one doesn't exist.
- **Secure Public Key Installation**: Copies the public key to a remote server's `authorized_keys` file.
- **DVC Remote Configuration**: Sets up a DVC remote to use SSH for data transfer.
- **Simplified Data Operations**: Provides wrapper functions to `dvc add`, `dvc push`, and `dvc pull`.
- **CLI Interface**: Easy-to-use command-line interface for all major functions.

## Getting Started

### Installation

1.  Clone this repository:
    ```bash
    git clone <repository-url>
    cd dvc-ssh-manager
    ```

2.  Install the required dependencies. It is recommended to do this in a virtual environment.
    ```bash
    pip install -e .
    ```

### Configuration

The tool can be configured via a `config.yaml` file in the root of the project. A sample configuration is provided:

```yaml
# Sample configuration for the DVC SSH Manager
ssh:
  host: "your_server_hostname"
  user: "your_username"
  port: 22
dvc:
  remote_name: "storage"
  remote_path: "/path/to/dvc/storage"
keys:
  private_key_path: "~/.ssh/dvc_id_rsa"
```

You can either fill out this file or provide the parameters as command-line options.

## Usage

The tool provides three main commands: `setup`, `push`, and `pull`.

### `setup`

This command automates the entire setup process:
1.  Generates an SSH key pair (if it doesn't exist).
2.  Installs the public key on the remote server.
3.  Initializes a DVC repository (if needed).
4.  Configures the DVC remote to use the SSH key.

```bash
# Using parameters from config.yaml
dvc-ssh setup --password YOUR_PASSWORD

# Overriding config with command-line options
dvc-ssh setup --host my-server --user my-user --password YOUR_PASSWORD
```

### `push`

This command adds one or more files/directories to DVC and pushes them to the configured remote.

```bash
# Create some data
mkdir data
echo "hello" > data/foo.txt

# Push the data
dvc-ssh push data/foo.txt --remote storage
```

### `pull`

This command pulls data from the DVC remote.

```bash
# Pull all data from a remote
dvc-ssh pull --remote storage

# Pull a specific file
dvc-ssh pull data/foo.txt --remote storage
```

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.
