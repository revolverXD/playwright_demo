# Intro
- Playwright automation practice repo
- Runs against https://practice-automation.com by default
- To run against a saved copy of the site instead, set APP_URL to where you serve it, e.g.
  `APP_URL="http://127.0.0.1:8091"` with `python3 -m http.server 8091 -d <saved site>`.
  The saved copy needs the original layout (`/assets/form-fields_index.html`), the public site uses `/form-fields`.
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

# Jenkins
- Build the docker image
```
sudo docker build -t local-jenkins .
```
- Bring up the jenkins appliance
```
docker compose up -d
```
