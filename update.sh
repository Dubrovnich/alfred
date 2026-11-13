#!/bin/sh
# Pull the latest Alfred and restart it. Run on the server:  ~/alfred/update.sh
set -e
cd "$(dirname "$0")"
git pull --ff-only
.venv/bin/pip install -q -r requirements.txt
mkdir -p ~/.config/systemd/user
cp deploy/alfred.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now alfred
systemctl --user restart alfred
sleep 2
curl -s http://127.0.0.1:8000/healthz && echo
echo "Alfred updated: $(git log -1 --format='%h %s')"
