"""
OpenLP Link.py
==============
Connects OpenLP to Livestream Studio!

:copyright: (C) 2020 Matthew Frazier.
:license:   MIT/X11, see LICENSE global variable
"""
import csv
import os
import pprint
import re
import requests # external library: install with "pip install requests"
import sys
import time
import urllib.parse

LICENSE = '''
Copyright (C) 2020 Matthew Frazier

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))
TEXT_LAYER_FILE = os.path.join(THIS_FOLDER, 'Text Layer.csv')
URL_FILE = os.path.join(THIS_FOLDER, 'OpenLP URL.txt')

REFRESH_INTERVAL = 1 / 6
RETRY_INTERVAL = 5
CTRL_C_TIMEOUT = 1.5

CHAPTER_VERSE_RE_TEXT = (
    r'(?:[1-9][0-9]*:)?'        # Chapter (optional, some books have no chapters)
    r'[1-9][0-9]*[a-z]?'        # Verse
    r'(?:-[1-9][0-9]*[a-z]?)?'  # Through verse (optional when there's only one verse)
)

BIBLE_REFERENCE_RE = re.compile(
    r'^[A-Za-z0-9 ]+ ' +                        # Book
    CHAPTER_VERSE_RE_TEXT +                     # Initial chapter/verse reference
    r'(?:, ' + CHAPTER_VERSE_RE_TEXT + r')*' +  # Additional chapter/verse references
    r'(?: [A-Z]{3,})?'                          # Version (optional)
)

def adjust_item_display(item):
    """
    This is used to adjust items once they are downloaded from OpenLP.
    The 'plugin', 'title', 'id', and 'slides' parameters are initialized.
    'footer' is blank by default.
    """
    plugin = item['plugin']

    if plugin == 'custom' or plugin == 'bibles':
        # Parse out a Bible reference.
        # Sometimes we use custom slides to adjust the display of a passage.
        ref_match = BIBLE_REFERENCE_RE.match(item['title'])
        if ref_match:
            item['footer'] = ref_match.group(0)
        else:
            item['footer'] = ''
    elif plugin == 'songs':
        # Use the song title as the footer.
        item['footer'] = item['title']
    else:
        # Do not display items from other plugins.
        item['slides'] = []


def get_openlp_url():
    try:
        with open(URL_FILE) as fd:
            previous_url = fd.read().splitlines(False)[0]
    except OSError:
        previous_url = None

    print("Enter the URL for the OpenLP Remote to connect to.")
    if previous_url:
        print("(Press ENTER to use {}, Ctrl+C to cancel)".format(previous_url))
    else:
        print("(Press Ctrl+C to cancel)")
    url = None
    
    while not url:
        url_input = input("URL: ")

        # Handle blank input.
        if not url_input:
            if previous_url:
                url_input = previous_url
            else:
                print("(Press Ctrl+C to cancel)")
                continue

        # Parse and normalize the URL.
        if '://' not in url_input:
            url_input = 'http://' + url_input
        try:
            url_parsed = urllib.parse.urlparse(url_input)
        except ValueError as e:
            print("Invalid URL entered ({})".format(str(e)))
            continue

        if url_parsed.port is None:
            url_parsed = url_parsed._replace(netloc=url_parsed.netloc + ':4316')
        url_parsed = url_parsed._replace(path='', params='', query='', fragment='')
        url = url_parsed.geturl()

        # Test it!
        try:
            poll_response = requests.get(url + '/api/poll')
            poll_response.raise_for_status()
        except requests.RequestException as e:
            print("Cannot connect to OpenLP at {}:".format(url))
            print(str(e))
            url = None

    # Save location for later.
    try:
        with open(URL_FILE, 'w') as fd:
            fd.write(url)
    except OSError:
        pass
    return url


class OpenLPConnectionError(Exception):
    pass


def get_blank_status(poll_results):
    if poll_results.get('display'):
        return 'showing desktop'
    elif poll_results.get('blank'):
        return 'blacked out'
    elif poll_results.get('theme'):
        return 'blanked to theme'


class OpenLPConnection(object):
    def __init__(self, openlp_url):
        self.openlp_url = openlp_url
        self.session = requests.Session()
        self.last_poll = None

        #: Current connection status.
        self.network_status = None
        #: The time to wait until if our network is paused.
        self.network_retry = 0

        #: The current OpenLP item. This may not always match the ID
        #: in last_poll - item is only updated if we can retrieve
        #: all of the item details in one shot.
        self.item = self._empty_item()
        self._empty_item()
        #: The index of the current slide.
        self.slide_index = None
        #: If OpenLP is blanked, the current blanking status.
        self.blank_status = None

    def _empty_item(self):
        return {
            'id':       '',
            'plugin':   '',
            'selected': False,
            'title':    '',
            'notes':    '',
            'footer':   '',
            'slides':   []
        }

    def poll(self):
        """
        Checks OpenLP for changes. If anything changed, returns True.
        """
        if self.network_status == 'comm error, paused':
            if time.monotonic() < self.network_retry:
                # Don't actually poll...
                return
            else:
                # Hey, we can retry now!
                self.network_status = None

        try:
            poll_result = self.get('/api/poll')
        except OpenLPConnectionError:
            # Couldn't poll.
            return False
        self.last_poll = poll_result

        # Check the blank status.
        self.blank_status = get_blank_status(poll_result)

        # Check the item ID.
        item_id = poll_result.get('item', '')
        slide_index = poll_result.get('slide', 0)
        if item_id != self.item['id']:
            try:
                new_item = self.fetch_item(item_id)
            except OpenLPConnectionError:
                # Couldn't download item - can't commit.
                return

            # Check the slide.
            if len(new_item['slides']) == 0:
                # Slide doesn't matter.
                self.item = new_item
                self.slide_index = None
            elif slide_index < len(new_item['slides']):
                # Successful item fetch!
                self.item = new_item
                self.slide_index = slide_index
        elif slide_index != self.slide_index:
            if len(self.item['slides']) == 0:
                self.slide_index = None
            elif slide_index < len(self.item['slides']):
                # Change the slide!
                self.slide_index = slide_index

    def fetch_item(self, item_id):
        if item_id == '':
            return self._empty_item()

        item_text = self.get('/api/controller/live/text')
        if item_text['item'] != item_id:
            # Race condition - we didn't grab the same item.
            # We raise an exception to prevent the item from committing,
            # but don't set the network status.
            raise OpenLPConnectionError
        service_list = self.get('/api/service/list')
        matching_items = [i for i in service_list['items'] if i.get('id') == item_id]
        if len(matching_items) != 1:
            raise OpenLPConnectionError

        item = matching_items[0]
        item['slides'] = item_text['slides']
        item['footer'] = ''
        adjust_item_display(item)
        return item

    def get(self, path):
        try:
            response = self.session.get(self.openlp_url + path, timeout=1)
            results = response.json()['results']
        except (requests.RequestException, KeyError):
            # We had an error. Pause if two requests in a row failed.
            if self.network_status is None:
                self.network_status = 'comm error, retrying'
            else:
                self.network_status = 'comm error, paused'
                self.network_retry = time.monotonic() + RETRY_INTERVAL
            raise OpenLPConnectionError(path)
        else:
            self.network_status = None
            return results


class Controller(object):
    def __init__(self, openlp_url, text_layer_file):
        self.openlp = OpenLPConnection(openlp_url)
        self.text_layer_file = text_layer_file
        #: The timestamp of the last change to anything.
        self.timestamp = time.strftime('%H:%M:%S')
        #: The status message to display.
        self.status = "Starting up"
        #: The last written item ID and slide index.
        self.written = ('', None)
        #: If False, it will never display a slide.
        self.enabled = True
        #: Records if an I/O error happened.
        self.io_status = None

    def update_timestamp(self):
        #: The timestamp of the last change to anything.
        self.timestamp = time.strftime('%H:%M:%S')

    def update(self):
        self.openlp.poll()
        item = self.openlp.item
        if not self.enabled or self.openlp.blank_status:
            slide_index = None
        else:
            slide_index = self.openlp.slide_index

        # Step 1: Write the layer.
        to_write = (item['id'], slide_index)
        if to_write != self.written:
            self.update_timestamp()
            try:
                self.write_layer(item, slide_index)
            except OSError:
                self.io_status = 'I/O error'
            else:
                self.io_status = None
                self.written = to_write

        # Step 2: Write the status message - actually more complicated.
        if item['footer']:
            title = item['footer'][:30]
        elif item['title']:
            title = item['title'][:30]
        else:
            title = 'untitled item'
        if len(item['slides']) > 1:
            title = "{} slide {}/{}".format(title, self.openlp.slide_index + 1, len(item['slides']))
        elif len(item['slides']) == 0:
            title = title + " (no overlay)"
        status = title + "".join(" (" + e + "!)" for e in [
            self.openlp.blank_status,
            "disabled" if not self.enabled else None,
            self.openlp.network_status,
            self.io_status
        ] if e is not None)
        if status != self.status:
            self.update_timestamp()
            self.status = status

    def write_layer(self, item, slide_index):
        with open(self.text_layer_file, 'w', newline='') as layer_fd:
            writer = csv.writer(layer_fd)
            writer.writerow(('PROGRAM', 'Body', 'Footer'))
            if len(item['slides']) == 0:
                writer.writerow(('OFF', '', ''))
            for n, slide in enumerate(item['slides']):
                switch = 'ON' if n == slide_index else 'OFF'
                writer.writerow((switch, slide['text'], item['footer']))


class StatusPrinter(object):
    def __init__(self):
        self.current = None

    def print(self, message):
        if self.current:
            if self.current == message:
                return
            print('\r' + ' ' * len(self.current), end='')
        print('\r' + message, end='')
        self.current = message


def main():
    try:
        openlp_url = get_openlp_url()
    except KeyboardInterrupt:
        return 1
    print("======================")
    print("Connected to OpenLP at {}".format(openlp_url))
    print("Using {} as text layer".format(TEXT_LAYER_FILE))
    print("Press Ctrl+C once to enable/disable, twice to quit")

    controller = Controller(openlp_url, TEXT_LAYER_FILE)
    printer = StatusPrinter()
    printer.print('[{}] {}'.format(controller.timestamp, controller.status))
    ctrl_c_timeout = 0
    waiting_to_reenable = False
    while True:
        try:
            loop_start = time.monotonic()
            # Disabling is instant, but reenabling has a 1-second delay to make sure
            # you don't reenable then immediately exit.
            if waiting_to_reenable and loop_start > ctrl_c_timeout:
                controller.enabled = True
                waiting_to_reenable = False

            # Update OpenLP and the controller.
            controller.update()
            printer.print('[{}] {}'.format(controller.timestamp, controller.status))

            # Wait for the next refresh.
            next_round = loop_start + REFRESH_INTERVAL - time.monotonic()
            if next_round > 0.05:
                time.sleep(next_round)
        except KeyboardInterrupt:
            # Ctrl+C was pressed! It may have been during sleep.
            ctrl_c = time.monotonic()
            if ctrl_c < ctrl_c_timeout:
                print("\nShutting down.")
                return 0
            else:
                ctrl_c_timeout = time.monotonic() + CTRL_C_TIMEOUT
                if controller.enabled:
                    controller.enabled = False
                else:
                    waiting_to_reenable = True


if __name__ == '__main__':
    sys.exit(main())
