# Container for the self-contained AuthRefine checks. Build from this directory:
#   docker build -t authrefine .
#   docker run --rm -v /path/to/times-new-roman:/fonts:ro \
#       -e AUTHREFINE_FONT_DIR=/fonts authrefine
# The image contains no Times New Roman files. Without the mounted files named
# in figures/figstyle.py, the figure step still runs every data check and
# compares the generated table rows, and reports PDF byte comparison as
# unavailable.
FROM python:3.12-slim
LABEL org.opencontainers.image.title="AuthRefine research artifact" \
      org.opencontainers.image.licenses="MIT"
WORKDIR /opt/authrefine
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 LC_ALL=C.UTF-8 LANG=C.UTF-8 TZ=UTC
COPY requirements-figures.txt /tmp/requirements-figures.txt
RUN pip install --no-cache-dir -r /tmp/requirements-figures.txt
COPY . .
CMD ["python3", "-B", "review.py", "--scope", "core", "--output", "/tmp/authrefine-evidence/review"]
