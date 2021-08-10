FROM python:3.9.6-slim-buster

RUN python -m pip install --upgrade pip && pip install --upgrade setuptools

RUN mkdir /Comrade-major-bot
WORKDIR /Comrade-major-bot

COPY ./requirements.txt /Comrade-major-bot/requirements.txt

RUN pip install -r requirements.txt

CMD ["python", "./com_major.py"]