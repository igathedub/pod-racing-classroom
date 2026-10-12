# No network is available at runtime; no third-party Python dependencies.
FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /runner
COPY --chmod=0444 boot.py /runner/boot.py
USER 65534:65534
ENTRYPOINT ["python", "-I", "-u", "/runner/boot.py"]
