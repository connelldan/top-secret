#!/bin/bash

cd ~/projects/top-secret

# Check if we're in a git repository
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Error: Not in a git repository"
    exit 1
fi

# Check if there are any changes
if git diff-index --quiet HEAD -- && [ -z "$(git status --porcelain)" ]; then
    # No changes, create/update a timestamp file
    echo "Timestamp: $(date)" > .last_commit_timestamp
    git add .last_commit_timestamp
else
    # Add all changes
    git add .
fi

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