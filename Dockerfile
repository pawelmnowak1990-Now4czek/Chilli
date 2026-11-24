FROM python:3.12-slim

WORKDIR /srv

# Dependencies first: this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The embedding model (about 120 MB) is downloaded when the image is built, not when the service
# starts: startup is fast and does not depend on Hugging Face being available. We copy only
# three files, so changes in the rest of the code do not force the model to be downloaded again.
COPY app/__init__.py app/config.py app/embeddings.py ./app/
RUN python -c "from app import embeddings; embeddings.warm_up()"

COPY app ./app
# Database schema: the service runs it at startup to add new columns (app/db.py).
COPY db ./db

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
