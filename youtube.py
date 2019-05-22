import logging

import httplib2
from oauth2client.file import Storage
from apiclient.discovery import build
from oauth2client.client import flow_from_clientsecrets
from oauth2client.tools import run_flow

class YoutubePlaylists():
    def __init__(self, CLIENT_SECRETS_FILE, CREDENTIALS_FILE):
        logger = logging.getLogger(__name__)
        # Login or create credentials
        YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube"
        YOUTUBE_API_SERVICE_NAME = "youtube"
        YOUTUBE_API_VERSION = "v3"

        storage = Storage(CREDENTIALS_FILE)
        credentials = storage.get()
        if credentials is None or credentials.invalid:
            logger.info('Youtube credentials invalid. Initing oAuth flow...')
            flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE, scope=YOUTUBE_SCOPE, message='Nop')
            credentials = run_flow(flow, storage)
            logger.info('Youtube credentials updated')

        self.service = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, http=credentials.authorize(httplib2.Http()))

    def _request_youtube(self, request):
        try:
            response = request.execute()
            if 'error' in response:
                error_code = response['error']['errors']['code']
                error_message = response['error']['errors']['message']
                raise ValueError('API error {} - {}'.format(error_code, error_message))
            else:
                return response
        except:
            raise ValueError('An error occured during interaction with Youtube: {}'.format(sys.exc_info()))

    # def _get_all_pages(self, request_func, kwargs):
    #     request = request_func(**kwargs)
    #     response = self._request_youtube(request)
    #     responses = response['items']
    #
    #     while 'nextPageToken' in response.keys():
    #         kwargs['pageToken'] = response['nextPageToken']
    #         request = request_func(**kwargs)
    #         response = self._request_youtube(request)
    #         responses += response['items']
    #
    #     return responses
    #
    # def get_playlists_list(self):
    #     playlists = [['liked', 'liked']]
    #
    #     request_playlists = self.service.playlists().list
    #     kwargs = {'part': 'snippet', 'mine': True}
    #     playlists_raw = self._get_all_pages(request_playlists, kwargs)
    #
    #     for playlist in playlists_raw:
    #         playlist_id = playlist['id']
    #         playlist_title = playlist['snippet']['title']
    #         playlists.append([playlist_id, playlist_title])
    #
    #     return playlists
    #
    # def get_videos_list(self, playlist_id):
    #     videos = []
    #
    #     if playlist_id == 'liked':
    #         request_liked = self.service.videos().list
    #         kwargs = {'part': 'snippet', 'myRating': 'like'}
    #         videos_raw = self._get_all_pages(request_liked, kwargs)
    #     else:
    #         request_videos = self.service.playlistItems().list
    #         kwargs = {'part': 'snippet', 'playlistId': playlist_id}
    #         videos_raw = self._get_all_pages(request_videos, kwargs)
    #
    #     for video in videos_raw:
    #         video_id = video['id']
    #         video_title = video['snippet']['title']
    #         video_descr = video['snippet']['description']
    #         videos.append([video_id, video_title, video_descr])
    #
    #     return videos

    def get_video_info(self, video_id):
        request = self.service.videos().list(part='snippet', id=video_id)
        return self._request_youtube(request)