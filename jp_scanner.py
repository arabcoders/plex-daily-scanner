#!/usr/bin/env python

"""
This file extends Plex filename parser to support the standard japanese daily episodes.
The supported formats are:
    YY?YY(-._)MM(-._)DD -? series -? epNumber -? title
    YY?YY(-._)MM(-._)DD -? title
    title YY?YY(-._)MM(-._)DD at end of filename.
    series - YY?YY(-._)MM(-._)DD -? title    
"""

# I needed some plex libraries, you may need to adjust your plex install location accordingly
import sys
import re
import os
import os.path
import sys
import logging
import inspect
import json
import Media
import VideoFiles
import Stack
import Utils
import time
import UnicodeHelper

__author__ = "ArabCoders"
__copyright__ = "Copyright 2024"
__credits__ = ["ArabCoders"]

__license__ = "MIT"
__version__ = "1.0"
__maintainer__ = "ArabCoders"
__email__ = ""

try:
    ### Define PLEX_ROOT ##################################################################################
    PLEX_ROOT = os.path.abspath(os.path.join(os.path.dirname(inspect.getfile(inspect.currentframe())), "..", ".."))
    if not os.path.isdir(PLEX_ROOT):
        path_location = {
            'Windows': '%LOCALAPPDATA%\\Plex Media Server',
            'MacOSX':  '$HOME/Library/Application Support/Plex Media Server',
            'Linux':   '$PLEX_HOME/Library/Application Support/Plex Media Server',
            'Android': '/storage/emulated/0/Plex Media Server'
        }
        PLEX_ROOT = os.path.expandvars(path_location[sys.platform.lower()] if sys.platform.lower(
        ) in path_location else '~')  # Platform.OS:  Windows, MacOSX, or Linux
except:
    PLEX_ROOT = os.path.expanduser('~')

# load custom path from env
customPath = os.environ.get('JP_SCANNER_PATH') or PLEX_ROOT

logging.basicConfig(
    filename=os.path.join(PLEX_ROOT, 'Logs', 'jp_scanner.log'),
    format="%(asctime)s [%(levelname)-5.5s] %(message)s",
    level=logging.DEBUG
)

logger = logging.getLogger(__name__)

LOGGING_LEVEL_MAP = {
    logging.DEBUG: 3,
    logging.INFO: 2,
    logging.WARNING: 1,
    logging.ERROR: 0
}


def logit(message, level=logging.INFO):
    if level not in LOGGING_LEVEL_MAP:
        level = logging.INFO

    Utils.Log(message=message, level=LOGGING_LEVEL_MAP[level], source='jp_scanner.bundle')


YT_RX = re.compile(r'(?<=\[)(?:youtube-)?(?P<id>[a-zA-Z0-9\-_]{11})(?=\])', re.IGNORECASE)
YT_FILE_RX = re.compile(
    r'^(?P<year>\d{4})(\-|\.|_)?(?P<month>\d{2})(\-|\.|_)?(?P<day>\d{2})\s-?(?P<title>.+)', re.IGNORECASE)
YT_JSON_DATE_RX = re.compile(r'(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})', re.IGNORECASE)
YT_FILE_DATE = re.compile(r'^(?P<year>\d{2,4})(\-|\.|_)?(?P<month>\d{2})(\-|\.|_)?(?P<day>\d{2})\s?', re.IGNORECASE)

RX_LIST = []

DEFAULT_RX = [
    # YY?YY(-._)MM(-._)DD -? series -? epNumber -? title
    r'^(?P<year>\d{2,4})(\-|\.|_)?(?P<month>\d{2})(\-|\.|_)?(?P<day>\d{2})\s-?(?P<series>.+?)(?P<epNumber>\#(\d+)|ep(\d+)|DVD[0-9.-]+|SP[0-9.-]+) -?(?P<title>.+)',
    # YY?YY(-._)MM(-._)DD -? title
    r'^(?P<year>\d{2,4})(\-|\.|_)?(?P<month>\d{2})(\-|\.|_)?(?P<day>\d{2})\s?-?(?P<title>.+)',
    # title YY?YY(-._)MM(-._)DD at end of filename.
    r'(?P<title>.+?)(?P<year>\d{2,4})(\-|\.|_)?(?P<month>\d{2})(\-|\.|_)?(?P<day>\d{2})$',
    # series - YY?YY(-._)MM(-._)DD -? title
    r'(?P<series>.+?)(?P<year>\d{2,4})(\-|\.|_)?(?P<month>\d{2})(\-|\.|_)?(?P<day>\d{2})\s?-?(?P<title>.+)?',
    # series ep0000 Title
    r'(?P<series>.+?)\s?[Ee][Pp](?P<episode>[0-9]{1,4})\s?(?P<title>.+)',
    # S00E00 - Title
    r'^[Ss](?P<season>[0-9]{1,2})[Ee](?P<episode>[0-9]{1,4})\s?-?(?P<title>.+)',
    # Title ep0000
    r'(?P<title>.+?)\s?[Ee][Pp](?P<episode>[0-9]{1,4})$',
    # Standard scanner Series - S00E00 - Title
    r'^(?P<series>.+?)[Ss](?P<season>[0-9]{1,})[Ee](?P<episode>[0-9]{1,})\s?-?(?P<title>.+)',
]

