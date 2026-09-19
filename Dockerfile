FROM python:3.11-slim

WORKDIR /usr/app
ENV PYTHONPATH=/usr/app

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY data_products /usr/app/data_products
COPY utils /usr/app/utils
COPY user_tests /usr/app/user_tests

WORKDIR /usr/app/data_products
