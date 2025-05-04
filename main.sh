#!/bin/bash

# Check if we're in a git repository
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Error: Not in a git repository"
    exit 1
fi

# Add all changes
git add .

# Get commit message from user (or use default)
if [ -z "$1" ]; then
    COMMIT_MSG="Update: $(date)"
else
    COMMIT_MSG="$1"
fi

# Commit changes
git commit -m "$COMMIT_MSG"

# Push to default branch (assumes origin is set up)
git push origin $(git branch --show-current)

# Check if push was successful
if [ $? -eq 0 ]; then
    echo "Successfully pushed to GitHub"
else
    echo "Error: Failed to push to GitHub"
    exit 1
fi