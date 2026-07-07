#!/bin/bash
# Exit immediately if a command exits with a non-zero status
set -e

echo "=== Preparing Deployment for Hugging Face Spaces ==="

# 1. Ensure we are on the main branch
git checkout main

# 2. Cleanup any pre-existing temporary branches from previous failed runs
echo "Cleaning up old temporary release branches..."
git branch -D hf-release-temp 2>/dev/null || true
git branch -D hf-deploy 2>/dev/null || true
git branch -D hf-deploy2 2>/dev/null || true

# 3. Create a temporary orphan branch (clean slate, no history)
echo "Creating clean temporary release branch..."
git checkout --orphan hf-release-temp

# Clear the index copied from main so .gitignore is fully respected
git rm -rf --cached . --quiet

# 4. Add all files (this respects .gitignore, so the 63MB ONNX files and other ignored files are excluded!)
git add -A


# 5. Commit the files
git commit -m "Deploy build to Hugging Face Spaces"

# 6. Push this clean commit directly to HF Space's main branch
echo "Pushing code to Hugging Face Space..."
git push hf hf-release-temp:main --force

# 7. Switch back to main branch
git checkout main

# 8. Clean up the temporary branch
git branch -D hf-release-temp

echo "=== Successfully deployed to Hugging Face Spaces! ==="
