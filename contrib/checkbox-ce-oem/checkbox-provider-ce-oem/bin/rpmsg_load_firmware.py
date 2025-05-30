#!/usr/bin/env python3
# This file is part of Checkbox.
#
# Copyright 2024 Canonical Ltd.
# Written by:
#   Stanley Huang <stanley.huang@canonical.com>
#
# Checkbox is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3,
# as published by the Free Software Foundation.
#
# Checkbox is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Checkbox. If not, see <http://www.gnu.org/licenses/>.

import sys
import re
import argparse
import time
import logging
import subprocess
from collections import OrderedDict
from pathlib import Path


class RpmsgLoadFirmwareTest:

    properties = ["firmware_path", "firmware_file", "rpmsg_state"]

    def __init__(self, remoteproc_dev: str):
        self._firmware_path = Path(
            "/sys/module/firmware_class/parameters/path"
        )
        self._firmware_file = Path(
            "/sys/class/remoteproc/{}/firmware".format(remoteproc_dev)
        )
        self._rpmsg_state = Path(
            "/sys/class/remoteproc/{}/state".format(remoteproc_dev)
        )
        self._search_patterns = {}
        self.expected_events = []

    def __enter__(self):
        self._setup()
        return self

    def __exit__(self, type, value, traceback):
        self._teardown()

    def _setup(self):
        self._previous_config = OrderedDict()
        for key in self.properties:
            self._previous_config.update({key: getattr(self, key)})

    def _teardown(self):
        self.rpmsg_state = "stop"
        self.firmware_path = self._previous_config["firmware_path"]
        self.firmware_file = self._previous_config["firmware_file"]
        if (
            self.firmware_file.strip() != "(null)"
            and self._previous_config["rpmsg_state"].strip() == "running"
        ):
            # start RPMSG again when firmware file been configured
            self.rpmsg_state = "start"

    @property
    def firmware_path(self) -> str:
        return self._firmware_path.read_text().strip()

    @firmware_path.setter
    def firmware_path(self, value: str) -> None:
        self._firmware_path.write_text(value)

    @property
    def firmware_file(self) -> str:
        return self._firmware_file.read_text()

    @firmware_file.setter
    def firmware_file(self, value: str) -> None:
        self._firmware_file.write_text(value)

    @property
    def rpmsg_state(self) -> str:
        """
        Reports the state of the remote processor, which will be one of:

        - "offline"
        - "suspended"
        - "running"
        - "crashed"
        - "invalid"

        "offline" means the remote processor is powered off.
        "suspended" means that the remote processor is suspended and
        must be woken to receive messages.
        "running" is the normal state of an available remote processor
        "crashed" indicates that a problem/crash has been detected on
        the remote processor.
        "invalid" is returned if the remote processor is in an
        unknown state.

        Returns:
            str: remote processor state
        """
        return self._rpmsg_state.read_text()

    @rpmsg_state.setter
    def rpmsg_state(self, value: str) -> None:
        """
        Writing this file controls the state of the remote processor.

        The following states can be written:
        - "start"
        - "stop"

        Writing "start" will attempt to start the processor running the
        firmware indicated by, or written to,
        /sys/class/remoteproc/.../firmware. The remote processor should
        transition to "running" state.

        Writing "stop" will attempt to halt the remote processor and
        return it to the "offline" state.

        Returns:
            None
        """
        if value not in ["start", "stop"]:
            raise ValueError("Unsupported value for remote processor state")
        self._rpmsg_state.write_text(value)

    @property
    def search_pattern(self) -> dict:
        return self._search_patterns

    @search_pattern.setter
    def search_pattern(self, patterns: dict) -> None:
        self._search_patterns.update(patterns)

    def _init_logger(self) -> None:
        self.log_reader = subprocess.Popen(
            ["journalctl", "-f"], stdout=subprocess.PIPE
        )

    def lookup_reload_logs(self, entry: str) -> bool:
        keep_looking = True
        for key, pattern in self._search_patterns.items():
            if re.search(pattern, entry):
                self.expected_events.append((key, entry))
                if key == "ready":
                    keep_looking = False
                    break

        return keep_looking

    def _monitor_journal_logs(self, lookup_func) -> None:
        start_time = time.time()
        logging.info("# start time: %s", start_time)

        while True:
            raw = self.log_reader.stdout.readline().decode()
            logging.info(raw)
            if raw and lookup_func(raw) is False:
                return
            cur_time = time.time()
            if (cur_time - start_time) > 60:
                return


def verify_load_firmware_logs(
    match_records: list, search_stages: list
) -> bool:
    logging.info("Validate RPMSG related log from journal logs")
    logging.debug(match_records)
    actuall_stage = []
    for record in match_records:
        if record[1]:
            actuall_stage.append(record[0])
        logging.info("%s stage: %s", record[0], record[1])

    return set(actuall_stage) == set(search_stages)


