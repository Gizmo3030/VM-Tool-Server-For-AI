#!/bin/bash

# --- Configuration Variables ---
APP_NAME="vm-update-tool"
APP_DIR="/opt/$APP_NAME"
APP_MODULE_FILE="vm_update_tool_server.py" # The main Python file
APP_MODULE_NAME="vm_update_tool_server"   # The module name (without .py)
APP_ENTRY_POINT="app"                     # The FastAPI/Starlette app instance name (e.g., vm_update_tool_server:app)
APP_USER="vmupdateuser"
UVICORN_HOST="0.0.0.0"
UVICORN_PORT="8000"
VENV_NAME="venv"
SERVICE_FILE="/etc/systemd/system/$APP_NAME.service"

# --- Logging Functions ---
log_info() {
    echo -e "\033[1;34m[INFO]\033[0m $1"
}

log_success() {
    echo -e "\033[1;32m[SUCCESS]\033[0m $1"
}

log_warning() {
    echo -e "\033[1;33m[WARNING]\033[0m $1"
}

log_error() {
    echo -e "\033[1;31m[ERROR]\033[0m $1"
    exit 1
}

# --- Script Pre-checks ---
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root. Please use 'sudo ./$0'."
    fi
}

# --- Main Functions ---

install_dependencies() {
    log_info "Updating apt packages and installing python3-venv..."
    sudo apt update || log_error "Failed to update apt."
    sudo apt install -y python3-venv || log_error "Failed to install python3-venv."
    log_success "Python3 venv installed."
}

prompt_for_app_source() {
    APP_SOURCE_DIR=""
    while [ ! -d "$APP_SOURCE_DIR" ] || [ ! -f "$APP_SOURCE_DIR/$APP_MODULE_FILE" ]; do
        read -rp "$(log_info 'Please enter the absolute path to your application''s root directory (e.g., /home/youruser/my_app_project/): ')" APP_SOURCE_DIR
        if [ ! -d "$APP_SOURCE_DIR" ]; then
            log_warning "Directory '$APP_SOURCE_DIR' does not exist. Please enter a valid path."
        elif [ ! -f "$APP_SOURCE_DIR/$APP_MODULE_FILE" ]; then
            log_warning "File '$APP_SOURCE_DIR/$APP_MODULE_FILE' not found. Please ensure it's in the specified directory."
        fi
    done
    log_success "Application source directory set to: $APP_SOURCE_DIR"
}

create_user_and_dir() {
    log_info "Creating system user '$APP_USER'..."
    if id -u "$APP_USER" &>/dev/null; then
        log_warning "User '$APP_USER' already exists. Skipping user creation."
    else
        sudo useradd --system --no-create-home "$APP_USER" || log_error "Failed to create user '$APP_USER'."
        log_success "User '$APP_USER' created."
    fi

    log_info "Creating application directory '$APP_DIR'..."
    sudo mkdir -p "$APP_DIR" || log_error "Failed to create application directory."
    log_success "Application directory created."

    log_info "Copying application files from '$APP_SOURCE_DIR' to '$APP_DIR'..."
    sudo cp -r "$APP_SOURCE_DIR/." "$APP_DIR/" || log_error "Failed to copy application files."
    log_success "Application files copied."

    log_info "Setting ownership for '$APP_DIR' to '$APP_USER:$APP_USER'..."
    sudo chown -R "$APP_USER:$APP_USER" "$APP_DIR" || log_error "Failed to set ownership for '$APP_DIR'."
    log_success "Ownership set."
}

setup_virtualenv() {
    log_info "Creating Python virtual environment in '$APP_DIR/$VENV_NAME'..."
    sudo -u "$APP_USER" python3 -m venv "$APP_DIR/$VENV_NAME" || log_error "Failed to create virtual environment."
    log_success "Virtual environment created."

    log_info "Installing uvicorn and other dependencies (if requirements.txt exists)..."
    VENV_PYTHON="$APP_DIR/$VENV_NAME/bin/python"
    VENV_PIP="$APP_DIR/$VENV_NAME/bin/pip"

    if [ ! -f "$VENV_PYTHON" ]; then
        log_error "Virtual environment Python executable not found: $VENV_PYTHON"
    fi

    sudo -u "$APP_USER" "$VENV_PIP" install uvicorn || log_error "Failed to install uvicorn."

    if [ -f "$APP_DIR/requirements.txt" ]; then
        log_info "Found requirements.txt. Installing dependencies..."
        sudo -u "$APP_USER" "$VENV_PIP" install -r "$APP_DIR/requirements.txt" || log_error "Failed to install dependencies from requirements.txt."
        log_success "Dependencies from requirements.txt installed."
    else
        log_warning "No requirements.txt found in '$APP_DIR'. Only uvicorn was installed."
    fi
    log_success "Uvicorn and dependencies installed in virtual environment."
}

create_systemd_service() {
    log_info "Creating Systemd service file: $SERVICE_FILE"
    SERVICE_CONTENT=$(cat <<EOF
[Unit]
Description=VM Update Tool Server
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/$VENV_NAME/bin/uvicorn $APP_MODULE_NAME:$APP_ENTRY_POINT --host $UVICORN_HOST --port $UVICORN_PORT
Restart=on-failure
RestartSec=5
Type=simple
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
)
    echo "$SERVICE_CONTENT" | sudo tee "$SERVICE_FILE" > /dev/null || log_error "Failed to create service file."
    log_success "Service file '$SERVICE_FILE' created."
}

manage_service() {
    log_info "Reloading Systemd daemon..."
    sudo systemctl daemon-reload || log_error "Failed to reload systemd daemon."
    log_success "Systemd daemon reloaded."

    log_info "Enabling service to start on boot..."
    sudo systemctl enable "$APP_NAME.service" || log_error "Failed to enable service."
    log_success "Service enabled."

    log_info "Starting service..."
    sudo systemctl start "$APP_NAME.service" || log_error "Failed to start service."
    log_success "Service started."

    log_info "Checking service status..."
    sudo systemctl status "$APP_NAME.service"
}

# --- Main Script Execution ---
main() {
    check_root

    log_info "Starting setup for VM Update Tool Service..."

    read -rp "$(log_info 'This script will set up your Uvicorn application as a systemd service. Continue? (y/N): ')" CONFIRMATION
    if [[ ! "$CONFIRMATION" =~ ^[Yy]$ ]]; then
        log_info "Setup cancelled by user."
        exit 0
    fi

    prompt_for_app_source
    install_dependencies
    create_user_and_dir
    setup_virtualenv
    create_systemd_service
    manage_service

    log_info "Setup complete for VM Update Tool Service!"
    log_info "You can check the service status with: sudo systemctl status $APP_NAME.service"
    log_info "To view logs, use: sudo journalctl -u $APP_NAME.service -f"
    log_info "Your Uvicorn application should now be running on http://$UVICORN_HOST:$UVICORN_PORT"
}

main "$@"
