#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
# -*- coding: utf-8 -*-
#

import glob
import json
import os
import pathlib
import random
import re
import logging
import time

try:
    from termcolor import colored as c
except ImportError:

    def c(text, color):
        return text


class FilesDict:
    file: pathlib.Path
    sidecar: list[pathlib.Path]


LOG = logging.getLogger(__name__)

RX_PAT = [
    # YY?YY(-._)MM(-._)DD -? series -? epNumber -? title
    r"^(?P<year>\d{2,4})(\-|\.|_)?(?P<month>\d{2})(\-|\.|_)?(?P<day>\d{2})\s-?(?P<series>.+?)(?P<epNumber>\#(\d+)|ep(\d+)|DVD[0-9.-]+|SP[0-9.-]+) -?(?P<title>.+)",
    # YY?YY(-._)MM(-._)DD -? title
    r"^(?P<year>\d{2,4})(\-|\.|_)?(?P<month>\d{2})(\-|\.|_)?(?P<day>\d{2})\s?-?(?P<title>.+)",
    # title YY?YY(-._)MM(-._)DD at end of filename.
    r"(?P<title>.+?)(?P<year>\d{2,4})(\-|\.|_)?(?P<month>\d{2})(\-|\.|_)?(?P<day>\d{2})$",
    # series - YY?YY(-._)MM(-._)DD -? title
    r"(?P<series>.+?)(?P<year>\d{2,4})(\-|\.|_)?(?P<month>\d{2})(\-|\.|_)?(?P<day>\d{2})\s?-?(?P<title>.+)?",
]

RX_LIST: list[re.Pattern] = []

for rx in RX_PAT:
    try:
        pat = re.compile(rx, re.IGNORECASE)
        RX_LIST.append(pat)
    except Exception as e:
        LOG.error("Error compiling default regex: " + str(rx) + " - " + str(e))


def getSideCarFiles(file: pathlib.Path) -> list[pathlib.Path]:
    """
    Get sidecar files for the given file.

    :param file: File to get sidecar files for.

    :return: List of sidecar files.
    """
    files = []

    for sub_file in file.parent.glob(f"{glob.escape(file.stem)}.*"):
        if (
            sub_file == file
            or sub_file.is_file() is False
            or sub_file.stem.startswith(".")
        ):
            continue

        files.append(sub_file)

    return files


def get_files(
    input: pathlib.Path, recursive: bool, extensions: list = [], sideCar: bool = True
) -> list[FilesDict]:
    """
    Get files from the input directory.

    :param input: Input directory.
    :param recursive: Recursively get files.

    :return: list of files.
    """
    if input.is_file():
        return [{"file": input, "sidecar": getSideCarFiles(input) if sideCar else []}]

    def natural_sort(items):
        def convert(text):
            return int(text) if text.isdigit() else text.lower()

        def alphanum_key(key):
            return [convert(c) for c in re.split("([0-9]+)", str(key))]

        return sorted(items, key=alphanum_key)

    files: list = []

    for filename in natural_sort(
        [item for item in input.glob("**/*.*" if recursive else "*.*")]
    ):
        file = pathlib.Path(filename)

        if file.is_file() is False or file.stem.startswith("."):
            LOG.debug(f"Skipping '{file}' as it's not a file or it's a hidden file.")
            continue

        if file.suffix[1:] not in extensions:
            LOG.debug(f"Skipping '{file}' as it's not in the extensions list.")
            continue

        files.append(
            {"file": file, "sidecar": getSideCarFiles(file) if sideCar else []}
        )

    return files


def get_date(match: re.Match, file: pathlib.Path) -> int | None:
    """
    Handle the regex match and return expected broadcast date.

    :param match: The regex match object.
    :param file: The file name.

    :return: int returns the episode number. Or None if it's not possible to get the episode number.
    """
    month = match.group("month")
    day = match.group("day")
    year = match.group("year")

    if not month or not day or not year:
        LOG.debug(f"Match: {match} is missing month, day or year.")
        return None

    if year and len(year) == 2:
        year = "20" + year

    episode = int("1" + match.group("month") + match.group("day"))

    if len(str(episode)) < 8:
        time_ts = None

        if file.with_suffix(".info.json").exists():
            with open(file.with_suffix(".info.json"), "r") as f:
                data = json.load(f)
                if data.get("epoch", None):
                    time_ts = time.gmtime(float(data.get("epoch")))

        if not time_ts:
            time_ts = time.gmtime(os.path.getmtime(file))

        episode = int("{}{:>02}{:>02}".format(episode, time_ts[4], time_ts[5]))

    return episode


