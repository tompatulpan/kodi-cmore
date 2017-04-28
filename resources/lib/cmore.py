# -*- coding: utf-8 -*-
"""
A Kodi-agnostic library for C More
"""
import os
import json
import codecs
import cookielib
import time
import calendar
import uuid
from urllib import urlencode
from datetime import datetime, timedelta

import requests
import xmltodict


class CMore(object):
    def __init__(self, settings_folder, country, debug=False):
        self.debug = debug
        self.country = country
        self.domain_suffix = self.country.split('_')[1].lower()
        self.http_session = requests.Session()
        self.settings_folder = settings_folder
        self.cookie_jar = cookielib.LWPCookieJar(os.path.join(self.settings_folder, 'cookie_file'))
        self.credentials_file = os.path.join(settings_folder, 'credentials')
        self.base_url = 'https://cmore-mobile-bff.b17g.services'
        self.config_path = os.path.join(self.settings_folder, 'configuration.json')
        self.config_version = '3.1.4'
        self.config = self.get_config()
        self.client = 'cmore-android'
        self.pages = ['start', 'movies', 'series', 'sports', 'tv', 'programs', 'kids']  # hopefully, this can be acquired dynamically in the future
        try:
            self.cookie_jar.load(ignore_discard=True, ignore_expires=True)
        except IOError:
            pass
        self.http_session.cookies = self.cookie_jar

    class CMoreError(Exception):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return repr(self.value)

    def log(self, string):
        if self.debug:
            try:
                print '[C More]: %s' % string
            except UnicodeEncodeError:
                # we can't anticipate everything in unicode they might throw at
                # us, but we can handle a simple BOM
                bom = unicode(codecs.BOM_UTF8, 'utf8')
                print '[C More]: %s' % string.replace(bom, '')
            except:
                pass

    def make_request(self, url, method, params=None, payload=None, headers=None):
        """Make an HTTP request. Return the response."""
        self.log('Request URL: %s' % url)
        self.log('Method: %s' % method)
        self.log('Params: %s' % params)
        self.log('Payload: %s' % payload)
        self.log('Headers: %s' % headers)
        try:
            if method == 'get':
                req = self.http_session.get(url, params=params, headers=headers, verify=False)
            elif method == 'put':
                req = self.http_session.put(url, params=params, data=payload, headers=headers, verify=False)
            else:  # post
                req = self.http_session.post(url, params=params, data=payload, headers=headers, verify=False)
            self.log('Response code: %s' % req.status_code)
            self.log('Response: %s' % req.content)
            self.cookie_jar.save(ignore_discard=True, ignore_expires=False)
            self.raise_cmore_error(req.content)
            return req.content

        except requests.exceptions.ConnectionError as error:
            self.log('Connection Error: - %s' % error.message)
            raise
        except requests.exceptions.RequestException as error:
            self.log('Error: - %s' % error.value)
            raise

    def raise_cmore_error(self, response):
        try:
            error = json.loads(response)['error']
            if isinstance(error, dict):
                if 'message' in error.keys():
                    raise self.CMoreError(error['message'])
                elif 'code' in error.keys():
                    raise self.CMoreError(error['code'])
            elif isinstance(error, str):
                raise self.CMoreError(error)

            raise self.CMoreError('Error')  # generic error message

        except KeyError:
            pass
        except ValueError:  # when response is not in json
            pass

    def get_config(self):
        """Return the config in a dict. Re-download if the config version doesn't match self.config_version."""
        try:
            config = json.load(open(self.config_path))['data']
        except IOError:
            self.download_config()
            config = json.load(open(self.config_path))['data']

        config_version = int(str(config['settings']['currentAppVersion']).replace('.', ''))
        version_to_use = int(str(self.config_version).replace('.', ''))
        if config_version != version_to_use:
            self.download_config()
            config = json.load(open(self.config_path))['data']

        return config

    def download_config(self):
        """Download the C More app configuration."""
        url = self.base_url + '/configuration'
        params = {
            'device': 'android_tab',
            'locale': self.country
        }
        config_data = self.make_request(url, 'get', params=params)
        with open(self.config_path, 'w') as fh_config:
            fh_config.write(config_data)

    def save_credentials(self, credentials):
        credentials_dict = json.loads(credentials)['data']
        if self.get_credentials().get('remember_me'):
            credentials_dict['remember_me'] = {}
            credentials_dict['remember_me']['token'] = self.get_credentials()['remember_me']['token']  # resave token
        with open(self.credentials_file, 'w') as fh_credentials:
            fh_credentials.write(json.dumps(credentials_dict))

    def reset_credentials(self):
        credentials = {}
        with open(self.credentials_file, 'w') as fh_credentials:
            fh_credentials.write(json.dumps(credentials))

    def get_credentials(self):
        try:
            with open(self.credentials_file, 'r') as fh_credentials:
                credentials_dict = json.loads(fh_credentials.read())
                return credentials_dict
        except IOError:
            self.reset_credentials()
            with open(self.credentials_file, 'r') as fh_credentials:
                return json.loads(fh_credentials.read())

    def get_operators(self):
        url = self.config['links']['accountAPI'] + 'operators'
        params = {
            'client': self.client,
            'country_code': self.domain_suffix
        }
        data = self.make_request(url, 'get', params=params)

        return json.loads(data)['data']['operators']

    def login(self, username=None, password=None, operator=None):
        url = self.config['links']['accountAPI'] + 'session'
        params = {
            'client': self.client,
            'legacy': 'true'
        }

        if self.get_credentials().get('remember_me'):  # TODO: find out when token expires
            method = 'put'
            payload = {
                'locale': self.country,
                'remember_me': self.get_credentials()['remember_me']['token']
            }
        else:
            method = 'post'
            payload = {
                'username': username,
                'password': password
            }
            if operator:
                payload['country_code'] = self.domain_suffix
                payload['operator'] = operator


        credentials = self.make_request(url, method, params=params, payload=payload)
        self.save_credentials(credentials)

    def get_page(self, page_id, namespace='page'):
        url = self.config['links']['pageAPI'] + page_id
        params = {
            'locale': self.country,
            'namespace': namespace
        }
        headers = {'Authorization': 'Bearer {0}'.format(self.get_credentials().get('jwt_token'))}
        data = self.make_request(url, 'get', params=params, headers=headers)

        return json.loads(data)['data']

    def get_contentdetails(self, page_type, page_id, season=None, size='999', page='1'):
        url = self.config['links']['contentDetailsAPI'] + '{0}/{1}'.format(page_type, page_id)
        params = {'locale': self.country}
        if season:
            params['season'] = season
            params['size'] = size
            params['page'] = page

        headers = {'Authorization': 'Bearer {0}'.format(self.get_credentials().get('jwt_token'))}
        data = self.make_request(url, 'get', params=params, headers=headers)

        return json.loads(data)['data']

    def parse_page(self, page_id, namespace='page', main_categories=True):
        page = self.get_page(page_id, namespace)
        if 'targets' in page.keys():
            return page['targets']
        elif page['containers']['page_link_container']['pageLinks'] and main_categories:
            return page['containers']['page_link_container']['pageLinks']
        else:
            categories = []
            for i in page['containers']['genre_containers']:
                if i['pageLink']['id']:
                    categories.append(i['pageLink'])
                else:
                    category = {
                        'id': i['id'],
                        'attributes': i['attributes'],
                        'item_data': i['targets']

                    }
                    categories.append(category)

            return categories

    def get_unfinished_assets(self, limit=200):
        url = self.config['links']['personalizationAPI'] + 'unfinished_assets'
        params = {
            'limit': limit,
            'locale': self.country
        }
        headers = {'Authorization': 'Bearer {0}'.format(self.get_credentials().get('jwt_token'))}
        data = self.make_request(url, 'get', params=params, headers=headers)

        return json.loads(data)['data']

    def get_stream(self, video_id):
        stream = {}
        allowed_formats = ['ism', 'mpd']
        url = self.config['links']['vimondRestAPI'] + 'api/tve_web/asset/{0}/play.json'.format(video_id)
        params = {'protocol': 'VUDASH'}
        headers = {'Authorization': 'Bearer {0}'.format(self.get_credentials().get('vimond_token'))}
        data_dict = json.loads(self.make_request(url, 'get', params=params, headers=headers))['playback']
        stream['drm_protected'] = data_dict['drmProtected']

        if isinstance(data_dict['items']['item'], list):
            for i in data_dict['items']['item']:
                if i['mediaFormat'] in allowed_formats:
                    stream['mpd_url'] = i['url']
                    if stream['drm_protected']:
                        stream['license_url'] = i['license']['@uri']
                        stream['drm_type'] = i['license']['@name']
                    break
        else:
            stream['mpd_url'] = data_dict['items']['item']['url']
            if stream['drm_protected']:
                stream['license_url'] = data_dict['items']['item']['license']['@uri']
                stream['drm_type'] = data_dict['items']['item']['license']['@name']

        return stream

    def get_image_url(self, image_url):
        """Request the image from their image proxy. Can be extended to resize/add image effects automatically.
        See https://imageproxy.b17g.services/docs for more information."""
        return '{0}?source={1}'.format(self.config['links']['imageProxy'], image_url)

