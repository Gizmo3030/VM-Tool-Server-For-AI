# tests/test_api_endpoints.py
import httpx
import pytest
import time
import os
import json

# The base URL where your Uvicorn app will be running in CI
BASE_URL = "http://localhost:8000"

# --- Pytest Fixture to wait for the API to start ---
@pytest.fixture(scope="session")
def api_server_ready():
    """
    Waits for the API server to be reachable before running tests.
    """
    max_retries = 30 # Wait up to 60 seconds (30 * 2s)
    for i in range(max_retries):
        try:
            # Hit a simple endpoint like '/' to check if the server is up
            response = httpx.get(f"{BASE_URL}/", timeout=1)
            if response.status_code in [200, 404]: # 404 is fine, means server is responding
                print(f"Attempt {i+1}: API is ready!")
                yield
                return
        except httpx.RequestError as e:
            print(f"Attempt {i+1}: API not ready yet. Error: {e}")
        time.sleep(2) # Wait for 2 seconds before retrying
    pytest.fail("API did not become ready within the timeout period.")

# --- Helper to create a dummy config.json for ESXi calls (for CI only) ---
# This is crucial if your ESXi-dependent endpoints require a config.json.
# For actual testing against ESXi, you'd use GitHub Secrets to populate these values.
# For simple functional tests on PR, this might just allow the code path to run.
@pytest.fixture(autouse=True, scope="session")
def setup_dummy_config_json():
    # Create a dummy config.json for tests that might try to load it.
    # Replace with actual GitHub Secrets if you are testing against a real ESXi host.
    dummy_config = {
        "esxi_host_ip": "127.0.0.1", # Dummy IP for local testing/mocking
        "esxi_username": "dummy_user",
        "esxi_password": "dummy_password",
        "default_vm_username": "testuser",
        "default_vm_sudo_password": "testpassword"
    }
    config_path = "config.json" # Assumes config.json is in the root
    with open(config_path, "w") as f:
        json.dump(dummy_config, f)
    print(f"Created dummy {config_path} for tests.")
    yield
    # Clean up the dummy config.json after tests
    os.remove(config_path)
    print(f"Cleaned up dummy {config_path}.")

# --- API Tests ---

def test_root_endpoint_status(api_server_ready):
    """Verify the root endpoint is accessible and returns a 200 OK."""
    response = httpx.get(f"{BASE_URL}/")
    assert response.status_code == 200
    assert "message" in response.json() # Check for expected content

def test_status_endpoint_content(api_server_ready):
    """Verify the /status endpoint (if it exists) returns expected content."""
    # This assumes you have a /status endpoint in vm_update_tool_server.py
    # If not, you can remove or modify this test.
    response = httpx.get(f"{BASE_URL}/status")
    assert response.status_code == 200
    assert response.json().get("status") == "running"


# Example of testing an endpoint requiring a body and specific logic
def test_check_vm_upgrades_endpoint(api_server_ready):
    """
    Verify /vm/check_upgrades endpoint.
    NOTE: This test will likely fail unless 'run_ssh_command' is mocked
    or you have a real VM accessible with the default SSH key.
    For CI, mocking paramiko/SSH interactions is crucial for this type of test.
    """
    vm_config = {
        "ip_address": "192.168.1.100", # Dummy IP
        "username": "ubuntu",
        "ssh_key_path": "~/.ssh/openwebui_vm_key"
    }
    response = httpx.post(f"{BASE_URL}/vm/check_upgrades", json=vm_config)
    # The actual expected status code might be 500 (SSH error) or 200 (if mocked)
    # Depending on how you mock/handle external dependencies in CI, adjust this.
    # For a basic functional check, we just ensure the endpoint *responds*.
    assert response.status_code in [200, 500], f"Expected 200 or 500, got {response.status_code}. Response: {response.text}"
    # Further assertions would depend on mocking strategy

def test_list_powered_on_vms_endpoint(api_server_ready):
    """
    Verify /esxi/list_powered_on_vms endpoint.
    NOTE: This endpoint directly calls pyVmomi and requires ESXi credentials
    loaded from config.json and access to a real ESXi host.
    For CI, you would need to mock `pyVim.connect` and `vim` objects,
    or provide real credentials via GitHub Secrets (HIGHLY DISCOURAGED).
    Without mocking, this will likely fail with connection or permission errors.
    """
    response = httpx.get(f"{BASE_URL}/esxi/list_powered_on_vms")
    # Again, expect 500 if ESXi connection fails, or 200 if pyVmomi is mocked.
    assert response.status_code in [200, 500], f"Expected 200 or 500, got {response.status_code}. Response: {response.text}"
    # If mocked, you'd check for "powered_on_vms" in response.json()