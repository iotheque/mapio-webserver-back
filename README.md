# mapio_webserver_back

![PyPI - Python Version](https://img.shields.io/pypi/pyversions/sapling)
![GitHub tag (with filter)](https://img.shields.io/github/v/tag/pcurt/mapio-webserver-back)
![PDM](https://img.shields.io/badge/pdm-managed-blueviolet)
![Black](https://img.shields.io/badge/code_style-black-000000)
![Isort](https://img.shields.io/badge/imports-isort-1674b1?labelColor=ef8336)
![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)
[![Checked with pyright](https://microsoft.github.io/pyright/img/pyright_badge.svg)](https://microsoft.github.io/pyright/)
![Pre Commit](https://img.shields.io/badge/pre_commit-enabled-brightgreen?logo=pre-commit)

A Python project based on the Seedlings template

- [Usage](#usage)
- [Installation](#installation)
  - [With `pipx`](#with-pipx)
  - [With a `.pex` executable](#with-a-pex-executable)
  - [With `pip`, from a release version](#with-pip-from-a-release-version)
  - [With `pip`, from sources](#with-pip-from-sources)
- [Development Quickstart](#development-quickstart)

## Usage

Start the API on port 8456:

```sh
MAPIO_API_TOKEN=change-me mapio_webserver_back app
```

Environment variables:

- `MAPIO_API_TOKEN`: bearer token required by every endpoint (the API is
  unprotected when not set)
- `MAPIO_CORS_ORIGINS`: comma-separated allowed origins, `*` by default
- `MAPIO_COMPOSE_FILE`: path of the docker-compose file
- `MAPIO_TOOLS_DIR`: folder holding the `docker_*.sh` helper scripts

## Installation

Installing this package can be achieved in multiple ways.

### With `pipx`

[`pipx`](https://pypa.github.io/pipx/) is the recommended install method if you
want to install the CLI provided by this package on your system, have it
accessible anywhere, and not have to mess with `virtualenv`s.

Once you have `pipx` installed on your machine, you can proceed with installing
this package.

- If this package is available on a Pip repository (e.g.
  [pypi.org](https://pypi.org)), then you can simply run:

```sh
pipx install mapio_webserver_back
```

- If you want to install it directly from the repository:

```sh
pipx install git+https://github.com/pcurt/mapio_webserver_back
```

- If you downloaded a `.whl` or `.tar.gz` archive from the releases:

```sh
# Prebuilt wheel
pipx install mapio_webserver_back-${VERSION}-py3-none-any.whl
# Tarball
pipx install mapio_webserver_back-${VERSION}.tar.gz
```

where `$VERSION` is the version of the package you downloaded.

### With a `.pex` executable

[`pex`](https://pex.readthedocs.io/en/latest/) is an executable Python
virtualenv format, that can be executed on any machine that provides a suitable
Python interpreter.

To install the CLI provided by `mapio_webserver_back`, download the `.pex` files
of the latest release, and copy them somewhere in your `$PATH` (on Linux,
`~/.local/bin` is often a good idea). The executables will then be available in
your shell.

### With `pip`, from a release version

If you do not wish to use the methods above, you can use `pip` instead. The same
instructions as for `pipx` apply. However, remember to always run your `pip`
commands from inside a `virtualenv`, to avoid polluting your system packages.

### With `pip`, from sources

If you want to install this project from source, you will need to first download
them. For this, you can either download a release tarball, or directly clone
this repository.

Make sure you have a virtualenv activated to install this package.

You can then enter the project directory (with `cd mapio_webserver_back/`), and
install the project with:

``` sh
pip install .
```

## Development Quickstart

A quickstart guide/cheatsheet is [available here](./readme/Quickstart.md), it
lists how to use the development tools for this project.
