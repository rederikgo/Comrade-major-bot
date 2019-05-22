FROM python:3.7.3-slim-stretch

RUN python -m pip install --upgrade pip && pip install --upgrade setuptools

RUN mkdir /Comrade-major-bot
WORKDIR /Comrade-major-bot

COPY ./requirements.txt /Comrade-major-bot/requirements.txt

RUN pip install -r requirements.txt

CMD ["python", "./com_major.py"]