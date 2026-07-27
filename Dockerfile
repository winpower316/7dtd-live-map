FROM nginx:1.29-alpine

RUN mkdir -p /var/cache/nginx/map \
    && chown -R nginx:nginx /var/cache/nginx

COPY nginx.conf /etc/nginx/nginx.conf.template
COPY site/ /usr/share/nginx/html/

USER nginx

EXPOSE 8080

CMD ["/bin/sh", "-c", "envsubst '${SEVEN_DAYS_HOST} ${SEVEN_DAYS_WEB_PORT}' < /etc/nginx/nginx.conf.template > /tmp/nginx.conf && exec nginx -c /tmp/nginx.conf -g 'daemon off;'"]