# Load Custom Regex patterns.matchers from `jp_scanner.json` file.
customFile = os.path.join(customPath, 'jp_scanner.json')
if os.path.exists(os.path.join(customFile)):
    with open(customFile) as data_file:
        try:
            data = json.load(data_file)
            for rx in data:
                if not rx:
                    continue
                try:
                    pat = re.compile(rx, re.IGNORECASE)
                    RX_LIST.append(pat)
                except Exception as e:
                    logit("Error compiling custom regex: " +
                          str(rx) + " - " + str(e))
        except Exception as e:
            logit(
                "Error loading custom regex file [%s] - [%s]" % (customFile, str(e)))

# Load default scanner regex.
for rx in DEFAULT_RX:
    try:
        pat = re.compile(rx, re.IGNORECASE)
        RX_LIST.append(pat)
    except Exception as e:
        logit("Error compiling default regex: " + str(rx) + " - " + str(e))


def handleMatch(match, show, file=None):
    """
    Handle the regex match and return a dict of the results.

    :param match: The regex match object.
    :param show: The show name.
    :param file: The file name.
    :return: A dict of the results.
    """
    series = match.group('series') if match.groupdict().has_key('series') else None
    month = match.group('month') if match.groupdict().has_key('month') else None
    day = match.group('day') if match.groupdict().has_key('day') else None
    year = match.group('year') if match.groupdict().has_key('year') else None
    episode = match.group('episode') if match.groupdict().has_key('episode') else None
    title = match.group('title') if match.groupdict().has_key('title') else None
    if title:
        if show and show.lower() in title.lower():
            title = re.sub(re.escape(show), '', title, flags=re.IGNORECASE)
        title = re.sub('\[.+?\]', ' ', title).strip('-').strip()

    season = match.group('season') if match.groupdict().has_key('season') else None

    if year and len(year) == 2:
        year = '20' + year

    released_date = "{}-{}-{}".format(year, month, day) if year and month and day else None

    if not season:
        season = "{:>04}{:>02}".format(year, month) if year and month else 1

    if not episode:
        episode = int('1' + match.group('month') + match.group('day'))

    if not title or title == series:
        title = released_date

    if title:
        title = title.strip().strip('-').strip()

        if match.groupdict().has_key('epNumber'):
            title = match.group('epNumber') + ' - ' + title
        elif title and released_date and released_date != title:
            title = "{} ~ {}".format(released_date.replace('-', '')[2:], title)

        title = title.strip()

    if season is None and episode is None:
        return None

    if file and released_date and len(str(episode)) < 8 and os.path.exists(file):
        json_ts = time.gmtime(os.path.getmtime(file))
        minute = json_ts[4]
        seconds = json_ts[5]
        episode = int('{}{:>02}{:>02}'.format(episode, minute, seconds))

    return {"season": season, "episode": episode, "title": title, "year": year, "month": month, "day": day, 'released_date': released_date}


