"""REST API wrappers

Wrappers for Telegram, Last.fm(in future) and Discogs(in future) APIs - taken from MusicBro. Lastfm only here!

"""
import logging
import os
import sys
import time
import urllib3

import requests


# Wrapper parent class
class Requester:
    def __init__(self, token, proxies={}, rate_limit=1, error_retries=3):
        # Setup logging
        # session_hash = os.environ['MB_SESSION_HASH']
        # module = os.environ['MB_MODULE']
        self.logger = logging.getLogger("comrade")

        self.token = token
        self.headers = {'User-Agent': 'MusicBro/alpha'}
        self.proxies = proxies

        self.error_retries = error_retries
        self.rate_limit =` rate_limit

        self.request_time = 0

    # Get url via requests. Return response with status 200 or raise an error
    def _get_url(self, url, params={}):
        for _ in range(self.error_retries):
            self._request_throttle()
            self.request_time = time.time()
            try:
                response = requests.get(url, headers=self.headers, proxies=self.proxies, params=params)
                self.last_response = response
                if response.status_code == 200:
                    self.logger.debug('{}: {}'.format(response.status_code, url))
                    return response.json()
                else:
                    self.logger.warning('{}: {}'.format(response.status_code, url))
            except:
                self.logger.error('{} on {}'.format(sys.exc_info(), url))
        else:
            self.logger.error('Too many request errors in a row')
            raise UserWarning('Too many request errors in a row')

    # Rate limiter, no more than n requests per second
    def _request_throttle(self):
        n = self.rate_limit
        since_last_request = time.time() - self.request_time
        if since_last_request < 1/n:
            time.sleep(1/n - since_last_request)


# Telegram wrapper subclass
class LastRequester(Requester):
    api_endpoint = 'https://ws.audioscrobbler.com/2.0/'


    # Construct url string from parameters
    def _make_url(self, method, params={}):

        url = f'{self.api_endpoint}?method={method}&api_key={self.token}&format=json'
        if params:
            params = [key + '=' + params[key] for key in params]
            params = '&' + '&'.join(params)
            url += params
        return url

    # Check and report response status
    def _check_response_status(self, response):
        if response['ok'] is True:
            return True
        else:
            return False

    # Check if artist exists
    def check_artist(self, artist):
        params = {}
        params['artist'] = artist
        params['autocorrect'] = '1'
        url = self._make_url('artist.getTopTags', params)

        response = self._get_url(url)
        try:
            tags = [tag['name'] for tag in response['toptags']['tag']]
            if 'seen live' in tags:
                tags.remove('seen live')
            return tags[0:5]
        except:
            return False

