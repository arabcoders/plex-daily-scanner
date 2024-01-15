# jp_scanner.py

This scanner extends plex filename parser to support Japanese standard media naming convention. This plugin has been developed mainly to work with my other agents:

- [plex yt-dlp info reader agent](https://github.com/arabcoders/plex-ytdlp-info-reader-agent)
- [Custom metadata agent](https://github.com/arabcoders/cmdb.bundle)

This plugin has poor support for non Japanese media naming convention, while it does support the standard naming you are better fit to use plex agents for that.

## Installation

Download or clone this repository. Copy the `jp_scanner.py` file to your plex Media Server `Scanners/Series` directory. What [where is that](https://support.plex.tv/articles/201106098-how-do-i-find-the-plug-ins-folder/)? Go to this directory and then go one level up from there You most likely wont find a `Scanners/Series` directory, so create one and copy the file there.

Once that is done, restart your plex media server and you should be able to see the scanner in the list of scanners.

The `Scanners` directory should be next to the following directories: `Logs`, `Plugins`, `Plug-in Support`. If it isn't in that place, then the scanner won't show up.

## How to use?

Simply create new library and select the scanner from the list of scanners. Select the Agent to be one of the agents mentioned above.

## How is the library supposed to be structured?

The library should be structured as follows:


```
├── main_root_directory (The place where you store all of your jp media)
│   ├── the show title
│   │   ├── Season (Year)
│   │   │   ├── {date} Show Title -? ep01 - optional episode title.ext
│   │   │   ├── {date} title.ext
│   │   │   ├── title {date}.ext
│   │   │   ├── Series title - {date} - optional episode title.ext
```

The `{date}` in filename references one of the following formats:
We will use the following date as an example: `2021-10-21`

* `211021` `21-10-21` `21_10_21` `21.10.21`
* `20211021` `2021-10-21` `2021_10_21` `2021.10.21`

All the formats you see above match the same date in the scanner. 

If the date length is less than `8` and to avoid identifying multiple episodes that aired on same date, the episode Index is extended with `4` more digits the four digits comes from the file last modified date `mmss`.

So the final episode index becomes `1` + `episode air date` + `last modified date`.

Continuing with the example above, if the episode air date is `2021-10-21` and the file last modified date is `2021-10-21 12:34:56` then the episode index becomes `1-211021-3456`.

## Why the seasons showing as `Season (Year)`?

Simply put, I like it this way, and there is no plans to change it.

## How to add custom regex matchers?

You can do so by, creating a file named `jp_scanner.json` next to where you created `Scanners` directory. The file should be in the following format:

```json5
[
    "(?P<title>.+?)\s?[Ee][Pp](?P<episode>[0-9]{1,4})$",
    ...
]
```