def handleYouTube(fullpath, file):
    """
    Handle the youtube filename and return a dict of the results.

    :param fullpath: The full path to the file.
    :param file: The file name.
    :return: A dict of the results.
    """

    # Pull info from info.json file if it exists
    json_file = os.path.splitext(fullpath)[0] + '.info.json'
    if os.path.exists(json_file):
        try:
            json_data = open(json_file)
            data = json.load(json_data)
            json_data.close()
        except Exception as e:
            logit("Error loading json file: {} - {}".format(str(json_file), str(e)), logging.ERROR)
            return None
        
        if data.get('upload_date', None):
            json_date = YT_JSON_DATE_RX.match(data.get('upload_date'))
        elif data.get('epoch', None):
            json_date = YT_JSON_DATE_RX.match(time.strftime("%Y%m%d", time.gmtime(float(data.get('epoch')))))
        else:
            json_date = YT_FILE_DATE.search(os.path.basename(file))
            if not json_date:
                logit("Error matching file: '{}', and no upload_date in json.file".format(file))
                return None

        title = data.get('title')
        year = json_date.group('year') if json_date else None
        if year and len(year) == 2:
            year = '20' + year

        month = json_date.group('month') if json_date else None
        day = json_date.group('day') if json_date else None
        season = "{:>04}{:>02}".format(year, month) if year and month else 1

        released_date = "{}-{}-{}".format(year, month, day) if year and month and day else None

        if not data.get('epoch'):
            json_ts = time.gmtime(os.path.getmtime(fullpath))
        else:
            json_ts = time.gmtime(float(data.get('epoch')))

        hour = json_ts[3]
        minute = json_ts[4]
        seconds = json_ts[5]

        # for title replace content in brackets with nothing
        if title:
            title = re.sub('\[.+?\]', ' ', title).strip('-').strip()

        episode = '1{:>02}{:>02}{:>02}{:>02}'.format(month, day, minute, seconds)
        if not episode:
            logit("Error matching youtube file: {} - {} - {} - {} - {}".format(
                str(file), str(month), str(day), str(hour), str(minute)))
            return None

        return {"season": season, "episode": episode, "title": title, "year": year,  "month": month,
                "day": day, "hour": hour, "minute": minute, 'released_date': released_date}

    # Pull info from filename if info.json doesn't exist
    match = YT_FILE_RX.match(file)
    if not match:
        logit("Error matching youtube file: '{}'.".format(str(file)))
        return None

    logit("Failed to find '{}' for '{}', so using mod file instead.".format(json_file, file), logging.WARNING)

    title = match.group('title') if match.groupdict().has_key('title') else None
    year = match.group('year') if match.groupdict().has_key('year') else None
    month = match.group('month') if match.groupdict().has_key('month') else None
    day = match.group('day') if match.groupdict().has_key('day') else None
    season = "{:>04}{:>02}".format(year, month) if year and month else 1
    released_date = "{}-{}-{}".format(year, month, day) if year and month and day else None

    json_ts = time.gmtime(os.path.getmtime(fullpath))
    hour = json_ts[3]
    minute = json_ts[4]
    seconds = json_ts[5]
    episode = '1{:>02}{:>02}{:>02}{:>02}'.format(month, day, minute, seconds)
    if not episode:
        logit("Error matching youtube file: '{}'.".format(str(file)))
        return None

    # for title replace content in brackets with nothing
    if title:
        title = re.sub('\[.+?\]', ' ', title).strip('-').strip()

    return {
        "season": season, "episode": episode, "title": title, "year": year, "month": month,
        "day": day,  "hour": hour, "minute": minute, 'released_date': released_date}


def Scan(path, files, mediaList, subdirs):
    try:
        scan_real(path, files, mediaList, subdirs)
    except Exception as e:
        logit("Error scanning '{}'. {} ".format(path, str(e)), logging.ERROR)
        logger.error("Error scanning. {}".format(str(e)))


def scan_real(path, files, mediaList, subdirs):
    """
    Scan for video files.
    """
    # Scan for video files.
    VideoFiles.Scan(path, files, mediaList, subdirs)

    # Take top two as show/season, but require at least the top one.
    paths = Utils.SplitPath(path)

    if len(paths) > 0 and len(paths[0]) > 0:
        done = False

        if done == False:
            (show, _) = VideoFiles.CleanName(paths[0])

            for i in files:
                found = False
                done = False
                file = os.path.basename(i)
                (file, _) = os.path.splitext(file)

                # Handle Youtube content.
                if YT_RX.search(file):
                    data = handleYouTube(i, file)
                    if data:
                        found = True
                        tv_show = Media.Episode(
                            show=UnicodeHelper.toBytes(show),
                            season=int(data.get('season')),
                            episode=int(data.get('episode')),
                            title=UnicodeHelper.toBytes(data.get('title')),
                            year=int(data.get('year'))
                        )

                        if data.get('released_date'):
                            tv_show.released_at = data.get('released_date')

                        logit("{}: {} - S{}E{}".format(
                            file, show, data.get('season'), data.get('episode')
                        ), logging.DEBUG)

                        tv_show.parts.append(i)
                        mediaList.append(tv_show)
                    else:
                        logit("Youtube error matching: " + str(i), logging.ERROR)
                else:
                    # Handle normal content.
                    for rx in RX_LIST:
                        match = rx.match(file)
                        if not match:
                            continue

                        data = handleMatch(match, show, i)
                        if not data:
                            logit("Error matching: " + str(file), logging.ERROR)
                            continue

                        found = True

                        tv_show = Media.Episode(
                            show=UnicodeHelper.toBytes(show),
                            season=data.get('season'),
                            episode=data.get('episode'),
                            title=UnicodeHelper.toBytes(data.get('title')),
                            year=data.get('year')
                        )

                        if data.get('released_date'):
                            tv_show.released_at = data.get('released_date')

                        logit("{}: {} - S{}E{}".format(
                            file, show, data.get('season'), data.get('episode')
                        ), logging.DEBUG)

                        tv_show.parts.append(i)
                        mediaList.append(tv_show)
                        break

                if True == found:
                    continue

                if False == done:
                    logit("Got nothing for: " + str(file), logging.ERROR)

    # Stack the results.
    Stack.Scan(path, files, mediaList, subdirs)


if __name__ == '__main__':
    logger.info("jp_scanner.py: " + str(__version__))
    path = sys.argv[1]
    files = [os.path.join(path, file) for file in os.listdir(path)]
    media = []
    Scan(path[1:], files, media, [])
    logger.info("Files detected: " + str(media), logging.DEBUG)
