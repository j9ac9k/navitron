"""connections.py: general tools for all cronjobs: db connection and requests"""
from os import path
import warnings

import requests
import pymongo

import navitron_crons.exceptions as exceptions
import navitron_crons.cli_core as cli_core

DEFAULT_HEADER = {
    'User-Agent': 'Navitron-cron: https://github.com/j9ac9k/NavitronEve'
}

def get_esi(
        source_route,
        endpoint_route,
        params=None,
        header=DEFAULT_HEADER,
        logger=cli_core.DEFAULT_LOGGER
):
    """request wrapper for fetching ESI data

    Args:
        source_route (str): URI for ESI connection
        endpoint_route (str): endpoint information for ESI resource
        params (:obj:`dict`, optional): params for REST request
        header (:obj:`dict`, optional): header information for request
        logger (:obj:`logging.logger`, optional): logging handler

    Returns:
        :obj:`list` JSON return from endpoint

    """
    address = '{source_route}{endpoint_route}'.format(
        source_route=source_route,
        endpoint_route=endpoint_route
    )
    logger.debug('--fetching URL: %s', address)

    req = requests.get(address, params=params, header=header)
    req.raise_for_status()
    data = req.json()

    return data


CONNECTION_STR = 'mongodb://{username}:{{password}}@{hostname}:{port}/{database}'
class MongoConnection(object):
    """hacky session manager for pymongo con/curr

    Args:
        config (:obj:`p_config.ProsperConfig`): config object with [MONGO] data
        logger (:obj:`logging.logger`, optional): logging handle

    """
    def __init__(
            self,
            config,
            logger=cli_core.DEFAULT_LOGGER
    ):
        self.logger = logger
        self.ready_to_query = False
        self.password = ''
        self.mongo_address = self._load_connection(config_obj)

    def _load_connection(
            self,
            config,
            connection_str=CONNECTION_STR
    ):
        """parse config for mongo connection string

        Notes:
            Does not write password to conn str

        Args:
            config (:obj:`p_config.ProsperConfig`): config object with [MONGO] data
            connection_str (str, optional): template-string for creating mongo connection

        Returns:
            str: mongo connection string

        """
        self.ready_to_query = all([
            config.get('MONGO', 'username'),
            config.get('MONGO', 'password'),
            config.get('MONGO', 'hostname'),
            config.get('MONGO', 'port'),
            config.get('MONGO', 'database')
        ])

        self.password = config.get('MONGO', 'password')

        return connection_str.format(
            username=config.get('MONGO', 'username'),
            hostname=config.get('MONGO', 'hostname'),
            port=config.get('MONGO', 'port'),
            database=config.get('MONGO', 'database')
        )

    def __bool__(self):
        return self.ready_to_query

    def __enter__(self, collection=''):
        """for `with obj()` logic -- open connection

        Args:
            collection (str, optional): collection to connect to (for shorter variables)

        Returns:
            :obj:`pymongo.collections` or TBD

        """
        if not self.password or not bool(self):
            self.logger.warning('Missing connection info')
            raise exceptions.MissingMongoConnectionInfo

        self.logger.info('Connecting to: %s', self.mongo_address)
        mongo_address = self.mongo_address.format(password=self.password)

        self.mongo_conn = pymongo.MongoClient(mongo_address)

        if colletion:
            return self.mongo_conn[self.database][collection]
        else:
            return self.mongo_conn[self.database]

    def __exit__(self, exception_type, exception_value, traceback):
        """for `with obj()` logic -- close connection"""
        self.mongo_conn.close()
