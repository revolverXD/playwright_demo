# Env creation
```bash
distrobox create --name playwright_test --image ubuntu:24.04
distrobox enter playwright_test
sudo apt update && sudo apt install -y python3 python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium
```
