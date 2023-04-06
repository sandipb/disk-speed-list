#!/usr/bin/env python3
# Following: https://linuxreviews.org/HOWTO_Test_Disk_I/O_Performance
import subprocess
from typing import List, Tuple, Any
import logging
import os
import sys
import re
from collections import namedtuple
import argparse
from dataclasses import dataclass
from pathlib import PosixPath
import time
from enum import Enum, auto
from datetime import datetime
import signal


class Timer:
    def __init__(self, func_name: str = "function"):
        self.start = datetime.now()
        self.func_name = func_name

    def __enter__(self):
        self.start = datetime.now()

    def __exit__(self, *_):
        logging.debug(f"'{self.func_name}' took {datetime.now() - self.start}")


@dataclass
class HDParmResult:
    cached: str = ""
    disk: str = ""


@dataclass
class USBDev:
    bus: str
    device: str
    vendor: str
    model: str
    name: str


class DiskTest(Enum):
    READ = "read"
    WRITE = "write"


# Additional flags to pass to dd
# conv=fsync: single fsync at end of command
# oflag=direct: bypass caches
DD_FLAGS_WRITE = "oflag=direct conv=fsync"
DD_FLAGS_READ = "oflag=direct"

DDTestSpec = namedtuple("DDTestSpec", "desc block count")


