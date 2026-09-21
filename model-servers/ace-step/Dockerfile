FROM voice-app-torch-base:latest

RUN pip install --no-cache-dir git+https://github.com/ace-step/ACE-Step.git

COPY server.py .

EXPOSE 7860

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
