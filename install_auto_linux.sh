#!/bin/bash

# Auto_Jobs_Applier_AIHawk Automated Installation Script
# This script sets up the Auto_Jobs_Applier_AIHawk project on Ubuntu via WSL.

# Use
# chmod +x install_auto_linux.sh
# ./install_auto_linux.sh

set -Eeuo pipefail  # Enhanced error handling

# Variables
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/virtual"
CRON_SCRIPT="$PROJECT_DIR/run_auto_jobs.sh"
CRON_LOG="$PROJECT_DIR/log/cron.log"
RESUME_DIR="$PROJECT_DIR/resumes"
PYTHON_VERSION="3.11"  # Specify the desired Python version

# Function to display information messages
function echo_info() {
    echo -e "\e[34m[INFO]\e[0m $1"
}

# Function to display error messages
function echo_error() {
    echo -e "\e[31m[ERROR]\e[0m $1" >&2
}

# Ensure script is run from the project directory
cd "$PROJECT_DIR"

# Step 1: Update and Upgrade Ubuntu Packages
echo_info "Updating and upgrading Ubuntu packages..."
sudo apt-get update -y && sudo apt-get upgrade -y

# Step 2: Install Essential Dependencies
echo_info "Installing essential dependencies..."
sudo apt-get install -y \
    software-properties-common \
    wget \
    unzip \
    git \
    curl \
    gnupg \
    lsb-release \
    build-essential \
    libssl-dev \
    libffi-dev \
    jq

