from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import paramiko
import logging
import os # For resolving home directory in SSH key path
import ssl
import json
from contextlib import contextmanager
from typing import List, Dict, Optional

# Import pyVmomi components
from pyVim import connect
from pyVmomi import vim

app = FastAPI(
    title="VM Management and Upgrade Tool Server", # Updated title
    description="Tooling for discovering VMs on ESXi/vCenter and managing upgrades on Ubuntu Linux VMs via SSH."
)

class PoweredOnVMsResponse(BaseModel):
    status: str
    powered_on_vms: List[Dict[str, Optional[str]]]

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Models for Request Bodies ---
class VMConfig(BaseModel):
    """
    Model for specifying SSH connection details to a Linux VM.

    Attributes:
        ip_address (str): The IP address of the target VM.
        username (str): The SSH username to use for connecting.
        ssh_key_path (str): Path to the SSH private key file (default: ~/.ssh/openwebui_vm_key).
    """
    ip_address: str
    username: str
    ssh_key_path: str = "~/.ssh/openwebui_vm_key" # Default path for SSH key

class ESXiVMDiscoveryConfig(BaseModel):
    """
    Model for specifying ESXi/vCenter connection and VM search parameters.

    Attributes:
        esxi_host_ip (str): IP address of the ESXi host or vCenter server.
        esxi_username (str): Username for ESXi/vCenter authentication.
        esxi_password (str): Password for ESXi/vCenter authentication.
        vm_name (str): The exact name of the VM to search for.
    """
    esxi_host_ip: str
    esxi_username: str
    esxi_password: str
    vm_name: str # The exact name of the VM to search for

# --- Helper for SSH Commands (Ubuntu VM interactions) ---
def run_ssh_command(vm_config: VMConfig, command: str) -> str:
    """
    Executes a shell command on a remote Linux VM over SSH using Paramiko.

    Args:
        vm_config (VMConfig): SSH connection details.
        command (str): The shell command to execute.

    Returns:
        str: The command's standard output.

    Raises:
        HTTPException: For authentication, SSH, or file errors.
    """
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy()) 

    resolved_key_path = os.path.expanduser(vm_config.ssh_key_path)

    try:
        private_key = paramiko.RSAKey.from_private_key_file(resolved_key_path)
        client.connect(
            hostname=vm_config.ip_address,
            username=vm_config.username,
            pkey=private_key,
            timeout=10 
        )

        logging.info(f"Executing SSH command on {vm_config.ip_address}: '{command}'")
        stdin, stdout, stderr = client.exec_command(command, timeout=300)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()

        if error:
            logging.warning(f"SSH Command '{command}' on {vm_config.ip_address} produced stderr: {error}")
        
        logging.info(f"SSH Command output on {vm_config.ip_address}: {output}")
        return output

    except paramiko.AuthenticationException:
        logging.error(f"Authentication failed for {vm_config.username}@{vm_config.ip_address}. Check SSH key/password. Key path: {resolved_key_path}")
        raise HTTPException(status_code=401, detail=f"Authentication failed for {vm_config.username}@{vm_config.ip_address}. Check SSH key/password.")
    except FileNotFoundError:
        logging.error(f"SSH Key not found at {resolved_key_path}. Ensure the key exists and path is correct.")
        raise HTTPException(status_code=404, detail=f"SSH Key not found at {resolved_key_path}. Ensure the key exists and path is correct.")
    except paramiko.SSHException as e:
        logging.error(f"SSH connection or command error: {e}")
        raise HTTPException(status_code=500, detail=f"SSH error connecting to {vm_config.ip_address}: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during SSH operation: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during SSH operation: {e}")
    finally:
        client.close()

# --- ESXi/vCenter VM Discovery Endpoint ---
class VMNameRequest(BaseModel):
    vm_name: str

# --- Helper Functions ---

def load_esxi_config() -> dict:
    try:
        with open("config.json") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config.json: {e}")
        raise HTTPException(status_code=500, detail="Failed to load ESXi config from config.json")

def load_vm_defaults() -> dict:
    """
    Loads default VM SSH username and sudo password from config.json.
    """
    try:
        with open("config.json") as f:
            config = json.load(f)
            return {
                "default_vm_username": config.get("default_vm_username", "root"),
                "default_vm_sudo_password": config.get("default_vm_sudo_password", "password!")
            }
    except Exception as e:
        logging.error(f"Failed to load VM defaults from config.json: {e}")
        raise HTTPException(status_code=500, detail="Failed to load VM defaults from config.json")

