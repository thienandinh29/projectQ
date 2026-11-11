# The runner service: a small HTTP server that starts one sandbox container per request.
# It talks to the host's Docker daemon through the mounted socket, which is powerful: run it as its
# own service, on a private network the API can reach, with RUNNER_TOKEN set (specs/code-sandbox).
FROM docker:27.5.1-cli AS dockercli

FROM python:3.12-slim
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
WORKDIR /app
COPY nodetrail_runner /app/nodetrail_runner
ENV RUNNER_HOST=0.0.0.0 RUNNER_PORT=8090
EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=3)"
CMD ["python", "-m", "nodetrail_runner.server"]