# Step 3: Add Deadsnakes PPA for Python
echo_info "Adding Deadsnakes PPA repository for Python $PYTHON_VERSION..."
if ! grep -q "deadsnakes/ppa" /etc/apt/sources.list.d/*.list 2>/dev/null; then
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update -y
fi

# Step 4: Install the Latest Python Version
echo_info "Installing Python $PYTHON_VERSION..."
sudo apt-get install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev

# Step 5: Update Python3 Alternative to the New Version
echo_info "Configuring Python3 to use version $PYTHON_VERSION..."
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python${PYTHON_VERSION} 2
sudo update-alternatives --set python3 /usr/bin/python${PYTHON_VERSION}

# Verify the installed Python version
echo_info "Verifying the installed Python version..."
python3 --version

# Step 6: Install pip for the New Python Version
echo_info "Installing pip for Python $PYTHON_VERSION..."
curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3 -

# Step 7: Install Additional Dependencies
echo_info "Installing additional Python dependencies..."
sudo apt-get install -y python3-pip python3-venv

# Step 8: Set Up Python Virtual Environment
echo_info "Setting up Python virtual environment..."
python3 -m venv "$VENV_DIR"

# Activate the virtual environment
source "$VENV_DIR/bin/activate"

# Upgrade pip inside the virtual environment
pip install --upgrade pip

# Step 9: Install Project Dependencies
echo_info "Installing project dependencies..."
if [[ -f "requirements.txt" ]]; then
    pip install -r requirements.txt
else
    echo_error "requirements.txt not found in $PROJECT_DIR"
    exit 1
fi

# Step 10: Fetch Latest Stable Chrome and ChromeDriver Versions
echo_info "Fetching the latest stable versions of Chrome and ChromeDriver..."

# Fetch the JSON data
JSON_DATA=$(curl -sSL "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json")

# Extract the latest stable version and download URLs
CHROME_VERSION=$(echo "$JSON_DATA" | jq -r '.channels.Stable.version')
CHROME_URL=$(echo "$JSON_DATA" | jq -r '.channels.Stable.downloads.chrome | .[] | select(.platform=="linux64") | .url')
CHROMEDRIVER_URL=$(echo "$JSON_DATA" | jq -r '.channels.Stable.downloads.chromedriver | .[] | select(.platform=="linux64") | .url')

if [[ -z "$CHROME_VERSION" || -z "$CHROME_URL" || -z "$CHROMEDRIVER_URL" ]]; then
    echo_error "Failed to retrieve the latest stable versions."
    exit 1
fi

echo_info "Latest stable Chrome version: $CHROME_VERSION"

# Step 11: Install Google Chrome
echo_info "Installing Google Chrome version $CHROME_VERSION..."

# Download Chrome
wget -q -O chrome-linux64.zip "$CHROME_URL"
if [[ ! -f "chrome-linux64.zip" ]]; then
    echo_error "Failed to download Google Chrome."
    exit 1
fi

# Extract Chrome
unzip -q chrome-linux64.zip -d chrome_temp

# Ensure the destination directory exists
sudo mkdir -p /opt/google/chrome

# Remove existing Chrome installation if necessary
if [[ -d "/opt/google/chrome/chrome-linux64" ]]; then
    echo_info "Removing existing Chrome installation..."
    sudo rm -rf /opt/google/chrome/chrome-linux64
fi

# Move the new Chrome installation
sudo mv chrome_temp/chrome-linux64 /opt/google/chrome/

# Create or update the symbolic link
sudo ln -sf /opt/google/chrome/chrome-linux64/chrome /usr/bin/google-chrome

# Clean up
rm -rf chrome_temp chrome-linux64.zip

# Verify Google Chrome installation
echo_info "Verifying Google Chrome installation..."
google-chrome --version || { echo_error "Google Chrome installation failed."; exit 1; }

# Step 13: Update Configuration Files
echo_info "Updating configuration files..."

# Paths to configuration files
CONFIG_YAML="$PROJECT_DIR/data_folder/config.yaml"
PLAIN_TEXT_RESUME_YAML="$PROJECT_DIR/data_folder/plain_text_resume.yaml"

# Ensure configuration files exist
if [[ ! -f "$CONFIG_YAML" ]]; then
    echo_error "Configuration file not found: $CONFIG_YAML"
    exit 1
fi

if [[ ! -f "$PLAIN_TEXT_RESUME_YAML" ]]; then
    echo_error "Plain text resume file not found: $PLAIN_TEXT_RESUME_YAML"
    exit 1
fi

# Step 14: Create .env File
echo_info "Setting up the .env file..."

ENV_FILE="$PROJECT_DIR/.env"
ENV_EXAMPLE_FILE="$PROJECT_DIR/.env.example"

# Create .env.example if it doesn't exist
if [[ ! -f "$ENV_EXAMPLE_FILE" ]]; then
    echo_info "Creating .env.example file..."
    cat <<EOL > "$ENV_EXAMPLE_FILE"
# .env.example

LLM_API_KEY=your_actual_api_key_here
EOL
fi

# Check if .env already exists to prevent overwriting
if [[ ! -f "$ENV_FILE" ]]; then
    # Prompt user to enter their LLM_API_KEY
    echo_info "Please enter your LLM_API_KEY (OpenAI, Ollama, or Gemini):"
    read -rsp "LLM_API_KEY: " LLM_API_KEY
    echo

    # Write the LLM_API_KEY to the .env file
    echo "LLM_API_KEY=$LLM_API_KEY" > "$ENV_FILE"

    echo_info ".env file has been set up successfully."
else
    echo_info ".env file already exists. Skipping setup."
fi

# Step 15: Create Shell Script to Run the Python Script
echo_info "Creating shell script for automated execution..."

CRON_SCRIPT_PATH="$CRON_SCRIPT"

cat <<EOL > "$CRON_SCRIPT_PATH"
#!/bin/bash

# Auto_Jobs_Applier_AIHawk Cron Job Script

# Redirect all output to cron.log
exec >> "$CRON_LOG" 2>&1

# Insert a timestamp
echo "----- \$(date) -----"

# Navigate to the project directory
cd "$PROJECT_DIR" || { echo "Failed to navigate to project directory"; exit 1; }

# Activate the virtual environment
source "$VENV_DIR/bin/activate" || { echo "Failed to activate virtual environment"; exit 1; }

# Run the Python script with the resume
python main.py || { echo "Python main script failed"; exit 1; }

# Deactivate the virtual environment
deactivate

echo "Script executed successfully."
EOL

# Make the shell script executable
chmod +x "$CRON_SCRIPT_PATH"

# Step 16: Set Up Cron Job with flock to Prevent Multiple Instances
echo_info "Setting up cron job for automated script execution..."

# Ensure the log directory exists
mkdir -p "$(dirname "$CRON_LOG")"

# Ensure the cron script is executable
chmod +x "$CRON_SCRIPT_PATH"

# Define the cron job line with flock, ensuring all paths are properly quoted
CRON_JOB="1 * * * * /usr/bin/flock -n /tmp/run_auto_jobs.lock \"$CRON_SCRIPT_PATH\" >> \"$CRON_LOG\" 2>&1"

# Add the cron job if it doesn't already exist
if (crontab -l 2>/dev/null | grep -Fv "$CRON_SCRIPT_PATH" ; echo "$CRON_JOB") | crontab -; then
    echo_info "Cron job has been set up to run every hour with flock."
else
    echo_error "Failed to set up cron job."
    exit 1
fi

# Step 17: Create Resumes Directory and Instruct User to Add Resume
echo_info "Setting up resumes directory..."

# Create resumes directory if it doesn't exist
mkdir -p "$RESUME_DIR"

# Step 18: Final Instructions
echo_info ""
echo_info "========================================"
echo_info "      Installation and Setup Complete   "
echo_info "========================================"
echo_info "🚀 Next Steps 🚀"
echo_info "1. Place your HTML resume in: $RESUME_DIR"
echo_info "2. Review and update configuration files, config.yaml and plain_text_resume.yaml."
echo_info "3. Run the application manually: $CRON_SCRIPT_PATH. Log in to LinkedIn if prompted."
echo_info "4. Cron job executes hourly if configured."
echo_info "📂 Monitor logs at: $CRON_LOG"
echo_info "🔄 Activate virtual env: source $VENV_DIR/bin/activate"
echo_info "=== You're All Set! ==="

# Deactivate the virtual environment before exiting the script
deactivate


# Modify the Code to Remove Interactive Prompt
# ./virtual/lib/python3.10/site-packages/lib_resume_builder_AIHawk/manager_facade.py

# def choose_style(self):
#     styles = self.style_manager.get_styles()
#     if not styles:
#         print("No styles available")
#         return None
#     final_style_choice = "Create your resume style in CSS"
#     formatted_choices = self.style_manager.format_choices(styles)
#     formatted_choices.append(final_style_choice)
#     if formatted_choices:
#         selected_choice = formatted_choices[0]  # Automatically select the first style
#         print(f"Selected default style: {selected_choice}")
#     else:
#         selected_choice = final_style_choice