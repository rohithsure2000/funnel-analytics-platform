FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# This project runs on a real, licensed Kaggle dataset that is NOT bundled
# in this image (see data/README.md for the download link + citation).
# Mount your downloaded CSVs into /app/data/raw before running, e.g.:
#
#   docker build -t funnel-analytics .
#   docker run -p 8501:8501 -v $(pwd)/data/raw:/app/data/raw funnel-analytics
#
# The entrypoint below runs the ETL pipeline against whatever is mounted
# at data/raw, then starts the dashboard.

EXPOSE 8501

CMD ["sh", "-c", "python -m src.pipeline && streamlit run dashboard/app.py --server.address=0.0.0.0"]
