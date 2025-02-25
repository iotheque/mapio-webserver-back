"""Define all flask endpoints called by frontend."""

# pyright: reportUnusedFunction=false

import json
import logging
import os
import time
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Any, Union

import yaml
from flask import Flask, Response, request
from flask_cors import CORS

YAML_FILE = "/home/root/mapio/docker-compose.yml"


class UpdateStatus(str, Enum):
    """Update status during an OTA update."""

    idle = "idle"
    updating = "updating"


update_status = UpdateStatus.idle


def create_app() -> Flask:
    """Create the app.

    Returns:
        Flask: The server
    """
    logger = logging.getLogger(__name__)
    logger.info("Create the app")

    app = Flask(__name__)
    # enable CORS
    CORS(app)  # Enable CORS for all routes

    # Set static data
    @app.context_processor
    def set_static_data() -> dict[str, str]:
        os_version = os.popen(
            "cat /etc/os-release | grep MAPIO_OS_VERSION_PRETTY | awk -F'=' '{print $2}'"  # noqa
        ).read()

        return {
            "os_version": os_version,
        }

    @app.route("/status", methods=["POST", "GET"])
    def status() -> dict[str, str]:
        """Main page for configuration wizard.

        Returns:
            str: The homepage page to select different actions
        """
        return {"status": update_status}

    @app.route("/version", methods=["GET"])
    def version() -> dict[str, str]:
        """Main page for configuration wizard.

        Returns:
            str: The homepage page to select different actions
        """
        os_version = os.popen(
            "cat /etc/os-release | grep MAPIO_OS_VERSION_PRETTY | awk -F'=' '{print $2}'"  # noqa
        ).read()

        return {
            "os_version": os_version,
        }

    @app.route("/wifi", methods=["POST", "GET"])
    def wifi() -> Response:
        """Wifi setup page.

        Returns:
            str: The setup wifi page
        """
        if request.method == "POST":
            logger.info("Setup WIFI network")
            data: Any = request.get_json()
            selected_wifi = data.get("selectedWifi")
            set_password = data.get("password")
            ssid = f'  ssid="{selected_wifi}"\n'
            password = f'  psk="{set_password}"\n'
            logger.info(f"ssid {ssid}")
            logger.info(f"password {password}")

            if password != "":
                # Replace existing file
                p = Path("/etc/wpa_supplicant/wpa_supplicant-wlan0.conf")
                file = Path.open(p, "w")
                file.writelines(
                    [
                        "ctrl_interface=/var/run/wpa_supplicant\n",
                        "ctrl_interface_group=0\n" "update_config=1\n",
                        "\n",
                        "network={\n",
                        ssid,
                        password,
                        "  key_mgmt=WPA-PSK\n",
                        "  proto=WPA2\n",
                        "  pairwise=CCMP TKIP\n",
                        "  group=CCMP TKIP\n",
                        "  scan_ssid=1\n",
                        "}\n",
                    ]
                )

                # Start wlan0 service
                os.popen("systemctl daemon-reload").read()  # noqa
                os.popen("systemctl stop wpa_supplicant-ap.service").read()  # noqa
                os.popen("systemctl enable --now wpa_supplicant.service").read()  # noqa
                time.sleep(5)  # Wait before enabling wlan0 service
                os.popen("systemctl enable wpa_supplicant@wlan0.service").read()  # noqa
                os.popen("systemctl restart wpa_supplicant@wlan0.service").read()  # noqa

        return Response(response="wifi", status=200)

    @app.route("/getScan")
    def getScan() -> str:
        """Wifi setup page.

        Returns:
            str: The setup wifi page
        """
        # scan with
        logger.info("getScan")
        os.popen("ifconfig wlan0 up").read()  # noqa
        output = os.popen(
            "iw wlan0 scan | grep SSID: | awk '{print $2}' | sed '/^$/d' | sort -u"  # noqa
        ).read()
        ssids: list[dict[str, str]] = []
        for line in output.splitlines():
            line = line.rstrip("\n")
            parsed_line = line.split(";")
            ssid = {"name": parsed_line[0]}
            ssids.append(ssid)

        logger.info(f"SSIDs : {ssids}")
        return json.dumps(ssids)

    @app.route("/compose", methods=["POST", "GET"])
    def compose() -> Union[str, Response]:
        """Docker setup page.

        Returns:
            str: The setup docker page
        """
        if request.method == "POST":
            data = request.form.to_dict().popitem()[0]
            json_data: Any = json.loads(data) if data else None
            logger.info(f"data extract is {json_data}")
            services = json_data.get("selectedServices")
            logger.info(f"services {services}")
            for service in services:
                action: Any = json_data.get("select_action")
                if action == "pull":
                    os.popen(f"docker compose -f {YAML_FILE} pull {service.lower()}").read()  # noqa
                    os.popen(
                        f"docker compose -f {YAML_FILE} up -d --force-recreate {service.lower()}"  # noqa
                    ).read()
                    os.popen("docker system prune -f").read()  # noqa
                elif action == "create":
                    os.popen(
                        f"docker compose -f {YAML_FILE} up -d --force-recreate {service.lower()}"  # noqa
                    ).read()
                else:
                    logger.error(f"Unknown action {action}")
                logger.info(f"docker {action} {service.lower()}")

            return Response(response="docker", status=200)

        if request.method == "GET":
            logger.debug("getDocker")

            containers: list[dict[str, str]] = []
            with Path.open(Path("/home/root/mapio/docker-compose.yml"), "r") as file:
                compose_data = yaml.safe_load(file)
                for service, config in compose_data.get("services", {}).items():
                    image = config.get("image", "None")
                    name = image.split(":")[0]
                    version = image.split(":")[-1] if ":" in image else "latest"
                    container = {"name": service, "image": name, "version": version}
                    containers.append(container)

            logger.debug(f"Containers : {containers}")
            return json.dumps(containers)

        return Response(response="docker", status=404)

    @app.route("/docker", methods=["POST", "GET"])
    def docker() -> Union[str, Response]:
        """Get Docker spectific running container.

        Returns:
            Response
        """
        if request.method == "POST":
            data = request.form.to_dict().popitem()[0]
            json_data: Any = json.loads(data) if data else None
            services = json_data.get("selectedServices")
            logger.info(f"services {services}")
            for service in services:
                action: Any = json_data.get("select_action")
                os.popen(f"docker {action} {service.lower()}").read()  # noqa

        if request.method == "GET":
            output = os.popen("docker ps -a --format '{{.Names}} {{.Status}}'").read()  # noqa
            containers: list[dict[str, str]] = []

            ports: Any = defaultdict(list)
            scan_port = os.popen("/home/root/tools/docker_scan_port.sh").read()  # noqa
            for line in scan_port.splitlines():
                line = line.rstrip("\n")
                name, port = line.split()
                ports[name].append(port)

            for line in output.splitlines():
                line = line.rstrip("\n")
                container_name = line.split(" ")[0]
                container = {
                    "name": container_name,
                    "status": line.split(" ")[1],
                    "port": ", ".join(map(str, ports[container_name])),
                }
                containers.append(container)

            logger.debug(f"containers {containers}")
            return json.dumps(containers)

        return Response(response="docker-custom", status=404)

    @app.route("/docker-update", methods=["GET"])
    def docker_update() -> Union[str, Response]:
        """Get Docker last version.

        Returns:
            Response
        """
        if request.method == "GET":
            containers: list[dict[str, str]] = []

            output = os.popen("/home/root/tools/docker_check_versions.sh").read()  # noqa
            for line in output.splitlines():
                line = line.rstrip("\n")
                container = {
                    "name": line.split(" ")[0],
                    "update": line.split(" ")[1],
                }
                containers.append(container)

            logger.debug(f"containers {containers}")
            return json.dumps(containers)

        return Response(response="docker-custom", status=404)

    @app.route("/update", methods=["POST", "GET"])
    def update() -> Response:
        """Update endpoint.

        Returns:
            Response: 200 if success, 404 otherwise
        """
        if request.method == "POST":
            logger.info(f"{request.files}")
            f: Any = request.files["bundle"]
            global update_status
            update_status = UpdateStatus.updating
            if f != "":
                f.save("/var/volatile/bundle.raucb")
                os.popen("rauc install /var/volatile/bundle.raucb").read()  # noqa
                os.popen("reboot").read()  # noqa

        return Response(response="update", status=200)

    @app.route("/ssh-setkey", methods=["POST", "GET"])
    def ssh_setkey() -> Response:
        """SSH add key endpoint.

        Returns:
            Response: 200 if success, 404 otherwise
        """
        if request.method == "POST":
            logger.info(f"{request.values}")
            key = request.values.get("userkey")
            if key != "":
                logger.info(f"Key is {key}")
                os.popen("mkdir -p ~/.ssh").read()  # noqa
                os.popen(f"echo {key} >> ~/.ssh/authorized_keys").read()  # noqa
                os.popen("chmod 600 ~/.ssh/authorized_keys").read()  # noqa

                return Response(response="ssh-setkey", status=200)

        return Response(response="ssh-setkey", status=404)

    @app.route("/logs", methods=["GET"])
    def logs():
        logger.info("getLogs")
        output = os.popen(
            'docker compose -f /home/root/mapio/docker-compose.yml logs --tail="20"'  # noqa
        ).read()
        logs: list[dict[str, str]] = []
        for line in output.splitlines():
            line = line.rstrip("\n")
            log = {"data": line}
            logs.append(log)

        logger.info(f"logs : {logs}")
        return json.dumps(logs)

    return app
