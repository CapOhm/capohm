#!/bin/bash
echo "🔄 Updating Capohm..."

# Move to the Capohm folder
cd "$(dirname "$0")"

# Pull updates if you're using git (optional)
#if [ -d ".git" ]; then
#    git pull
#fi

# Make sure all scripts are executable
chmod +x *.sh

echo "✅ Update complete."
