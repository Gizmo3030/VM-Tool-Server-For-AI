# tests/test_api_endpoints.py
import httpx
import pytest
import time
import os
import json
from unittest.mock import patch, MagicMock

# The base URL where your Uvicorn app will be running in CI
BASE_URL = "http://localhost:8000"

# --- Pytest Fixtures ---

@pytest.fixture(scope="session")
def api_server_ready():
    """
    Waits for the API server to be reachable before running tests.
    """
    max_retries = 30 # Wait up to 60 seconds (30 * 2s)
    for i in range(max_retries):
        try:
            response = httpx.get(f"{BASE_URL}/", timeout=1)
            if response.status_code in [200, 404]:
                print(f"Attempt {i+1}: API is ready!")
                yield
                return
        except httpx.RequestError as e:
            print(f"Attempt {i+1}: API not ready yet. Error: {e}")
        time.sleep(2)
    pytest.fail("API did not become ready within the timeout period.")

@pytest.fixture(autouse=True, scope="session")
def setup_dummy_config_json():
    """
    Creates a dummy config.json for tests that might try to load it.
    Crucial for mocking, as the app still tries to load this file.
    """
    dummy_config = {
        "esxi_host_ip": "127.0.0.1", # Dummy IP for local testing/mocking
        "esxi_username": "dummy_user",
        "esxi_password": "dummy_password",
        "default_vm_username": "testuser",
        "default_vm_sudo_password": "testpassword"
    }
    config_path = "config.json"
    with open(config_path, "w") as f:
        json.dump(dummy_config, f)
    print(f"Created dummy {config_path} for tests.")
    yield
    os.remove(config_path)
    print(f"Cleaned up dummy {config_path}.")

# --- Mocking Fixtures ---

@pytest.fixture
def mock_esxi_connect():
    """Mocks pyVim.connect.SmartConnect and related pyVmomi objects."""
    with patch("pyVim.connect.SmartConnect") as mock_smart_connect:
        mock_si = MagicMock() # ServiceInstance
        mock_content = MagicMock() # RetrieveContent()
        mock_vm_view = MagicMock() # viewManager.CreateContainerView()

        # Configure a mock VM for get_linux_vm_ip
        mock_vm = MagicMock()
        mock_vm.name = "MyTestLinuxVM"
        mock_vm.summary.guest.guestFullName = "Ubuntu Linux (64-bit)"
        mock_vm.summary.guest.ipAddress = "192.168.1.10"
        mock_vm.summary.runtime.powerState = "poweredOn"

        # Configure a list of VMs for list_powered_on_vms
        mock_another_vm = MagicMock()
        mock_another_vm.name = "AnotherPoweredOnVM"
        mock_another_vm.summary.guest.guestFullName = "CentOS Linux (64-bit)"
        mock_another_vm.summary.guest.ipAddress = "192.168.1.11"
        mock_another_vm.summary.runtime.powerState = "poweredOn"

        mock_powered_off_vm = MagicMock()
        mock_powered_off_vm.name = "PoweredOffVM"
        mock_powered_off_vm.summary.guest.guestFullName = "Windows (64-bit)"
        mock_powered_off_vm.summary.guest.ipAddress = "192.168.1.12"
        mock_powered_off_vm.summary.runtime.powerState = "poweredOff"


        # The 'view' attribute of ContainerView should return the list of VMs
        mock_vm_view.view = [mock_vm, mock_another_vm, mock_powered_off_vm]

        mock_content.viewManager.CreateContainerView.return_value = mock_vm_view
        mock_si.RetrieveContent.return_value = mock_content
        mock_smart_connect.return_value = mock_si

        # Also mock Disconnect if it's called in finally blocks
        with patch("pyVim.connect.Disconnect"):
            yield mock_smart_connect # Yield the mock object for potential further configuration in tests

@pytest.fixture
def mock_paramiko_ssh():
    """Mocks paramiko.SSHClient and its methods."""
    with patch("paramiko.SSHClient") as mock_ssh_client_class:
        mock_client = MagicMock()
        mock_ssh_client_class.return_value = mock_client

        # Mock stdout/stderr for check_upgrades
        mock_stdout_check = MagicMock()
        mock_stdout_check.read.return_value = b"Reading package lists...\nDone\nAll packages are up to date.\n0 packages can be upgraded."
        mock_stderr_check = MagicMock()
        mock_stderr_check.read.return_value = b""

        # Mock stdout/stderr for apply_upgrades
        mock_stdout_apply = MagicMock()
        mock_stdout_apply.read.return_value = b"Reading package lists...\nDone\nBuilding dependency tree...\nDone\n0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded."
        mock_stderr_apply = MagicMock()
        mock_stderr_apply.read.return_value = b""

        # Configure exec_command to return different outputs based on the command
        def mock_exec_command(command, timeout):
            if "apt list --upgradable" in command:
                return MagicMock(), mock_stdout_check, mock_stderr_check
            elif "apt upgrade -y" in command:
                return MagicMock(), mock_stdout_apply, mock_stderr_apply
            return MagicMock(), MagicMock(read=lambda: b""), MagicMock(read=lambda: b"")

        mock_client.exec_command.side_effect = mock_exec_command
        mock_client.open_sftp.return_value = MagicMock() # If you have SFTP calls

        yield mock_ssh_client_class # Yield the mock SSHClient class for potential further configuration