class DDTest(Enum):
    T64M = DDTestSpec("DD: 64M blocks for a total of 1G", "64M", 1024 // 64)
    T1M = DDTestSpec("DD: 1M blocks for a total of 1G", "1M", 1024)
    T4K = DDTestSpec("DD: 4K blocks for a total of 1M", "4K", 1024 // 4)


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
        vendor, model = tokens[5].split(":")
        usbdev = USBDev(
            bus=bus,
            device=device,
            vendor=vendor,
            model=model,
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


def device_for_path(path: PosixPath) -> str:
    "Find the device mounted on the path"
    command = ["/usr/bin/findmnt", "-no", "SOURCE", "--target", str(path)]
    logging.debug("Executing %s", command)
    return subprocess.check_output(command).decode().strip()


def model_for_device(device: str) -> str:
    "Find the model property for given device"
    command = f"/usr/bin/udevadm info {device} --query=property"
    logging.debug("Executing %s", command)
    output = subprocess.check_output(command.split()).decode()
    for line in output.splitlines():
        if line.startswith("ID_MODEL="):
            return line.split("=", 1)[1]
    return ""


def assert_root():
    if os.geteuid() != 0:
        logging.critical("This needs to be run as root. Use sudo!")
        sys.exit(1)


def run_hdparm(device: str) -> HDParmResult:
    "Run hdparm read test and return results"
    command = f"sudo /usr/sbin/hdparm -Tt --direct {device}"
    logging.debug("Executing %s", command)
    output = subprocess.check_output(command.split()).decode()
    result = HDParmResult()
    for line in output.splitlines():
        line = line.strip()
        if "Timing O_DIRECT cached reads" in line:
            # Timing O_DIRECT cached reads:   242 MB in  2.01 seconds = 120.36 MB/sec
            result.cached = line.split("=")[1].strip()
        if "Timing O_DIRECT disk reads" in line:
            # Timing O_DIRECT disk reads: 438 MB in  3.01 seconds = 145.61 MB/sec
            result.disk = line.split("=")[1].strip()
    return result


def test_file_name(path: PosixPath) -> PosixPath:
    test_file_name = "dd-test-" + time.strftime("%Y-%m-%d-%H-%M-%S")
    test_file_path = path / test_file_name
    return test_file_path


def run_dd(path: PosixPath, test_type: DiskTest, test_size: DDTest) -> str:
    test_file = test_file_name(path)
    if test_type == DiskTest.WRITE:
        return run_dd_write(test_file, test_size.value, clean=True)
    elif test_type == DiskTest.READ:
        run_dd_write(test_file, DDTest.T64M.value, clean=False)
        return run_dd_read(test_file, test_size.value, clean=True)
    raise Exception("test not supported")


def run_dd_write(test_file: PosixPath, test_size: DDTestSpec, clean: bool = True) -> str:
    "Run dd write test and return results"

    command = (
        f"sudo /usr/bin/dd if=/dev/zero of={test_file} bs={test_size.block} count={test_size.count} {DD_FLAGS_WRITE}"
    )
    logging.debug("Executing %s", command)
    output = ""
    try:
        output = subprocess.check_output(command.split(), stderr=subprocess.STDOUT).decode()
    except Exception as e:
        logging.exception("Could not write to test file %s", test_file)
        sys.exit(1)
    finally:
        if clean and test_file.exists():
            subprocess.run(["sudo", "rm", "-f", test_file], check=True)
            logging.debug("Deleted %s", test_file)

    last = (output.splitlines())[-1]
    return last.split(", ")[-1]


def run_dd_read(test_file: PosixPath, test_size: DDTestSpec, clean: bool = True) -> str:
    "Run dd read test and return results"

    if not test_file.exists():
        raise ValueError("No test file present to read: %s", test_file)

    command_drop_caches = f"echo 3 | sudo tee /proc/sys/vm/drop_caches"
    command = f"sudo /usr/bin/dd if={test_file} of=/dev/zero bs={test_size.block} count={test_size.count}"
    output = ""
    try:
        logging.debug("Dropping cache: %s", command_drop_caches)
        subprocess.check_output(command_drop_caches, shell=True)
        logging.debug("Executing: %s", command)
        output = subprocess.check_output(command.split(), stderr=subprocess.STDOUT).decode()
    except Exception as e:
        logging.exception("Could not write to test file %s", test_file)
        sys.exit(1)
    finally:
        if clean and test_file.exists():
            subprocess.run(["sudo", "rm", "-f", test_file], check=True)
            logging.debug("Deleted %s", test_file)

    last = (output.splitlines())[-1]
    return last.split(", ")[-1]


def run_tests(device: str, mount_path: PosixPath):
    with Timer("hdparm test"):
        hdparm = run_hdparm(device)
        print(f"READ: hdparm o_direct cached =", hdparm.cached)
        print(f"READ: hdparm o_direct disk =", hdparm.disk)

    for test in [DDTest.T64M, DDTest.T1M, DDTest.T4K]:
        with Timer(test.value.desc):
            dd_out = run_dd(mount_path, DiskTest.WRITE, test)
            print(f"WRITE: {test.value.desc} =", dd_out)

    for test in [DDTest.T64M, DDTest.T1M, DDTest.T4K]:
        with Timer(test.value.desc):
            dd_out = run_dd(mount_path, DiskTest.READ, test)
            print(f"READ: {test.value.desc} =", dd_out)


def main():
    signal.signal(signal.SIGINT, exit_quietly)
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", "-d", action="store_true", help="Debug messages")
    parser.add_argument("--yes", "-y", action="store_true", help="Accept the discovered device")
    parser.add_argument("mount_path", help="Path to a writable mountable location of the device")
    args = parser.parse_args()

    logging.basicConfig(
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        level=logging.INFO if not args.debug else logging.DEBUG,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    mount_path = PosixPath(args.mount_path).resolve()
    if not mount_path.exists():
        logging.critical("%s does not exit", mount_path)
        sys.exit(1)
    # devices = get_usb_devices()
    # if not devices:
    #     return
    # logging.debug("Devices: %s", devices)
    # device = choose_device(devices)
    # logging.info("Testing device %s", device)
    try:
        device = device_for_path(mount_path)
        model = model_for_device(device)
        ans = "" if not args.yes else "y"
        while ans not in ["y", "n"]:
            ans = input(f"Test device '{device} ({model})'? (Y/n) > ").strip().lower()[:1]
            if not ans:
                ans = "y"
        if ans == "n":
            sys.exit(0)
    except Exception as e:
        logging.critical("Couldn't find device: %s", e)
        sys.exit(1)

    print(f"Testing device '{device} ({model})'\n")
    run_tests(device=device, mount_path=mount_path)


def exit_quietly(sig: int, *ignore: Any):
    sys.exit(0)


if __name__ == "__main__":
    main()
