# IndiaPulse Full-Stack Website

## Deploy Live (Render / Railway)
1. Upload this folder to a GitHub repository.
2. Connect the repo to Render or Railway (it detects `Procfile` and `requirements.txt` automatically).
3. Open your live site URL, click **API & Add Data**, enter your Dhan Client ID, Access Token, and your live site URL in **API Endpoint**, then click **Connect & Render Live Data**.

## Run Locally
```bash
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```
Then open `http://localhost:8000`.