# --- API Tests ---

def test_root_endpoint_status(api_server_ready):
    """Verify the root endpoint is accessible and returns a 200 OK."""
    response = httpx.get(f"{BASE_URL}/")
    assert response.status_code == 200
    assert "message" in response.json()

def test_status_endpoint_content(api_server_ready):
    """Verify the /status endpoint (if it exists) returns expected content."""
    # This assumes you have a /status endpoint in vm_update_tool_server.py
    response = httpx.get(f"{BASE_URL}/status")
    assert response.status_code == 200
    assert response.json().get("status") == "running"

# --- Tests for endpoints with ESXi interactions (now mocked) ---
def test_get_linux_vm_ip_endpoint(api_server_ready, mock_esxi_connect):
    """
    Verify /esxi/get_linux_vm_ip endpoint with mocked ESXi connection.
    """
    vm_name_payload = {"vm_name": "MyTestLinuxVM"}
    response = httpx.post(f"{BASE_URL}/esxi/get_linux_vm_ip", json=vm_name_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["vm_name"] == "MyTestLinuxVM"
    assert data["ip_address"] == "192.168.1.10"
    assert "Linux" in data["guest_os"]
    assert data["powerState"] == "poweredOn"
    
    # Verify that SmartConnect was called
    mock_esxi_connect.assert_called_once()

def test_get_linux_vm_ip_endpoint_vm_not_found(api_server_ready, mock_esxi_connect):
    """
    Verify /esxi/get_linux_vm_ip when VM is not found.
    Needs to adjust the mock or ensure no VM matches.
    """
    # To simulate 'not found', ensure the mock_vm_view.view doesn't contain the requested name
    # The current mock setup will find other VMs if the name isn't "MyTestLinuxVM"
    # A more robust mock would configure view.view dynamically based on the request.
    # For now, let's test a non-linux VM if the mock provides one.
    vm_name_payload = {"vm_name": "NonExistentVM"}
    response = httpx.post(f"{BASE_URL}/esxi/get_linux_vm_ip", json=vm_name_payload)
    
    assert response.status_code == 404
    assert "not found on ESXi/vCenter" in response.json()["detail"]


def test_list_powered_on_vms_endpoint(api_server_ready, mock_esxi_connect):
    """
    Verify /esxi/list_powered_on_vms endpoint with mocked ESXi connection.
    """
    response = httpx.get(f"{BASE_URL}/esxi/list_powered_on_vms")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["powered_on_vms"]) == 2 # MyTestLinuxVM and AnotherPoweredOnVM
    assert any(vm['vm_name'] == "MyTestLinuxVM" for vm in data["powered_on_vms"])
    assert any(vm['vm_name'] == "AnotherPoweredOnVM" for vm in data["powered_on_vms"])
    assert not any(vm['vm_name'] == "PoweredOffVM" for vm in data["powered_on_vms"]) # Should not include poweredOff
    
    mock_esxi_connect.assert_called_once()

# --- Tests for endpoints with SSH interactions (now mocked) ---
def test_check_vm_upgrades_endpoint(api_server_ready, mock_paramiko_ssh):
    """
    Verify /vm/check_upgrades endpoint with mocked SSH.
    """
    vm_config = {
        "ip_address": "192.168.1.100",
        "username": "ubuntu",
        "ssh_key_path": "~/.ssh/openwebui_vm_key"
    }
    response = httpx.post(f"{BASE_URL}/vm/check_upgrades", json=vm_config)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "no_upgrades"
    assert "All packages are up to date" in data["details"]
    
    # Verify SSHClient and exec_command were called
    mock_paramiko_ssh.assert_called_once()
    mock_paramiko_ssh.return_value.connect.assert_called_once()
    mock_paramiko_ssh.return_value.exec_command.assert_called_once()


def test_apply_vm_upgrades_endpoint(api_server_ready, mock_paramiko_ssh):
    """
    Verify /vm/apply_upgrades endpoint with mocked SSH.
    """
    vm_config = {
        "ip_address": "192.168.1.100",
        "username": "ubuntu",
        "ssh_key_path": "~/.ssh/openwebui_vm_key"
    }
    response = httpx.post(f"{BASE_URL}/vm/apply_upgrades", json=vm_config)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "no_upgrades_applied"
    assert "0 upgraded, 0 newly installed" in data["details"]
    
    mock_paramiko_ssh.assert_called_once()
    mock_paramiko_ssh.return_value.connect.assert_called_once()
    mock_paramiko_ssh.return_value.exec_command.assert_called_once()
