ARG PYTHON_VERSION=3.12.2
ARG PDM_VERSION=2.29.2

FROM python:${PYTHON_VERSION}-slim as base
RUN addgroup --system --gid 1000 abc && \
    adduser \
    --uid 1000 \
    --shell /bin/sh \
    --ingroup abc \
    --disabled-password \
    abc
USER 1000:1000
ENV PATH="/home/abc/.local/bin:${PATH}"
WORKDIR /app


FROM base as base-pdm
ARG PDM_VERSION
RUN pip install --user --no-cache-dir pdm==${PDM_VERSION}
COPY --chown=abc:abc ./pyproject.toml /app/
COPY --chown=abc:abc ./pdm.lock /app/



FROM base-pdm as package-builder
COPY --chown=abc:abc ./src /app/src
RUN pdm build --no-sdist



FROM base-pdm as dependencies-installer
RUN pdm sync --production --no-self



FROM base as final
ENV PATH="/app/.venv/bin:${PATH}"
COPY --from=dependencies-installer /app/.venv/ /app/.venv/
COPY --from=package-builder /app/dist/mapio_webserver_back*.whl /app/
RUN pip --python "$(which python)" install --no-cache-dir --no-deps ./mapio_webserver_back*.whl

ENTRYPOINT [ "mapio_webserver_back" ]
