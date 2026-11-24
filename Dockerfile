# Container for the self-contained AuthRefine checks. Build from this directory:
#   docker build -t authrefine .
#   docker run --rm -v /path/to/liberation-fonts-ttf-2.1.5:/fonts:ro \
#       -e AUTHREFINE_TEXMF=/fonts authrefine
# The image contains no fonts; the figure step of the core profile needs the
# Liberation Serif 2.1.5 TrueType files mounted and named by AUTHREFINE_TEXMF.
FROM python:3.12-slim
LABEL org.opencontainers.image.title="AuthRefine research artifact" \
      org.opencontainers.image.licenses="MIT"
WORKDIR /opt/authrefine
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 LC_ALL=C.UTF-8 LANG=C.UTF-8 TZ=UTC
RUN pip install --no-cache-dir PyMuPDF==1.26.7 reportlab==4.4.9
COPY . .
CMD ["python3", "-B", "review.py", "--scope", "core", "--output", "/tmp/authrefine-evidence/review"]
