# jp_scanner.py

This scanner extends plex filename parser to support Japanese standard media naming convention. This plugin has been developed mainly to work with my other agents:

- [plex yt-dlp info reader agent](https://github.com/arabcoders/plex-ytdlp-info-reader-agent)
- [Custom metadata agent](https://github.com/arabcoders/cmdb.bundle)

This plugin has poor support for non Japanese media naming convention, while it does support the standard naming you are better fit to use plex agents for that.

## Installation

Download or clone this repository. Copy the `jp_scanner.py` file to your plex Media Server `Scanners/Series` directory. What [where is that](https://support.plex.tv/articles/201106098-how-do-i-find-the-plug-ins-folder/)? Go to this directory and then go one level up from there You most likely wont find a `Scanners/Series` directory, so create one and copy the file there.

Once that is done, restart your plex media server and you should be able to see the scanner in the list of scanners.

## How to add custom regex matchers?

You can do so by, creating a file named `jp_scanner.json` next to where you created `Scanner` directory. The file should be in the following format:

```json5
[
    "(?P<title>.+?)\s?[Ee][Pp](?P<episode>[0-9]{1,4})$",
    ...
]
```