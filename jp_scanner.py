#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Japanese Daily Episodes Scanner for Plex Media Server

This file extends Plex filename parser to support standard Japanese daily episodes.

Supported formats:
    - YYYY-MM-DD series epNumber title
    - YYYY-MM-DD title  
    - title YYYY-MM-DD (at end of filename)
    - series - YYYY-MM-DD title
    - Limited standard scanner formats

VERSION HISTORY:
1.6 - 2025-08-12: Code refactoring for better readability and nfo support.
1.2 - 2024-07-02: Replaced mtime with extend_id for better resistance to changes
1.1 - 2024-07-01: Added support for multi-episodes  
1.0 - 2024-01-15: Initial version
"""

import sys
import re
import os
import os.path
import logging
import inspect
import json
import time
import hashlib

# Plex imports
import Media # type: ignore
import VideoFiles  # type: ignore
import Stack  # type: ignore
import Utils  # type: ignore
import UnicodeHelper  # type: ignore

# Optional imports
HAS_TRACEBACK = True
try:
    import traceback
except ImportError:
    HAS_TRACEBACK = False

# ================================================================================
# CONSTANTS AND CONFIGURATION
# ================================================================================

__author__ = "ArabCoders"
__copyright__ = "Copyright 2025"
__license__ = "MIT"
__version__ = "1.6"
__maintainer__ = "ArabCoders"

# Date format separators
DATE_SEPARATORS = r'(\-|\.|_)?'

# Episode number patterns
EP_PATTERNS = r'(\#(\d+)|ep(\d+)|DVD[0-9.-]+|SP[0-9.-]+)'

# YouTube video ID pattern (11 characters)
YOUTUBE_ID_LENGTH = 11

# Default episode number for date-based episodes
DEFAULT_EPISODE_PREFIX = '1'

# Hash truncation length for unique IDs
HASH_ID_LENGTH = 4

# ================================================================================
# COMPILED REGEX PATTERNS
# ================================================================================

# YouTube video ID extraction
YT_RX = re.compile(r'(?<=\[)(?:youtube-)?(?P<id>[a-zA-Z0-9\-_]{11})(?=\])', re.IGNORECASE)

# YouTube filename date parsing
YT_FILE_RX = re.compile(r'^(?P<year>\d{4})(\-|\.|_)?(?P<month>\d{2})(\-|\.|_)?(?P<day>\d{2})\s-?(?P<title>.+)',re.IGNORECASE)

# YouTube JSON date format
YT_JSON_DATE_RX = re.compile(r'(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})', re.IGNORECASE)

# General file date pattern
YT_FILE_DATE = re.compile(r'^(?P<year>\d{2,4})(\-|\.|_)?(?P<month>\d{2})(\-|\.|_)?(?P<day>\d{2})\s?',re.IGNORECASE)

# Multi-episode patterns (ep01-ep02, E01-E02, etc.)
MULTI_EPISODE_PATTERNS = [ur'(EP|E)(?P<start>\d{1,4})-(EP|E)?(?P<end>\d{1,4})']

# Main parsing patterns for Japanese daily episodes
DEFAULT_PARSING_PATTERNS = [
    # YYYY-MM-DD series epNumber title
    r'^(?P<year>\d{2,4})' + DATE_SEPARATORS + r'(?P<month>\d{2})' + DATE_SEPARATORS + r'(?P<day>\d{2})\s-?(?P<series>.+?)(?P<epNumber>' + EP_PATTERNS + r') -?(?P<title>.+)',
    
    # YYYY-MM-DD title
    r'^(?P<year>\d{2,4})' + DATE_SEPARATORS + r'(?P<month>\d{2})' + DATE_SEPARATORS + r'(?P<day>\d{2})\s?-?(?P<title>.+)',
    
    # title YYYY-MM-DD (at end)
    r'(?P<title>.+?)(?P<year>\d{2,4})' + DATE_SEPARATORS + r'(?P<month>\d{2})' + DATE_SEPARATORS + r'(?P<day>\d{2})$',
    
    # series - YYYY-MM-DD title
    r'(?P<series>.+?)(?P<year>\d{2,4})' + DATE_SEPARATORS + r'(?P<month>\d{2})' + DATE_SEPARATORS + r'(?P<day>\d{2})\s?-?(?P<title>.+)?',
    
    # Standard episode patterns
    r'(?P<series>.+?)\s?[Ee][Pp](?P<episode>[0-9]{1,4})\s?(?P<title>.+)',
    r'^[Ss](?P<season>[0-9]{1,2})[Ee](?P<episode>[0-9]{1,4})\s?-?(?P<title>.+)',
    r'(?P<title>.+?)\s?[Ee][Pp](?P<episode>[0-9]{1,4})$',
    r'^(?P<series>.+?)[Ss](?P<season>[0-9]{1,})[Ee](?P<episode>[0-9]{1,})\s?-?(?P<title>.+)',
    r'(?P<series>.+?)\s?[Ee][Pp](?P<episode>[0-9]{1,4})\s?-?(?P<title>.+)',
]

# ================================================================================
# LOGGING CONFIGURATION
# ================================================================================

def setup_logging():
    """Initialize logging configuration."""
    try:
        plex_root = get_plex_root()
        log_file = os.path.join(plex_root, 'Logs', 'jp_scanner.log')
        
        logging.basicConfig(
            filename=log_file,
            format="%(asctime)s [%(levelname)-5.5s] %(message)s",
            level=logging.DEBUG
        )
        
        return logging.getLogger(__name__)
    except Exception:
        # Fallback to basic logging if Plex root can't be determined
        logging.basicConfig(level=logging.DEBUG)
        return logging.getLogger(__name__)


def get_plex_root():
    """Determine the Plex Media Server root directory."""
    try:
        # Try to get from current file location first
        current_file = inspect.getfile(inspect.currentframe()) # type: ignore
        plex_root = os.path.abspath(os.path.join(os.path.dirname(current_file), "..", ".."))
        
        if os.path.isdir(plex_root):
            return plex_root
            
        # Fallback to platform-specific paths
        platform_paths = {
            'windows': '%LOCALAPPDATA%\\Plex Media Server',
            'macosx': '$HOME/Library/Application Support/Plex Media Server',
            'linux': '$PLEX_HOME/Library/Application Support/Plex Media Server',
            'android': '/storage/emulated/0/Plex Media Server'
        }
        
        platform_key = sys.platform.lower()
        if platform_key in platform_paths:
            return os.path.expandvars(platform_paths[platform_key])
        
    except Exception:
        pass
    
    # Final fallback
    return os.path.expanduser('~')


# Initialize logging
logger = setup_logging()

# Map Python logging levels to Plex levels
PLEX_LOG_LEVEL_MAP = {
    logging.DEBUG: 3,
    logging.INFO: 2,
    logging.WARNING: 1,
    logging.ERROR: 0
}

# ================================================================================
# UTILITY FUNCTIONS
# ================================================================================

def normalize_unicode(path):
    """Convert path to unicode string safely."""
    if not isinstance(path, unicode): # type: ignore
        encoding = sys.getfilesystemencoding() or 'utf-8'
        return path.decode(encoding, 'replace')
    return path


def log_message(message, level=logging.INFO):
    """Log message to both Python logging and Plex logging."""
    if level not in PLEX_LOG_LEVEL_MAP:
        level = logging.INFO
    
    # Log to Python logger
    logger.log(level, message)
    
    # Log to Plex (if Utils.Log is available)
    try:
        Utils.Log(
            message=message, 
            level=PLEX_LOG_LEVEL_MAP[level], 
            source='jp_scanner.bundle'
        )
    except (NameError, AttributeError):
        pass


def create_unique_episode_id(file_path):
    """Create a unique 4-digit ID from filename hash."""
    try:
        basename = os.path.splitext(os.path.basename(file_path))[0]
        basename = normalize_unicode(basename).lower()
        
        # Create hash
        hash_obj = hashlib.sha256(basename.encode('utf-8', 'replace'))
        hash_hex = hash_obj.hexdigest()
        
        # Convert to numeric string and truncate
        ascii_values = ''.join([str(ord(c)) for c in hash_hex])
        truncated = ascii_values[:HASH_ID_LENGTH]
        
        # Pad if necessary
        if len(truncated) < HASH_ID_LENGTH:
            truncated = truncated.ljust(HASH_ID_LENGTH, '9')
            
        return int(truncated)
        
    except Exception as e:
        log_message(
            "Error creating unique ID for '{}': {}".format(file_path, str(e)),
            logging.ERROR
        )
        return 1000


def normalize_year(year_str):
    """Convert 2-digit year to 4-digit year."""
    if year_str and len(str(year_str)) == 2:
        return '20' + year_str
    return year_str


def clean_title(title, show_name=None):
    """Clean and normalize episode title."""
    if not title:
        return title
        
    # Remove show name from title if present
    if show_name and show_name.lower() in title.lower():
        title = re.sub(re.escape(show_name), '', title, flags=re.IGNORECASE)
    
    # Remove content in brackets and clean up
    title = re.sub(r'\[.+?\]', ' ', title)
    title = title.strip().strip('-').strip()
    
    return title


def format_date_string(year, month, day):
    """Format year, month, day into date string."""
    if year and month and day:
        return "{}-{}-{}".format(year, month, day)
    return None


# ================================================================================
# REGEX PATTERN COMPILATION
# ================================================================================

def compile_regex_patterns():
    """Compile all regex patterns and return lists of compiled patterns."""
    multi_episode_list = []
    main_pattern_list = []
    
    # Compile multi-episode patterns
    for pattern in MULTI_EPISODE_PATTERNS:
        try:
            compiled = re.compile(pattern, re.UNICODE | re.IGNORECASE)
            multi_episode_list.append(compiled)
        except Exception as e:
            log_message("Error compiling multi-episode pattern '{}': {}".format(pattern, str(e)),logging.ERROR)
    
    # Load custom patterns from config file
    custom_patterns = load_custom_patterns()
    for pattern in custom_patterns:
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            main_pattern_list.append(compiled)
        except Exception as e:
            log_message("Error compiling custom pattern '{}': {}".format(pattern, str(e)), logging.ERROR)
    
    # Compile default patterns
    for pattern in DEFAULT_PARSING_PATTERNS:
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            main_pattern_list.append(compiled)
        except Exception as e:
            log_message("Error compiling default pattern '{}': {}".format(pattern, str(e)),logging.ERROR)
    
    return multi_episode_list, main_pattern_list


def load_custom_patterns():
    """Load custom regex patterns from configuration file."""
    custom_path = os.environ.get('JP_SCANNER_PATH') or get_plex_root()
    config_file = os.path.join(custom_path, 'jp_scanner.json')
    
    if not os.path.exists(config_file):
        return []
    
    try:
        with open(config_file) as f:
            data = json.load(f)
            return [pattern for pattern in data if pattern]
    except Exception as e:
        log_message(
            "Error loading custom patterns from '{}': {}".format(config_file, str(e)),
            logging.ERROR
        )
        return []


# Compile patterns at module level
MULTI_EPISODE_PATTERNS_COMPILED, MAIN_PATTERNS_COMPILED = compile_regex_patterns()

# ================================================================================
# XML/NFO FILE HANDLING
# ================================================================================

def escape_xml_text(text):
    """Escape special characters in XML text content."""
    # Preserve valid entities, escape stray ampersands
    text = re.sub(r'&(?![A-Za-z][A-Za-z0-9]*;|#[0-9]+;|#x[0-9A-Fa-f]+;)', '&amp;', text)
    # Escape angle brackets
    text = text.replace('<', '&lt;').replace('>', '&gt;')
    return text


def fix_xml_content(xml_content, outer_tag="episodedetails"):
    """Fix common XML formatting issues in NFO files."""
    # Extract the parent tag block
    pattern = r'<{tag}>(.*?)</{tag}>'.format(tag=outer_tag)
    match = re.search(pattern, xml_content, re.DOTALL)
    
    if not match:
        return xml_content
    
    tag_content = match.group(1)
    
    # Process all nested tags
    tag_pattern = r'<(\w+)([^>]*?)>(.*?)</\1>'
    
    def replace_tag_content(tag_match):
        tag_name = tag_match.group(1)
        attributes = tag_match.group(2)
        content = tag_match.group(3)
        
        escaped_content = escape_xml_text(content)
        
        return '<{tag}{attrs}>{content}</{tag}>'.format(tag=tag_name,attrs=attributes,content=escaped_content)
    
    # Fix content within the parent tag
    fixed_content = re.sub(tag_pattern, replace_tag_content, tag_content)
    
    # Reconstruct the XML
    fixed_xml = xml_content.replace(match.group(0),'<{tag}>{content}</{tag}>'.format(tag=outer_tag, content=fixed_content))
    
    # Final cleanup
    fixed_xml = re.sub(r"&(?![A-Za-z]+[0-9]*;|#[0-9]+;|#x[0-9a-fA-F]+;)", r"&amp;", fixed_xml)
    fixed_xml = re.sub(r"^\s*<.*/>[\r\n]+", "", fixed_xml, flags=re.MULTILINE)
    
    return fixed_xml


def extract_nfo_metadata(file_path):
    """Extract metadata from accompanying NFO file."""
    nfo_path = os.path.splitext(file_path)[0] + ".nfo"
    
    if not os.path.exists(nfo_path):
        return {}
    
    try:
        log_message("Processing NFO file: {}".format(nfo_path))
        nfo_text = ""
        # Load and fix NFO content
        try:
            with open(json_path) as f:
                nfo_text = f.read()
        except Exception as e:
            log_message("Error loading NFO file '{}': {}".format(nfo_path, str(e)), logging.ERROR )
            return {}

        nfo_text = fix_xml_content(nfo_text, "episodedetails")
        
        # Parse XML
        try:
            nfo_xml = XML.ElementFromString(nfo_text).xpath("//episodedetails")[0] # type: ignore
        except Exception as e:
            log_message("Cannot parse XML in '{}': {}".format(nfo_path, str(e)),logging.ERROR)
            return {}
        
        # Extract metadata
        metadata = {}
        xml_field_map = [
            "title", "season", "episode", "aired", "year",
            ("plot", "summary")  # XML field, metadata key
        ]
        
        for field_info in xml_field_map:
            if isinstance(field_info, tuple):
                xml_field, metadata_key = field_info
            else:
                xml_field = metadata_key = field_info
            
            try:
                elements = nfo_xml.xpath(xml_field)
                if elements and elements[0].text:
                    value = elements[0].text.strip()
                    if value:
                        metadata[metadata_key] = value
            except Exception:
                continue
        
        return metadata
        
    except Exception as e:
        log_message("Error processing NFO file '{}': {}".format(nfo_path, str(e)), logging.ERROR)
        if HAS_TRACEBACK:
            log_message("Traceback: {}".format(traceback.format_exc()), logging.DEBUG)
        return {}


# ================================================================================
# EPISODE DATA PROCESSING
# ================================================================================

def process_regex_match(match, show_name, file_path=None):
    """Process regex match and extract episode information."""
    if not match:
        return None
    
    # Load NFO metadata if available
    nfo_metadata = extract_nfo_metadata(file_path) if file_path else {}
    
    # Extract match groups safely
    groups = match.groupdict()
    
    series = groups.get('series')
    year = groups.get('year')
    month = groups.get('month')
    day = groups.get('day')
    episode = groups.get('episode')
    season = groups.get('season')
    title = groups.get('title')
    
    # Normalize year
    year = normalize_year(year)
    
    # Generate release date
    release_date = format_date_string(year, month, day)
    
    # Set default season
    if not season:
        season = "{:>04}".format(year) if year else 1
    
    # Generate episode number for date-based episodes
    if not episode and year and month and day:
        episode = int(DEFAULT_EPISODE_PREFIX + month + day)
    
    # Clean up title
    title = clean_title(title, show_name)
    
    # Use release date as title if no title available
    if not title or title == series:
        title = release_date
    
    # Format title with additional info
    if title:
        ep_number = groups.get('epNumber')
        if ep_number:
            title = "{} - {}".format(ep_number, title)
        elif title and release_date and release_date != title:
            short_date = release_date.replace('-', '')[2:]  # Remove dashes and year prefix
            title = "{} ~ {}".format(short_date, title)
        
        title = title.strip()
    
    # Override with NFO metadata if available
    nfo_override = False
    
    for field in ['season', 'episode', 'title', 'year']:
        if nfo_metadata.get(field):
            nfo_override = True
            if field in ['season', 'episode', 'year']:
                locals()[field] = int(nfo_metadata[field])
            else:
                locals()[field] = nfo_metadata[field]
    
    # Validate required fields
    if season is None and episode is None:
        return None
    
    # Generate unique episode ID for date-based episodes
    if (file_path and release_date and len(str(episode)) < 8 and not nfo_override):
        unique_id = create_unique_episode_id(file_path)
        episode = int('{}{:>04}'.format(episode, unique_id))
    
    return { "season": season, "episode": episode, "title": title, "year": year, "month": month, "day": day, "released_date": release_date }

def process_youtube_file(file_path, filename):
    """Process YouTube video files and extract episode information."""
    json_file_path = os.path.splitext(file_path)[0] + '.info.json'
    
    # Try to load metadata from JSON file first
    if os.path.exists(json_file_path):
        return process_youtube_json_metadata(json_file_path, file_path, filename)
    
    # Fallback to filename parsing
    return process_youtube_filename(filename, file_path)


def process_youtube_json_metadata(json_path, file_path, filename):
    """Extract YouTube metadata from JSON info file."""
    try:
        with open(json_path) as f:
            data = json.load(f)
    except Exception as e:
        log_message(
            "Error loading YouTube JSON '{}': {}".format(json_path, str(e)),
            logging.ERROR
        )
        return None
    
    # Extract date information
    date_match = None
    
    if data.get('upload_date'):
        date_match = YT_JSON_DATE_RX.match(data['upload_date'])
    elif data.get('epoch'):
        timestamp = time.gmtime(float(data['epoch']))
        date_string = time.strftime("%Y%m%d", timestamp)
        date_match = YT_JSON_DATE_RX.match(date_string)
    else:
        date_match = YT_FILE_DATE.search(os.path.basename(filename))
    
    if not date_match:
        log_message(
            "Cannot extract date from YouTube file '{}' and no upload_date in JSON".format(filename),
            logging.ERROR
        )
        return None
    
    # Extract metadata
    title = data.get('title', '')
    year = normalize_year(date_match.group('year'))
    month = date_match.group('month')
    day = date_match.group('day')
    
    season = "{:>04}".format(year) if year else 1
    release_date = format_date_string(year, month, day)
    
    # Clean title
    title = clean_title(title)
    
    # Generate unique episode number
    unique_id = create_unique_episode_id(file_path)
    episode = int('{}{:>02}{:>02}{:>04}'.format(DEFAULT_EPISODE_PREFIX, month, day, unique_id))
    
    return { "season": season, "episode": episode, "title": title, "year": year, "month": month, "day": day, "released_date": release_date }


def process_youtube_filename(filename, file_path):
    """Extract YouTube metadata from filename only."""
    match = YT_FILE_RX.match(filename)
    
    if not match:
        log_message("Cannot parse YouTube filename: '{}'".format(filename), logging.ERROR)
        return None
    
    log_message(
        "No JSON metadata found for '{}', using filename parsing".format(filename),
        logging.WARNING
    )
    
    # Extract data from filename
    title = match.group('title')
    year = normalize_year(match.group('year'))
    month = match.group('month')
    day = match.group('day')
    
    season = "{:>04}".format(year) if year else 1
    release_date = format_date_string(year, month, day)
    
    # Clean title
    title = clean_title(title)
    
    # Generate episode number
    unique_id = create_unique_episode_id(file_path)
    episode = int('{}{:>02}{:>02}{:>04}'.format(DEFAULT_EPISODE_PREFIX, month, day, unique_id))
    
    return { "season": season, "episode": episode, "title": title, "year": year, "month": month, "day": day, "released_date": release_date }


# ================================================================================
# MEDIA OBJECT CREATION
# ================================================================================

def create_episode_media_object(show_name, episode_data, file_path):
    """Create a Plex Media.Episode object from episode data."""
    tv_show = Media.Episode(
        show=UnicodeHelper.toBytes(show_name),
        season=int(episode_data['season']),
        episode=int(episode_data['episode']),
        title=UnicodeHelper.toBytes(episode_data.get('title', '')),
        year=episode_data.get('year')
    )
    
    if episode_data.get('released_date'):
        tv_show.released_at = episode_data['released_date']
    
    tv_show.parts.append(file_path)
    
    return tv_show


def process_multi_episode_file(filename, episode_data, show_name, file_path):
    """Handle files containing multiple episodes."""
    media_objects = []
    
    for pattern in MULTI_EPISODE_PATTERNS_COMPILED:
        match = pattern.search(filename)
        
        if not match:
            continue
        
        log_message("Multi-episode file detected: '{}'".format(filename), logging.INFO)
        
        start_ep = int(match.group('start'))
        end_ep = int(match.group('end'))
        
        for ep_num in range(start_ep, end_ep + 1):
            # Calculate display offset for multi-episode files
            total_episodes = end_ep - start_ep + 1
            offset = (ep_num - start_ep) * 100 / total_episodes
            
            tv_show = Media.Episode(
                show=UnicodeHelper.toBytes(show_name),
                season=int(episode_data['season']),
                episode=ep_num,
                title=UnicodeHelper.toBytes(episode_data.get('title', '')),
                year=episode_data.get('year')
            )
            
            if episode_data.get('released_date'):
                tv_show.released_at = episode_data['released_date']
            
            tv_show.display_offset = offset
            tv_show.parts.append(file_path)
            
            log_message("[Multi] '{}' - {} - S{}E{}".format(filename, show_name, episode_data['season'], ep_num),logging.DEBUG)
            
            media_objects.append(tv_show)
        
        return media_objects
    
    return []


# ================================================================================
# MAIN SCANNING FUNCTIONS
# ================================================================================

def scan_single_file(file_path, show_name, media_list):
    """Scan a single file and add to media list if recognized."""
    filename = os.path.basename(file_path)
    filename_no_ext, _ = os.path.splitext(filename)
    
    found_match = False
    
    # Handle YouTube content
    if YT_RX.search(filename):
        episode_data = process_youtube_file(file_path, filename_no_ext)
        
        if episode_data:
            tv_show = create_episode_media_object(show_name, episode_data, file_path)
            media_list.append(tv_show)
            
            log_message("{}: {} - S{}E{}".format(filename, show_name, episode_data['season'], episode_data['episode']), logging.DEBUG)
            found_match = True
        else:
            log_message("Error processing YouTube file: {}".format(file_path), logging.ERROR)
    
    # Handle regular content
    else:
        for pattern in MAIN_PATTERNS_COMPILED:
            match = pattern.match(filename_no_ext)
            
            if not match:
                continue
            
            episode_data = process_regex_match(match, show_name, file_path)
            
            if not episode_data:
                log_message("Error processing match for: {}".format(filename), logging.ERROR)
                continue
            
            found_match = True
            
            # Check for multi-episode content (only for non-date-based episodes)
            if not episode_data.get('released_date'):
                multi_episodes = process_multi_episode_file(filename_no_ext, episode_data, show_name, file_path)                
                if multi_episodes:
                    media_list.extend(multi_episodes)
                    break
            
            # Single episode
            tv_show = create_episode_media_object(show_name, episode_data, file_path)
            media_list.append(tv_show)
            
            log_message("{}: {} - S{}E{}".format(filename, show_name, episode_data['season'], episode_data['episode']), logging.DEBUG)
            break
    
    if not found_match:
        log_message("No pattern matched for file: {}".format(filename), logging.WARNING)


def scan_implementation(path, files, media_list, subdirs):
    """Main scanning implementation."""
    # Use Plex's built-in video file scanning
    VideoFiles.Scan(path, files, media_list, subdirs)
    
    # Extract show name from path
    path_parts = Utils.SplitPath(path)
    
    if not path_parts or not path_parts[0]:
        log_message("Invalid path structure: {}".format(path), logging.ERROR)
        return
    
    show_name, _ = VideoFiles.CleanName(path_parts[0])
    
    log_message("Scanning path: {} for show: {}".format(path, show_name), logging.INFO)
    
    # Process each file
    for file_path in files:
        try:
            scan_single_file(file_path, show_name, media_list)
        except Exception as e:
            log_message("Error processing file '{}': {}".format(file_path, str(e)), logging.ERROR)
            if HAS_TRACEBACK:
                log_message("Traceback: {}".format(traceback.format_exc()), logging.DEBUG)
    
    # Apply Plex's stacking logic
    Stack.Scan(path, files, media_list, subdirs)


# ================================================================================
# PUBLIC API
# ================================================================================

def Scan(path, files, media_list, subdirs):
    """
    Main entry point for Plex scanner.
    
    Args:
        path: Directory path being scanned
        files: List of files in the directory  
        media_list: List to append found media objects to
        subdirs: List of subdirectories
    """
    try:
        scan_implementation(path, files, media_list, subdirs)
    except Exception as e:
        log_message("Critical error scanning '{}': {}".format(path, str(e)),logging.ERROR)
        if HAS_TRACEBACK:
            log_message("Traceback: {}".format(traceback.format_exc()), logging.ERROR)


# ================================================================================
# COMMAND LINE INTERFACE
# ================================================================================

if __name__ == '__main__':
    """Command line interface for testing."""
    logger.info("jp_scanner.py version: {}".format(__version__))
    
    if len(sys.argv) < 2:
        print("Usage: {} <directory_path>".format(sys.argv[0]))
        sys.exit(1)
    
    test_path = sys.argv[1]
    
    if not os.path.isdir(test_path):
        print("Error: '{}' is not a valid directory".format(test_path))
        sys.exit(1)
    
    # Get list of files in directory
    test_files = [os.path.join(test_path, f) for f in os.listdir(test_path) if os.path.isfile(os.path.join(test_path, f))]
    
    test_media = []
    
    # Run scan
    Scan(test_path, test_files, test_media, [])
    
    # Output results
    logger.info("Scan completed. Found {} media files".format(len(test_media)))
    
    for media in test_media:
        print("Found: {} - S{}E{} - {}".format(media.show, media.season, media.episode, media.title))