FROM frolvlad/alpine-python3

RUN apk add git

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir --prefer-binary .

ENTRYPOINT ["srcdsknight"]
