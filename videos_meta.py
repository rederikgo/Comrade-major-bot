import re

# Try to parse
def parse_title(video_title):
    delimiters = ('-', '–', '—', '|', '/')
    for delimiter in delimiters:
        parts = video_title.split(delimiter, maxsplit=1)
        if len(parts) > 1:
            return parts

# Remove unwanted unicode
def remove_unicode(title):
    for character in title:
        if character > '\u4e20':
            title = title.replace(character, '')
    return title

# Remove brackets
def remove_brackets(title):
    return re.sub('[\(\[].*?[\)\]]', '', title)