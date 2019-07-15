#!/usr/bin/env python3

"""
Script to rip codex information from EDSM, since there is no 
actual dump of the data
"""

from html.parser import HTMLParser
import time
import datetime
import requests
import json
import os
import copy

results_file = "edsm-codex-scraper.json"

def download(filename, source_url, age_hours = None):
    """
    Downloads a file from a url. You can optionally tell it to not 
    download if the file exists and is younger than 'age' days old
    Empty / non-existant files are always downloaded
    Keeps a note of etags and won't download if they are the same
    Return value is True if a new file was downloaded
    """

    mtime = None
    if age_hours:
        old = datetime.datetime.utcnow() - datetime.timedelta(hours=age_hours)
        if os.path.exists(filename) and os.path.getsize(filename):
            mtime = os.path.getmtime(filename)

    if not mtime or mtime < old.timestamp() or etag_differs(source_url):
        r = requests.get(source_url, stream = True)
        with open(filename, "wb") as file:
            for chunk in r.iter_content(chunk_size=200000):
                file.write(chunk)
            else:
                return True
    return False

def url_gen(item, page):
    res = "https://www.edsm.net/en/search/systems/index/cmdrPosition/Sagittarius+A%2A/codexEntry/{}/onlyPopulated/0/radius/60000/sortBy/name".format(item)
    if page > 1:
        res = res + "/p/{}".format(page)
    return res

class EdsmCodexHtmlParser(HTMLParser):

    def __init__(self):
        super(EdsmCodexHtmlParser, self).__init__()
        self.systems = []
        self.in_container = False
        self.in_row = False
        self.in_body = False
        self.column = 0
        self.in_system_name = False
        self._categories = {}
        self._capture_option_value = False
        self._group = None
        self._in_codex = False

    def lookup(self, name, attrs, default = ""):
        for x in attrs:
            if x[0] == name:
                return x[1]
        return default

    def get_categories(self):
        return self._categories.copy()

    def handle_starttag(self, tag, attrs):
        #print(tag)
        if tag == 'div' and 'class' in attrs and attrs['class'] == 'container':
            self.in_container = True
        if tag == "tbody":
            self.in_body = True
        if self.in_body and tag == "tr":
            self.in_row = True
            self.column = 0
        if self.in_row and tag == "td":
            self.column = self.column + 1
        if self.column == 2 and tag == "strong":
            self.in_system_name = True
        if tag == 'select' and self.lookup('name', attrs) == "codexEntry[]":
            self._in_codex = True
        if self._in_codex and tag == "optgroup":
            self._group = self.lookup('label', attrs)
            if self._group not in self._categories:
                self._categories[self._group] = {}
        if self._in_codex and tag == "option":
            v = self.lookup('value', attrs)
            if v:
                self._option_id = v
                self._capture_option_value = True
                self._option_value = ""
       

    def handle_endtag(self, tag):
        if tag == 'div':
            self.in_container = False
        if tag == 'select':
            self._in_codex = False
        if tag == "option":
            self._capture_option_value = False
            if self._group:
                self._categories[self._group][self._option_id] = self._option_value
        if self.in_container and tag == "tbody":
            self.in_body = False
        if self.column == 2 and tag == "strong":
            self.in_system_name = False

    def handle_data(self, data):
        if self.in_system_name:
            self.systems.append(data)
        if self._capture_option_value:
            self._option_value = self._option_value + data.strip()

    def get_systems(self):
        return self.systems

def find_category_name(id, categories):
    """
    Return a tuple of the category and name for a given id
    """
    for c in categories:
        for i in categories[c]:
            if i == id:
                return (c, categories[c][i])

def update_results(current_results):
    with open(results_file, "wt") as results:
        json.dump(current_results, results, indent=1, sort_keys=True)

parser = EdsmCodexHtmlParser()

# Extract the codex classifications out of the search page

sample_search_page="edsm_codex_scraper_test-codex.html"
download(sample_search_page, "https://www.edsm.net/en/search/systems", age_hours=184)
with open(sample_search_page, "rt") as test_file:
    for line in test_file:
        parser.feed(line)

    whitelist = [
        'Trees', 
        'Spheres',
        'Hearts',
        'Plates',
        'Crystals',
        'Molluscs',
        'Pods',
        'Stolon',
        'Trees', 
        'Type Anomalies',
        'Tubers', 
        'Anemones', 
        'Lagrange',
        'Shards', 
        'Amphora Plants']
    print("Whitelist: {}".format(whitelist))
    classifications = []
    for k in parser.get_categories():
        if any( [x in k for x in whitelist] ):
            print("{} : {} entries".format(k, len(parser.get_categories()[k])))
            for l in parser.get_categories()[k]:
                print("  {} ({})".format(parser.get_categories()[k][l], l))
            classifications += parser.get_categories()[k].keys()
        else:
            print("Ignoring {}".format(k))

    print("classifications: {}".format(classifications))
    current_results = {}

    if os.path.exists(results_file):
        with open(results_file, "rt") as results:
            current_results = json.load(results)

    for k in current_results:
        print("{} ({}/{})".format(current_results[k]['name'], len(set([x for x in current_results[k]['systems']])),len(current_results[k]['systems'])))

        """
        Current results should a dict keyed on the id containing 
        { classification: <name>
          name: <name>
          last_updated: <isodate>
          systems: [ <systemname> ... ]
        }
        """

    for item_code in classifications:
        if item_code not in current_results:
            page = 1
            res = []
            page_size = 100
            while page_size == 100:
                print("Page {}".format(page))
                r = requests.get(url_gen(item_code, page))
                page = page + 1
                parser = EdsmCodexHtmlParser()
                parser.feed(r.text)
                page_size = len(parser.get_systems())
                res = res + parser.get_systems()
                print("{} systems".format(len(res)))
                time.sleep(60)

            print("Found {} systems for {}".format(len(res), item_code))
            current_results[item_code] = { "classification": find_category_name(item_code, parser.get_categories())[0], "systems": res, "name": find_category_name(item_code, parser.get_categories())[1]}
            update_results(current_results)



    
