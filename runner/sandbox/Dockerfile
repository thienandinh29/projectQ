# The sandbox image: Python and the harness only. No pip, no compilers, a non-root user.
FROM python:3.12-slim
RUN rm -rf /usr/local/bin/pip* /usr/local/lib/python3.12/ensurepip \
    /usr/local/lib/python3.12/site-packages/pip* \
 && mkdir -p /opt/harness
COPY harness.py /opt/harness/harness.py
USER 65534:65534
WORKDIR /tmp
# Start from an empty environment: nothing from the image or the host leaks into learner code.
ENTRYPOINT ["/usr/bin/env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "LANG=C.UTF-8", \
    "python", "-I", "/opt/harness/harness.py"]
