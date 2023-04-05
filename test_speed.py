#!/usr/bin/env python3

import subprocess
from typing import List, Tuple
import logging
import os
import sys
import re
from collections import namedtuple
import argparse

USBDev = namedtuple("USBDev", "bus device vendor product name")
skip_usb: List[re.Pattern] = [
    re.compile(r"\bhub\b", re.IGNORECASE),
    re.compile(r"\bbluetooth\b", re.IGNORECASE),
]


def get_usb_devices() -> List[USBDev]:
    out = subprocess.check_output(["/usr/bin/lsusb"]).decode()
    # Bus 004 Device 008: ID 0781:5583 SanDisk Corp. Ultra Fit
    ret = []
    for line in out.splitlines():
        # logging.debug("Processing line %s", line)

        tokens = line.split()
        bus, device = tokens[1], tokens[3][:-1]
        vendor, product = tokens[5].split(":")
        usbdev = USBDev(
            bus=bus,
            device=device,
            vendor=vendor,
            product=product,
            name=" ".join(tokens[6:]),
        )

        logging.debug("device=%s", usbdev)

        if any(pat.search(line) for pat in skip_usb):
            logging.debug("Skipping device as it matches skip pattern")
            continue
        ret.append(usbdev)
    return ret


def choose_device(devices: List[USBDev]) -> USBDev:
    choice = -1
    while choice not in range(1, len(devices) + 1):
        for i, d in enumerate(devices):
            print(f"{i+1}) {d.name}")
        print()
        userc = input("Test device number? (SPACE to exit) > ").strip()
        print()
        if userc == "":
            sys.exit(1)
        try:
            choice = int(userc)
        except Exception as e:
            logging.error("Invalid entry %s", userc)
            choice = -1
    return devices[choice - 1]


def main():
    if os.geteuid() != 0:
        logging.critical("This needs to be run as root. Use sudo!")
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", "-d", action="store_true", help="Debug messages")
    args = parser.parse_args()

    logging.basicConfig(
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        level=logging.INFO if not args.debug else logging.DEBUG,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    devices = get_usb_devices()
    if not devices:
        return
    logging.debug("Devices: %s", devices)
    device = choose_device(devices)
    logging.info("Testing device %s", device)


if __name__ == "__main__":
    main()