def load_firmware_test(args) -> None:
    remote_proc_dev = args.device
    target_path = args.path
    target_file = args.file

    proc_pattern = "remoteproc remoteproc[0-9]+"
    search_patterns = {
        "start": r"{}: powering up imx-rproc".format(proc_pattern),
        "boot_image": (r"{}: Booting fw image (?P<image>\w*.elf), \w*").format(
            proc_pattern
        ),
        # Please keep latest record in ready stage
        # This function will return if latest record been captured.
        "ready": (r"{}: remote processor imx-rproc is now up").format(
            proc_pattern
        ),
    }
    logging.info("# Start load M4 firmware test")
    with RpmsgLoadFirmwareTest(remote_proc_dev) as rpmsg_handler:
        rpmsg_handler.search_pattern = search_patterns
        rpmsg_handler._init_logger()
        if rpmsg_handler.rpmsg_state.strip() in [
            "running",
            "suspended",
            "invalid",
        ]:
            logging.info("Stop the Remote processor")
            rpmsg_handler.rpmsg_state = "stop"
        logging.info(
            "Configure the firmware file to %s and firmware path to %s",
            target_file,
            target_path,
        )
        rpmsg_handler.firmware_path = target_path
        rpmsg_handler.firmware_file = target_file
        logging.info("Start the Remote processor")
        rpmsg_handler.rpmsg_state = "start"
        rpmsg_handler._monitor_journal_logs(rpmsg_handler.lookup_reload_logs)
        rpmsg_handler.log_reader.kill()

        if verify_load_firmware_logs(
            rpmsg_handler.expected_events,
            rpmsg_handler._search_patterns.keys(),
        ):
            logging.info("# Reload M4 firmware successful")
        else:
            raise SystemExit("# Reload M4 firmware failed")

        # AI: will adding a feature to do testing after load M-core firmware
        # extra_testing = None
        # if extra_testing is not None:
        #    module_c = __import__(os.path.splitext(__file__)[0])
        #    getattr(module_c, extra_testing)()


def dump_firmware_test_mapping(args) -> None:
    firmware_mapping = args.mapping
    firmware_path = args.path
    pattern = r"(\w*):([\w\.-]*)"
    output_format = "device: {}\nfirmware: {}\npath: {}\n"

    re_result = re.findall(pattern, firmware_mapping)
    if not re_result or firmware_path.strip() == "":
        print(
            output_format.format(
                firmware_mapping, firmware_mapping, firmware_path
            )
        )
        return

    for data in re_result:
        print(output_format.format(data[0], data[1], firmware_path))


def register_arguments():
    parser = argparse.ArgumentParser(description="RPMSG reload firmware test")

    subparsers = parser.add_subparsers(dest="mode")
    reload_test_parser = subparsers.add_parser("test-reload")
    reload_test_parser.add_argument(
        "--device",
        help="The RPMSG device",
        type=str,
        required=True,
    )
    reload_test_parser.add_argument(
        "--path",
        help="The directory to store M-core ELF firmware",
        type=str,
        required=True,
    )
    reload_test_parser.add_argument(
        "--file", help="M-core ELF firmware file", required=True, type=str
    )
    # AI: will adding a feature to do testing after load M-core firmware
    # reload_test_parser.add_argument(
    #    "--extra-test",
    #    help="RPMSG functional tests",
    #    choices=["pingpong", "rpmsg-tty"],
    #    default=None,
    # )
    reload_test_parser.set_defaults(test_func=load_firmware_test)

    reload_res_test_parser = subparsers.add_parser("resource-reload")
    reload_res_test_parser.add_argument(
        "--mapping",
        help="The mapping with RPMSG node and M-Core firmware",
        type=str,
        required=True,
    )
    reload_res_test_parser.add_argument(
        "--path",
        help="The directory to store M-core ELF firmware",
        type=str,
        required=True,
    )
    reload_res_test_parser.set_defaults(test_func=dump_firmware_test_mapping)
    args = parser.parse_args()
    if args.mode is None:
        parser.print_help()
        exit(1)

    return args


if __name__ == "__main__":

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    logger_format = "%(asctime)s %(levelname)-8s %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Log DEBUG and INFO to stdout, others to stderr
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(logging.Formatter(logger_format, date_format))

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(logging.Formatter(logger_format, date_format))

    stdout_handler.setLevel(logging.DEBUG)
    stderr_handler.setLevel(logging.WARNING)

    # Add a filter to the stdout handler to limit log records to
    # INFO level and below
    stdout_handler.addFilter(lambda record: record.levelno <= logging.INFO)

    root_logger.addHandler(stderr_handler)
    root_logger.addHandler(stdout_handler)
    args = register_arguments()
    args.test_func(args)
