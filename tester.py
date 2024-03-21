#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
# -*- coding: utf-8 -*-
#

import logging
import os
import pathlib
import re
from utils import get_files, get_date, c, RX_PAT


def cli():
    import argparse

    parser = argparse.ArgumentParser(
        description="file name tester.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    opt_input = parser.add_argument_group("Input")
    opt_input.add_argument("-i", "--input", type=str, help="Input directory.", default=os.getcwd())
    opt_input.add_argument(
        "-e", "--extensions", nargs="+", default=list(['mp4', 'mkv']),
        help="Main extensions to scan for.")

    log_grp = parser.add_argument_group("Logging")
    log_grp.add_argument("-q", "--quiet", action="store_true", help='Only show errors and higher.')
    log_grp.add_argument("-v", "--verbose", action="store_true", help='Do not move files.')
    log_grp.add_argument("-l", "--log", type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                         help=f"Log level", default='INFO')

    args = parser.parse_args().__dict__

    loglevel: str = 'DEBUG' if args.get('verbose') else args.get('log')
    loglevel = 'ERROR' if args.get('quiet', None) else loglevel
    numeric_level = getattr(logging, loglevel.upper(), None)
    try:
        import coloredlogs
        coloredlogs.install(level=numeric_level, datefmt='%H:%M:%S',
                            fmt="%(asctime)s [%(levelname)-5.5s] %(message)s")
    except ImportError:
        logging.basicConfig(level=numeric_level, datefmt='%H:%M:%S',
                            format="%(asctime)s [%(levelname)-5.5s] %(message)s")

    LOG = logging.getLogger(__name__)

    LOG.info(f"Getting files from: '{args.get('input')}'.")

    RX_LIST: list[re.Pattern] = []

    # Load default scanner regex.
    for rx in RX_PAT:
        try:
            pat = re.compile(rx, re.IGNORECASE)
            RX_LIST.append(pat)
        except Exception as e:
            LOG.error("Error compiling default regex: " + str(rx) + " - " + str(e))

    files = get_files(pathlib.Path(args.get('input')), args.get('recursive'), args.get('extensions'), sideCar=False)

    parsed = 0

    matched = 0
    unmatched = 0
    for file in files:
        parsed += 1
        for rg in RX_LIST:
            match = rg.match(file['file'].stem)
            if match:
                LOG.debug(f"File: '{c(file['file'],'yellow')}' matched: '{c(rg.pattern,'yellow')}'")
                id = get_date(match, file['file'])
                if id:
                    matched += 1
                    LOG.info(f"File: '{c(file['file'],'yellow')}' id: '{c(id,'yellow')}'")
                else:
                    unmatched += 1
                    LOG.warning(f"File: '{c(file['file'],'yellow')}' has no id.")
                break

        if not match:
            unmatched += 1
            LOG.warning(f"File: '{c(file['file'],'yellow')}' did not match: '{c(rg.pattern,'yellow')}'")

    LOG.info(
        f"Total files parsed: '{c(parsed,'cyan')}', matched: '{c(matched,'cyan')}', unmatched: '{c(unmatched,'cyan')}'.")


if __name__ == "__main__":
    cli()
