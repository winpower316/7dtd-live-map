FROM python:3.13-alpine

RUN addgroup -g 10001 -S playerauth \
    && adduser -u 10001 -S -D -H -G playerauth playerauth \
    && mkdir -p /data \
    && chown playerauth:playerauth /data

WORKDIR /app

COPY auth_gateway.py /app/auth_gateway.py
COPY generate_password_hash.py /app/generate_password_hash.py

USER playerauth

EXPOSE 8080

CMD ["python", "/app/auth_gateway.py"]
