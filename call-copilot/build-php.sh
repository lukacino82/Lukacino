#!/bin/sh
# Sestaví složku dist/copilot/ k nahrání přes FTP (např. do rentez.eu/copilot/).
set -e
cd "$(dirname "$0")"
rm -rf dist && mkdir -p dist/copilot/knowledge
cp public/index.html prompt.txt dist/copilot/
cp php/api.php php/.htaccess php/config.sample.php dist/copilot/
cp php/knowledge.htaccess dist/copilot/knowledge/.htaccess
cp knowledge/*.md dist/copilot/knowledge/ 2>/dev/null || true
echo "Hotovo: $(pwd)/dist/copilot  → nahraj na FTP, zkopíruj config.sample.php na config.php a vyplň."
