FROM python:3.7 as build

ENV PYTHONUNBUFFERED 1

RUN useradd -m oioioi \
    && mkdir -p /sio2/sioworkers \
    && chown -R oioioi:oioioi /sio2

USER oioioi
WORKDIR /sio2

RUN pip install --user virtualenv \
    && /home/oioioi/.local/bin/virtualenv -p python3.7 venv

COPY --chown=oioioi:oioioi setup.py setup.cfg /sio2/sioworkers/
COPY --chown=oioioi:oioioi sio /sio2/sioworkers/sio
COPY --chown=oioioi:oioioi twisted /sio2/sioworkers/twisted

WORKDIR /sio2/sioworkers

RUN . /sio2/venv/bin/activate \
    && pip install .

FROM python:3.7 AS production

LABEL org.opencontainers.image.source=https://github.com/sio2project/sioworkers

ENV PYTHONUNBUFFERED 1

RUN useradd -m oioioi \
    && mkdir -p /sio2/sioworkers \
    && chown -R oioioi:oioioi /sio2

COPY --from=build --chown=oioioi:oioioi /sio2/venv /sio2/venv

COPY --chown=oioioi:oioioi config/supervisord.conf.example /sio2/sioworkers/config/supervisord.conf
COPY --chown=oioioi:oioioi config/supervisord-conf-vars.conf.docker /sio2/sioworkers/config/supervisord-conf-vars.conf
COPY --chown=oioioi:oioioi config/logging.json.example /sio2/sioworkers/config/logging.json
COPY --chown=oioioi:oioioi supervisor.sh /sio2/sioworkers

COPY --chown=oioioi:oioioi docker-entrypoint.sh /sio2

USER oioioi
WORKDIR /sio2/sioworkers

ENV SIOWORKERSD_HOST="web"

ENTRYPOINT [ "/sio2/docker-entrypoint.sh" ]

CMD [ "/sio2/sioworkers/supervisor.sh", "startfg" ]
