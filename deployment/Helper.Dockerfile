ARG HELPER_VERSION=1.0.18
FROM ghcr.io/coollabsio/coolify-helper:${HELPER_VERSION}
# The default Singapore GitHub endpoint times out from this server. This is a
# verified GitHub endpoint, with HTTPS hostname/certificate validation retained.
# Remove/refresh this route when connectivity changes; do not disable TLS checks.
RUN git config --system http.curloptResolve github.com:443:140.82.114.3 \
    && git config --system http.version HTTP/1.1 \
    && git config --system http.lowSpeedLimit 100 \
    && git config --system http.lowSpeedTime 60
COPY --chmod=0755 git-wrapper /usr/local/bin/git
COPY --chmod=0755 docker-wrapper /usr/local/bin/docker