# --- Ubuntu VM Upgrade Endpoints ---
@app.post("/vm/check_upgrades")
async def check_vm_upgrades(vm_config: VMConfig):
    """
    Checks for available package upgrades and update on a specified Ubuntu Linux VM using apt.
    """
    vm_defaults = load_vm_defaults()
    logging.info(f"Checking for upgrades and update on Ubuntu VM: {vm_config.ip_address} (forcing username '{vm_defaults['default_vm_username']}') using apt.")

    # Force username from config
    vm_config.username = vm_defaults["default_vm_username"]
    sudo_password = vm_defaults["default_vm_sudo_password"]
    
    try:
        # Provide sudo password non-interactively
        command = f"echo '{sudo_password}' | sudo -S apt update && apt list --upgradable"
        apt_output = run_ssh_command(vm_config, command)
        upgradable_packages = [line for line in apt_output.splitlines() if "upgradable from" in line or "newer is available" in line]
        
        if upgradable_packages:
            return {"status": "upgrades_available", "package_manager": "apt", "details": "Found the following upgradable packages via apt:\n" + "\n".join(upgradable_packages)}
        else:
            if "All packages are up to date" in apt_output or "0 packages can be upgraded" in apt_output:
                return {"status": "no_upgrades", "package_manager": "apt", "details": "No upgradable packages found via apt. System is up-to-date."}
            else:
                return {"status": "no_upgrades", "package_manager": "apt", "details": "Apt update ran, but no explicit upgradable packages identified. Your system is likely up-to-date."}
        
    except HTTPException as e:
        logging.error(f"Failed to check upgrades on {vm_config.ip_address} using apt: {e.detail}")
        raise HTTPException(status_code=500, detail=f"Failed to check upgrades on {vm_config.ip_address} using apt: {e.detail}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during apt upgrade check: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during apt upgrade check: {e}")

@app.post("/vm/apply_upgrades")
async def apply_vm_upgrades(vm_config: VMConfig):
    """
    Applies all available package upgrades and update on a specified Ubuntu Linux VM using apt.
    """
    vm_defaults = load_vm_defaults()
    logging.info(f"Applying upgrades and update on Ubuntu VM: {vm_config.ip_address} (forcing username '{vm_defaults['default_vm_username']}') using apt.")

    # Force username from config
    vm_config.username = vm_defaults["default_vm_username"]
    sudo_password = vm_defaults["default_vm_sudo_password"]
    
    try:
        # Provide sudo password non-interactively
        command = f"echo '{sudo_password}' | sudo -S apt update && echo '{sudo_password}' | sudo -S apt upgrade -y"
        apt_upgrade_output = run_ssh_command(vm_config, command)
        if "0 upgraded, 0 newly installed" in apt_upgrade_output or "0 to upgrade, 0 to newly install" in apt_upgrade_output or "0 packages upgraded" in apt_upgrade_output:
             return {"status": "no_upgrades_applied", "package_manager": "apt", "details": "No new packages were upgraded or installed by apt. System was already up-to-date or no new upgrades were available."}
        return {"status": "success", "package_manager": "apt", "details": apt_upgrade_output}
    except HTTPException as e:
        logging.error(f"Failed to apply upgrades on {vm_config.ip_address} using apt: {e.detail}")
        raise HTTPException(status_code=500, detail=f"Failed to apply upgrades on {vm_config.ip_address} using apt: {e.detail}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during apt upgrade application: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during apt upgrade application: {e}")

