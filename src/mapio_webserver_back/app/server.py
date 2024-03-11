"""Define all flask endpoints called by frontend."""

# pyright: reportUnusedFunction=false

import json
import logging
import os
import subprocess
import time
from enum import Enum
from pathlib import Path
from typing import Any, Union

from flask import Flask, Response, request
from flask_cors import CORS


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
            "cat /etc/os-release | grep PRETTY_NAME | awk -F'\"' '{print $2}'"  # noqa
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
            "cat /etc/os-release | grep PRETTY_NAME | awk -F'\"' '{print $2}'"  # noqa
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
                os.popen("systemctl restart wpa_supplicant@wlan0.service").read()  # noqa
                os.popen("systemctl enable wpa_supplicant@wlan0.service").read()  # noqa

        return Response(response="wifi", status=200)

    @app.route("/getScan")
    def getScan() -> str:
        """Wifi setup page.

        Returns:
            str: The setup wifi page
        """
        # scan with
        logger.info("getScan")
        output = os.popen(
            "iw wlan0 scan | grep SSID: | awk '{print $2}' | sed '/^$/d'"  # noqa
        ).read()
        ssids: list[dict[str, str]] = []
        for line in output.splitlines():
            line = line.rstrip("\n")
            parsed_line = line.split(";")
            ssid = {"name": parsed_line[0]}
            ssids.append(ssid)

        logger.info(f"SSIDs : {ssids}")
        return json.dumps(ssids)

    @app.route("/docker", methods=["POST", "GET"])
    def docker() -> Union[str, Response]:
        """Docker setup page.

        Returns:
            str: The setup docker page
        """
        if request.method == "POST":
            data = request.form.to_dict(flat=False)
            extract_data: Any = json.loads(data.popitem()[0]) if data else None

            logger.info(f"data extract is {extract_data}")
            # Get asked action
            action = None
            for item in iter(extract_data):
                if item.get("action") is not None:
                    action = item.get("action")
                    logger.info(f"Asked action is : {action}")

            # Execute the action if needed
            for item in iter(extract_data):
                service: Any = item.get("service")
                if service is not None:
                    if item.get("selected"):
                        if action == "restart":
                            os.popen(
                                f"docker-compose -f /home/root/mapio/docker-compose.yml restart {service.lower()}"  # noqa
                            ).read()
                        elif action == "stop":
                            os.popen(
                                f"docker-compose -f /home/root/mapio/docker-compose.yml stop {service.lower()}"  # noqa
                            ).read()
                        elif action == "update":
                            os.popen(
                                f"docker-compose -f /home/root/mapio/docker-compose.yml \
 pull {service.lower()} && docker-compose -f /home/root/mapio/docker-compose.yml up -d --force-recreate {service.lower()}"  # noqa
                            ).read()
                        else:
                            logger.error("Unknown action")
            return Response(response="docker", status=200)

        if request.method == "GET":
            logger.info("getDocker")
            output = os.popen("docker ps --format '{{.Names}}'").read()  # noqa
            containers: list[dict[str, str]] = []
            for line in output.splitlines():
                line = line.rstrip("\n")
                container = {"name": line}
                containers.append(container)
            logger.info(f"Containers : {containers}")
            return json.dumps(containers)

        return Response(response="docker", status=404)

    @app.route("/docker-custom", methods=["POST", "GET"])
    def docker_custom() -> Union[str, Response]:
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
            for line in output.splitlines():
                line = line.rstrip("\n")
                container = {"name": line.split(" ")[0], "status": line.split(" ")[1]}
                containers.append(container)

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
                f.save("/tmp/bundle.raucb")  # noqa
                os.popen("rauc install /tmp/bundle.raucb").read()  # noqa
                os.popen("rm /boot/first_boot_done").read()  # noqa
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

    def stream_logs():
        process: Any = subprocess.Popen(
            [  # noqa
                "docker-compose",
                "-f",
                "/home/root/mapio/docker-compose.yml",
                "logs",
                "--tail=1000",
                "-f",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        while True:
            output = process.stdout.readline()
            if output == "" and process.poll() is not None:
                break
            if output:
                yield "data: " + output.rstrip() + "\n\n"
                time.sleep(0.01)

    @app.route("/logs", methods=["GET"])
    def logs():
        logger.info("logs")
        return Response(stream_logs(), mimetype="text/event-stream")

    return app
