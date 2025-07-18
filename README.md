# Open WebUI VM Management & Upgrade Tool (Ubuntu + ESXi)

This project provides an OpenAPI-compatible tool server to extend Open WebUI's capabilities, allowing your chatbot to intelligently manage and upgrade Ubuntu Linux Virtual Machines running on your VMware ESXi 6 (or vCenter) hypervisor.

The tool server can:
1.  **Discover Ubuntu VMs by Name:** Connect to your ESXi/vCenter to find a specific VM by its name and retrieve its current IP address.
2.  **List Powered-On VMs:** List all VMs that are currently powered on, including their names, IPs, guest OS, and power state.
3.  **Check for Upgrades:** Connect to a specified Ubuntu VM via SSH to check for available software upgrades using `apt`.
4.  **Apply Upgrades:** Apply all pending software upgrades on a specified Ubuntu VM via SSH using `apt`.

This enables a conversational flow where you can simply tell your chatbot, "Hey, update my OpenVPN server," and it will handle the discovery and update process automatically.

## Table of Contents

-   [Features](#features)
-   [Prerequisites](#prerequisites)
-   [Setup](#setup)
    -   [1. Project Structure](#1-project-structure)
    -   [2. Create a Virtual Environment & Install Dependencies](#2-create-a-virtual-environment--install-dependencies)
    -   [3. SSH Key Setup (for VM Access)](#3-ssh-key-setup-for-vm-access)
    -   [4. Run the Tool Server](#4-run-the-tool-server)
-   [Open WebUI Integration](#open-webui-integration)
-   [How to Use with Open WebUI Chatbot](#how-to-use-with-openwebui-chatbot)
-   [Important Considerations & Security](#important-considerations--security)
-   [Troubleshooting](#troubleshooting)

## Features

*   **VM Discovery:** Locate Ubuntu VMs by name on your ESXi/vCenter server and retrieve their IP addresses automatically.
*   **List Powered-On VMs:** Get a list of all powered-on VMs, including their names, IPs, guest OS, and power state.
*   **Intelligent Upgrade Check:** Query specific Ubuntu VMs for available `apt` upgrades.
*   **Automated Upgrade Application:** Initiate `apt upgrade` remotely on your Ubuntu VMs.
*   **Seamless Chatbot Integration:** Leverage Open WebUI's tool calling feature for natural language commands.
*   **Ubuntu-Specific:** Optimized for Ubuntu Server VMs.

## Prerequisites

Before you begin, ensure you have the following:

### On the machine running the Tool Server:
*   **Python 3.9+**: Installed and available in your PATH.
*   **`pip`**: Python package installer (comes with Python).
*   **`git`**: For cloning the repository (optional, you can just download the files).
*   **Network Access**: The machine running this tool server must have network connectivity to:
    *   Your ESXi host/vCenter Server (typically port 443).
    *   Your Ubuntu VMs (typically SSH port 22).

### On your Ubuntu Server VMs:
*   **SSH Access**: An SSH user account with `sudo` privileges configured (e.g., `sudo apt update`, `sudo apt upgrade`).
*   **VMware Tools**: Must be installed and running inside each Ubuntu VM you wish to manage. This is crucial for ESXi/vCenter to report the VM's IP address.
*   **`apt` package manager**: Standard on Ubuntu.

### On your ESXi 6 Host or vCenter Server:
*   **Host IP Address**: The IP address or hostname of your ESXi host or vCenter Server.
*   **Credentials**: A username and password for ESXi/vCenter with sufficient permissions (at least **Read-only** access, propagated to VMs, to retrieve VM names and IP addresses).

### Open WebUI & Ollama:
*   **Open WebUI**: Already up and running (e.g., via Docker).
*   **Ollama**: Running and integrated with Open WebUI.
*   **LLM with Native Function Calling**: Your chosen Large Language Model in Open WebUI should support native function calling (ReACT-style). Models like `GPT-4o`, `Claude 3`, or `Mistral` are good choices.

## Setup

Follow these steps to get your VM Management Tool Server up and running.

### 1. Project Structure

Ensure you have your project directory containing the following files:

*   `vm_update_tool_server.py`
*   `requirements.txt`
*   `config.json` (see `example-config.json` for format)
*   `openai.json` (see `example-openai.json` for format)

### 2. Create a Virtual Environment & Install Dependencies

It's highly recommended to use a Python virtual environment to manage dependencies for this project.

```bash
# Navigate to your project directory
cd /path/to/your/vm-tool-server

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install the required Python packages
pip install -r requirements.txt
```

### 3. SSH Key Setup (for VM Access)

The tool server uses SSH keys for secure, password-less access to your Ubuntu VMs.

1.  **Generate an SSH Key Pair** (if you don't have one dedicated for this purpose on the machine running the tool server):
    ```bash
    ssh-keygen -t rsa -b 4096 -f ~/.ssh/openwebui_vm_key
    ```
    *   **Press Enter** when prompted for a passphrase if you want fully automated, non-interactive updates.
    *   **⚠️ Security Warning**: An SSH key without a passphrase provides direct access to your VMs. Ensure the machine running this tool server is secure and the key file (`~/.ssh/openwebui_vm_key`) has strict permissions (`chmod 600 ~/.ssh/openwebui_vm_key`).

2.  **Copy the Public Key to your Ubuntu VMs**:
    Replace `user` with your VM's SSH username and `your_ubuntu_vm_ip` with the VM's IP address.
    ```bash
    ssh-copy-id -i ~/.ssh/openwebui_vm_key.pub user@your_ubuntu_vm_ip
    ```
    You will be prompted for the `user`'s password on the VM once to install the key. Repeat for all Ubuntu VMs you wish to manage.

### 4. Run the Tool Server

With the virtual environment active, start the FastAPI server:

```bash
uvicorn vm_update_tool_server:app --host 0.0.0.0 --port 8000
```

Or use the provided VS Code debug configuration (see `.vscode/launch.json`):

- The server will use the `TOOL_SERVER_HOST` environment variable for the host IP.

*   `--host 0.0.0.0`: Makes the server accessible from any network interface.
*   `--port 8000`: Runs the server on port 8000.
*   For development, you can add `--reload` to automatically restart on code changes. Remove it for production.
*   **Firewall**: Ensure your firewall allows incoming connections to port 8000 on the machine running the tool server.

The server will now be running, typically accessible at `http://[YourServerIP]:8000`. You can test it by navigating to `http://[YourServerIP]:8000/docs` in your web browser to see the OpenAPI (Swagger UI) documentation.

## Open WebUI Integration

Now, connect your running tool server to Open WebUI. Requests from Global Tool Servers originate from the Open WebUI *backend*, which is usually necessary for reaching internal VMs or hypervisors.

1.  **Open Open WebUI**: Go to your Open WebUI instance in your web browser.
2.  **Access Admin Settings**: Navigate to the 🛠️ **Admin Settings** (usually bottom-left) > **Tools**.
3.  **Add New Tool Server**: Click the "Add Tool Server" button.
4.  **Enter the URL**:
    *   If Open WebUI is in Docker and the tool server is on the *host machine*: `http://host.docker.internal:8000`
    *   If Open WebUI and the tool server are on the *same machine (not Docker)*: `http://127.0.0.1:8000`
    *   If the tool server is on a *different machine* with a known IP: `http://[YOUR_TOOL_SERVER_IP]:8000`
5.  **Save**: Click "Save".

The tool server should now be registered and its functionalities (`/esxi/get_linux_vm_ip`, `/esxi/list_powered_on_vms`, `/vm/check_upgrades`, `/vm/apply_upgrades`) will be exposed to your LLM.

## How to Use with Open WebUI Chatbot

Global tools are hidden by default and need to be activated per user/chat.

1.  **Start a New Chat** or go to an existing chat in Open WebUI.
2.  **Enable the Tool**: Click the **+** button in the message input area (bottom left of the chat box).
3.  **Toggle on** the "VM Management and Upgrade Tool Server".
4.  **Ensure Native Function Calling**: For the best performance and intelligent tool usage, go to ⚙️ **Chat Controls** > **Advanced Params**, and change "Function Calling" to **Native**.

**Example Conversation Flow:**

You can now interact with your chatbot naturally. The LLM will determine which tool to use and what information it needs.

**Scenario: List Powered-On VMs**

1.  **You:** "Show me all powered-on VMs on my ESXi host."
2.  **Chatbot (Internal Action - Calls `/esxi/list_powered_on_vms`):**
    ```json
    {
      "status": "success",
      "powered_on_vms": [
        {
          "vm_name": "OpenVPN-Server-Prod",
          "ip_address": "192.168.1.100",
          "guest_os": "Ubuntu Linux (64-bit)",
          "powerState": "poweredOn"
        },
        ...
      ]
    }
    ```
3.  **Chatbot (To You):** "Here are your powered-on VMs: ..."

**Scenario: Update OpenVPN Server VM**

1.  **You:** "Hey, can you help me update my OpenVPN server? It's an Ubuntu VM on my ESXi host at `192.168.1.50`. The ESXi login is `root` with password `MySecureEsxiPass123`."
2.  **Chatbot:** "Please provide the exact name of the OpenVPN server VM and the SSH username."
3.  **You:** "The VM name is exactly `OpenVPN-Server-Prod` and the SSH username is `ubuntu`."
4.  **Chatbot (Internal Action - Calls `/esxi/get_linux_vm_ip`):**
    ```json
    {
      "vm_name": "OpenVPN-Server-Prod"
    }
    ```
5.  **Chatbot (To You):** "Found the VM with IP address `192.168.1.100`. Checking for upgrades..."
6.  **Chatbot (Internal Action - Calls `/vm/check_upgrades`):**
    ```json
    {
      "ip_address": "192.168.1.100",
      "username": "ubuntu",
      "ssh_key_path": "~/.ssh/openwebui_vm_key"
    }
    ```
7.  **Chatbot (To You):** "Upgrades available: ... Would you like to apply them?"
8.  **You:** "Yes."
9.  **Chatbot (Internal Action - Calls `/vm/apply_upgrades`):**
    ```json
    {
      "ip_address": "192.168.1.100",
      "username": "ubuntu",
      "ssh_key_path": "~/.ssh/openwebui_vm_key"
    }
    ```
10. **Chatbot (To You):** "Upgrades applied successfully!"

## Important Considerations & Security

*   **ESXi/vCenter Credentials**: The current setup involves loading ESXi/vCenter credentials from `config.json`. For production, secure this file and restrict access.
*   **SSH Key Security**: The SSH key without a passphrase (`~/.ssh/openwebui_vm_key`) grants access to your VMs.
    *   Ensure the host running the tool server is secured.
    *   Set strict file permissions on the private key (`chmod 600 ~/.ssh/openwebui_vm_key`).
    *   Consider using a dedicated, restricted SSH user on your VMs for updates, rather than `root` or a general admin user, to limit potential damage from a compromise.
*   **`paramiko.AutoAddPolicy()`**: In `run_ssh_command`, `client.set_missing_host_key_policy(paramiko.AutoAddPolicy())` automatically adds new SSH host keys to `known_hosts`. While convenient, it's less secure as it bypasses manual host key verification. For production, consider using `paramiko.RejectPolicy()` and pre-populating your `known_hosts` file or implementing a more robust host key management strategy.
*   **Firewall Rules**: Ensure proper firewall rules are in place to allow communication only between necessary components (Open WebUI backend to tool server, tool server to VMs, tool server to ESXi).
*   **VMware Tools**: Without VMware Tools installed and running in your guest VMs, the `/esxi/get_linux_vm_ip` function will not be able to retrieve the VM's IP address.
*   **Sudo Permissions**: The SSH user used for VM access must have `sudo` privileges to run `apt update` and `apt upgrade`.

## Troubleshooting

*   **Tool not appearing in Open WebUI or not being called by LLM:**
    *   Double-check the tool server URL in Open WebUI Admin Settings.
    *   Ensure the tool is enabled in the specific chat session (+ button).
    *   Verify your LLM's "Function Calling" setting is set to **Native** in Chat Controls > Advanced Params.
    *   Try restarting the Open WebUI Docker container (if applicable).
    *   Check the tool server's console for any startup errors.
*   **"Failed to connect to ESXi/vCenter Server." / "Authentication failed for ESXi/vCenter."**:
    *   Verify the `esxi_host_ip`, `esxi_username`, and `esxi_password` in `config.json` are correct.
    *   Ensure the ESXi/vCenter user has the necessary permissions (at least Read-only).
    *   Check network connectivity from the tool server machine to your ESXi host/vCenter (e.g., `ping [esxi_host_ip]`, `nc -vz [esxi_host_ip] 443`).
*   **"VM not found" / "No IP address reported."**:
    *   Ensure the `vm_name` provided to the chatbot exactly matches the VM name in ESXi/vCenter. VM names are case-sensitive.
    *   Confirm VMware Tools are installed and running inside the guest Ubuntu VM.
    *   Verify the VM is powered on.
*   **"Authentication failed for SSH."**:
    *   Ensure the `ssh_key_path` in `vm_update_tool_server.py` is correct (default `~/.ssh/openwebui_vm_key`).
    *   Verify the SSH key (`openwebui_vm_key` and `openwebui_vm_key.pub`) exists on the tool server machine.
    *   Check that the public key (`openwebui_vm_key.pub`) has been successfully copied to the Ubuntu VM's `~/.ssh/authorized_keys` for the specified `username`.
    *   Confirm the SSH user on the VM (`username`) is correct.
    *   Check file permissions on the private key (`chmod 600 ~/.ssh/openwebui_vm_key`).
*   **"Failed to check upgrades using apt..." / "Failed to apply upgrades using apt..."**:
    *   Ensure the SSH user has `sudo` privileges on the Ubuntu VM without requiring a password for `apt` commands (e.g., via `sudo visudo` configuration for `NOPASSWD`).
    *   Test the SSH connection and `sudo apt update` / `sudo apt upgrade -y` commands manually from the tool server machine's terminal.
*   **General Errors**:
    *   Check the console output of your `uvicorn` server for detailed Python tracebacks.
    *   Increase `logging.basicConfig(level=logging.DEBUG)` in `vm_update_tool_server.py` for more verbose logs.

## Running as a Systemd Service (Ubuntu)

You can easily install and run the VM Update Tool Server as a background service using the provided `setup.sh` script. This will set up the app to start automatically on boot and manage it with `systemctl`.

### Steps:

1. **Make the script executable:**
    ```bash
    chmod +x setup.sh
    ```

2. **Run the setup script as root (or with sudo):**
    ```bash
    sudo ./setup.sh
    ```
    - The script will prompt you for the absolute path to your application’s root directory (where `vm_update_tool_server.py` is located).
    - It will create a dedicated system user, copy the app files to `/opt/vm-update-tool`, set up a Python virtual environment, install dependencies, and create a systemd service.

3. **Service Management:**
    - **Check status:**
        ```bash
        sudo systemctl status vm-update-tool.service
        ```
    - **View logs:**
        ```bash
        sudo journalctl -u vm-update-tool.service -f
        ```
    - **Restart the service:**
        ```bash
        sudo systemctl restart vm-update-tool.service
        ```

4. **Access the API:**
    - By default, the server will be running on `http://0.0.0.0:8000` (all interfaces, port 8000).

**Note:**  
- The script will create a system user `vmupdateuser` and install the app in `/opt/vm-update-tool`.
- You can edit the `setup.sh` script to customize variables if needed.