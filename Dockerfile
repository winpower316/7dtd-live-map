FROM nginx:1.29-alpine

RUN mkdir -p /var/cache/nginx/map \
    && chown -R nginx:nginx /var/cache/nginx

COPY nginx.conf /etc/nginx/nginx.conf.template
COPY config/frontend-config.js.template /etc/nginx/frontend-config.js.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
COPY site/ /usr/share/nginx/html/

RUN chmod 755 /docker-entrypoint.sh

USER nginx

EXPOSE 8080

CMD ["/docker-entrypoint.sh"]
