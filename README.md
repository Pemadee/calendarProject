## Development Guide

This section provides instructions for setting up and working with the project for development purposes.

### Prerequisites

- Python 3.11 
- SQLite
- Docker (optional, for containerization)
- Git

### Environment Setup

1. Clone the repository:
   ```bash
   git clone https://gitlab.com/botnoi-fazwaz/backend-fazwaz/backend.git
   cd backend
   git checkout staging
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:

   **These variables are also already set in the .env file and docker-compose.yml of the project.**
   ```bash

   # Application environment
   export BASE_URL = ...  //Use server url (botnoi domain)

   #Google Cloud Console Cridential
   export CLIENT_SECRET_FILE = client_secret_736997996838-k40bdk0dc4uh90ic5d8km1l46dsddnh2.appsgoogleusercontent.com.json
   
   #Google Sheet Token
   export CREDENTIALS_GOOGLE_SHEET = inlaid-agility-459107-r8-b1df210116d7.json
   export SPREADSHEET_ID = 12KyhW9pbDgXvWGUEpF98mOKxm7EsQk33O_UtegZHp5E

   ```

### Building and Running Locally


1. Run the application:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

### Containerization

To build a Docker locally:
```bash
docker build  .
```

To run the containerized application:
```bash
docker compose up
```

## API Reference

The service provides a gRPC and REST API for uploading member CSV files.

### Base URL
```
...  //Use server url (botnoi domain)

```