@app.post("/esxi/get_linux_vm_ip")
async def get_linux_vm_ip_from_esxi(request: VMNameRequest):
    """
    Looks up a Linux VM by name on an ESXi/vCenter server and returns its IP address.

    Loads ESXi connection details from config.json.

    Request Body:
        vm_name (str): The exact name of the VM to search for.

    Returns:
        JSON object with VM name, IP address, guest OS, and power state.

    Errors:
        400: VM found but is not a Linux VM.
        403: Permission denied on ESXi/vCenter.
        404: VM not found or no IP address reported.
        500: Connection or retrieval error.
    """
    # Load ESXi config from config.json
    try:
        with open("config.json") as f:
            esxi_config = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config.json: {e}")
        raise HTTPException(status_code=500, detail="Failed to load ESXi config from config.json")

    config = ESXiVMDiscoveryConfig(
        esxi_host_ip=esxi_config["esxi_host_ip"],
        esxi_username=esxi_config["esxi_username"],
        esxi_password=esxi_config["esxi_password"],
        vm_name=request.vm_name
    )

    logging.info(f"Attempting to connect to ESXi/vCenter at {config.esxi_host_ip} to find VM: {config.vm_name}")
    service_instance = None
    try:
        try:
            # Use SmartConnect with an unverified SSL context
            context = ssl._create_unverified_context()
            service_instance = connect.SmartConnect(
                host=config.esxi_host_ip,
                user=config.esxi_username,
                pwd=config.esxi_password,
                sslContext=context
            )
            logging.info(f"Service instance: {service_instance} (type: {type(service_instance)})")
            if not service_instance:
                raise HTTPException(status_code=500, detail="Failed to connect to ESXi/vCenter Server.")
        except Exception as e:
            logging.error(f"Error connecting to ESXi/vCenter: {e}")
            raise HTTPException(status_code=500, detail=f"Error connecting to ESXi/vCenter: {e}")

        content = service_instance.RetrieveContent() # Retrieve the content of the service instance [1]

        # Get a list of all VMs [1]
        vm_view = content.viewManager.CreateContainerView(
            content.rootFolder, [vim.VirtualMachine], True
        )
        vms = vm_view.view
        
        found_vm = None
        for vm in vms:
            # Check VM name and guest OS [1]
            if vm.name == config.vm_name:
                # Basic check for Linux OS (can be refined based on specific guest OS names)
                guest_os = vm.summary.guest.guestFullName if vm.summary.guest else "Unknown"
                logging.info(f"Found VM '{vm.name}'. Guest OS: {guest_os}")
                if "Linux" in guest_os or "Ubuntu" in guest_os: # Assuming Ubuntu is a common Linux variant you'd find
                    found_vm = vm
                    break
                else:
                    logging.warning(f"VM '{config.vm_name}' found, but its guest OS ('{guest_os}') is not Linux. Skipping.")
                    raise HTTPException(status_code=400, detail=f"VM '{config.vm_name}' is not a Linux VM (detected OS: {guest_os}).")


        if found_vm:
            ip_address = found_vm.summary.guest.ipAddress
            if ip_address:
                logging.info(f"Found VM '{found_vm.name}' with IP: {ip_address}")
                return {
                    "status": "success",
                    "vm_name": found_vm.name,
                    "ip_address": ip_address,
                    "guest_os": found_vm.summary.guest.guestFullName,
                    "powerState": found_vm.summary.runtime.powerState
                }
            else:
                logging.warning(f"VM '{found_vm.name}' found, but no IP address reported by VMware Tools.")
                raise HTTPException(status_code=404, detail=f"VM '{config.vm_name}' found, but no IP address reported. Ensure VMware Tools are installed and running.")
        else:
            logging.warning(f"VM '{config.vm_name}' not found on ESXi/vCenter.")
            raise HTTPException(status_code=404, detail=f"VM '{config.vm_name}' not found on ESXi/vCenter.")

    except vim.fault.NoPermission as e:
        logging.error(f"Permission error connecting to ESXi/vCenter: {e}")
        raise HTTPException(status_code=403, detail=f"Permission denied for ESXi/vCenter. Check credentials and user roles.")
    except Exception as e:
        logging.error(f"Error connecting to ESXi/vCenter or finding VM: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve VM IP from ESXi/vCenter: {e}")
    finally:
        if service_instance:
            connect.Disconnect(service_instance)

@app.get("/esxi/list_powered_on_vms")
async def list_powered_on_vms():
    """
    Returns a list of all VMs that are currently powered on from the ESXi/vCenter server.

    Loads ESXi connection details from config.json.

    Returns:
        JSON object with a list of powered-on VMs, each including name, IP address, guest OS, and power state.

    Errors:
        403: Permission denied on ESXi/vCenter.
        500: Connection or retrieval error.
    """
    try:
        with open("config.json") as f:
            esxi_config = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load config.json: {e}")
        raise HTTPException(status_code=500, detail="Failed to load ESXi config from config.json")

    service_instance = None
    try:
        context = ssl._create_unverified_context()
        service_instance = connect.SmartConnect(
            host=esxi_config["esxi_host_ip"],
            user=esxi_config["esxi_username"],
            pwd=esxi_config["esxi_password"],
            sslContext=context
        )
        content = service_instance.RetrieveContent()
        vm_view = content.viewManager.CreateContainerView(
            content.rootFolder, [vim.VirtualMachine], True
        )
        vms = vm_view.view

        powered_on_vms = []
        for vm in vms:
            power_state = vm.summary.runtime.powerState
            if power_state == "poweredOn":
                guest_os = vm.summary.guest.guestFullName if vm.summary.guest else "Unknown"
                ip_address = vm.summary.guest.ipAddress if vm.summary.guest else None
                powered_on_vms.append({
                    "vm_name": vm.name,
                    "ip_address": ip_address,
                    "guest_os": guest_os,
                    "powerState": power_state
                })

        return {"status": "success", "powered_on_vms": powered_on_vms}

    except vim.fault.NoPermission as e:
        logging.error(f"Permission error connecting to ESXi/vCenter: {e}")
        raise HTTPException(status_code=403, detail="Permission denied for ESXi/vCenter. Check credentials and user roles.")
    except Exception as e:
        logging.error(f"Error retrieving powered-on VMs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve powered-on VMs: {e}")
    finally:
        if service_instance:
            connect.Disconnect(service_instance)