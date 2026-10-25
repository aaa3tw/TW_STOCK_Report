FROM python:3.11-slim

WORKDIR /app

# 安裝系統與 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 複製所有代碼
COPY . .

# 設定環境變數與端口
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
EXPOSE 8080

# 啟動決策儀表板服務
CMD ["python", "dashboard/server.py"]
