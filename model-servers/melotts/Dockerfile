FROM voice-app-torch-base:latest

RUN pip install --no-cache-dir git+https://github.com/myshell-ai/MeloTTS.git \
    && python -m unidic download

COPY server.py .