def spread_mtime(
    files: list[FilesDict],
) -> None:
    for file in files:
        LOG.debug(f"Spreading mtime for file: '{file['file']}'.")
        realtime = os.path.getmtime(file["file"])
        # introduce a random factor to the time from 1s to 60s
        random_factor = random.randint(1, 600)
        mod_time = realtime + random_factor
        os.utime(
            file["file"],
            (
                mod_time,
                mod_time,
            ),
        )
        LOG.info(
            f"File: '{c(file['file'],'yellow')}'. mod time: '{c(realtime,'cyan')}' will be changed to: '{c(mod_time,'cyan')}' the factor was: '{c(random_factor,'cyan')}'."
        )


def fix_id(
    files: list[FilesDict],
) -> None:
    """
    Fix the mtime for files with the same mtime.

    :param files: List of files to fix.
    """

    mtime = {}

    for file in files:
        for rx in RX_LIST:
            file_ts = None
            match = rx.match(file["file"].stem)
            if not match:
                continue

            file_ts = get_date(match, file["file"])
            if not file_ts:
                continue

            if file_ts not in mtime:
                mtime[file_ts] = []

            mtime[file_ts].append(file["file"])
            break

    for key in mtime:
        if len(mtime[key]) < 2:
            continue

        LOG.info(f"Files with the same id: {key} - {len(mtime[key])}\n{mtime[key]}.")

        for index, file in enumerate(mtime[key]):
            if file.with_suffix(".info.json").exists():
                LOG.info(f"Updating inferred id for file: '{file}' with info.json.")
                with open(file.with_suffix(".info.json"), "r") as f:
                    data = json.load(f)
                if data.get("epoch", None):
                    data["epoch"] = data["epoch"] + index + random.randint(1, 600)
                    with open(file.with_suffix(".info.json"), "w") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                LOG.info(f"Updating inferred id for file: '{file}'.")
                file_mtime = os.path.getmtime(file) + index + random.randint(1, 600)
                os.utime(
                    file,
                    (
                        file_mtime,
                        file_mtime,
                    ),
                )


def cli():
    import argparse

    parser = argparse.ArgumentParser(
        description="jp_scanner util.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    opt_input = parser.add_argument_group("Input")
    opt_input.add_argument(
        "-r", "--recursive", action="store_true", help="Recursively get files."
    )
    opt_input.add_argument(
        "-i", "--input", type=str, help="Input directory.", default=os.getcwd()
    )
    opt_input.add_argument(
        "-e",
        "--extensions",
        nargs="+",
        default=list(["mp4", "mkv"]),
        help="Main extensions to scan for.",
    )

    opt_options = parser.add_argument_group("Options")
    opt_options.add_argument(
        "-m",
        "--min-files",
        type=int,
        help="Number of minium sidecar files.",
        default=2,
    )
    opt_options.add_argument(
        "-sm", "--spread-mtime", action="store_true", help="Increase file mod_time."
    )
    opt_options.add_argument(
        "-ui", "--update-id", action="store_true", help="Update Ids."
    )

    log_grp = parser.add_argument_group("Logging")
    log_grp.add_argument(
        "-q", "--quiet", action="store_true", help="Only show errors and higher."
    )
    log_grp.add_argument(
        "-v", "--verbose", action="store_true", help="Do not move files."
    )
    log_grp.add_argument(
        "-l",
        "--log",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level",
        default="INFO",
    )

    args = parser.parse_args().__dict__

    minFiles: int = int(args.get("min_files"))
    spreadMtime: bool = bool(args.get("spread_mtime"))
    updateId: bool = bool(args.get("update_id"))

    loglevel: str = "DEBUG" if args.get("verbose") else args.get("log")
    loglevel = "ERROR" if args.get("quiet", None) else loglevel
    numeric_level = getattr(logging, loglevel.upper(), None)
    try:
        import coloredlogs

        coloredlogs.install(
            level=numeric_level,
            datefmt="%H:%M:%S",
            fmt="%(asctime)s [%(levelname)-5.5s] %(message)s",
        )
    except ImportError:
        logging.basicConfig(
            level=numeric_level,
            datefmt="%H:%M:%S",
            format="%(asctime)s [%(levelname)-5.5s] %(message)s",
        )

    LOG = logging.getLogger(__name__)

    LOG.info(f"Getting files from: {args.get('input')}.")
    files = get_files(
        pathlib.Path(args.get("input")), args.get("recursive"), args.get("extensions")
    )

    if updateId:
        fix_id(files)
        exit(0)

    if spreadMtime:
        spread_mtime(files)
        exit(1)

    parsed = 0

    for file in files:
        parsed += 1
        if len(file["sidecar"]) >= minFiles:
            LOG.debug(
                f"File: {file['file']}, has '{minFiles}' or more sidecar files:\n{file['sidecar']}"
            )
            continue

        LOG.info(
            f"File: '{c(file['file'],'yellow')}'. has '{len(file['sidecar'])}' sidecar files which is lower then '{minFiles}'.\n{file['sidecar']}"
        )

    LOG.info(f"Total files parsed: '{c(parsed,'cyan')}'.")


if __name__ == "__main__":
    cli()
