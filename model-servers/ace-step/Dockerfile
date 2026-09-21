FROM voice-app-torch-base:latest

RUN pip install --no-cache-dir git+https://github.com/ace-step/ACE-Step.git

# ACE-Step pulls torchvision from PyPI (CUDA build), whose C++ ops fail to
# register against the CPU-only torch in the base image ("operator
# torchvision::nms does not exist"). Swap in the matching CPU wheel.
# torchcodec: torchaudio 2.11 requires it to save audio files.
RUN pip install --no-cache-dir --force-reinstall --no-deps torchvision \
    --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir torchcodec \
    --index-url https://download.pytorch.org/whl/cpu

COPY server.py .

EXPOSE 7860

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
