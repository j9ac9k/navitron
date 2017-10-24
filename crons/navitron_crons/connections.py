"""connections.py: general tools for all cronjobs: db connection and requests"""
from os import path
from datetime import datetime
import warnings
import json  # TODO: ujson?

import requests
import pymongo

import navitron_crons.exceptions as exceptions
import navitron_crons.cli_core as cli_core

DEFAULT_HEADER = {
    'User-Agent': 'Navitron-cron: https://github.com/j9ac9k/NavitronEve'
}
HERE = path.abspath(path.dirname(__file__))

def get_esi(
        source_route,
        endpoint_route,
        params=None,
        headers=DEFAULT_HEADER,
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
    logger.info('--fetching URL: %s', address)

    req = requests.get(address, params=params, headers=headers)
    req.raise_for_status()
    data = req.json()

    return data

DATA_PROJECTION = {
    '_id': False,
    'metadata': False,
    'write_recipt': False
}
def fetch_current_sde(
        collection_name,
        conn,
        query={},
        projection=DATA_PROJECTION,
        logger=cli_core.DEFAULT_LOGGER
):
    """fetch current SDE collection

    Args:
        collection_name (str): name of SDE collection/table
        conn (:obj:`MongoConnection`): connection hnadle
        query (:obj:`dict`, optional): filtering query
        projection (:obj:`dict`, optional): pymongo projection (think SELECT)
        logger (:obj:`logging.logger`, optional): logging handle

    Returns:
        :obj:`pandas.DataFrame` or `NoneType`

    """
    logger.info('--fetching existing SDE data: %s', collection_name)

    with conn as db_conn:
        raw_data = list(db_conn[collection_name].\
            find(query, projection=projection)
        )

    if not raw_data:
        logger.warning('NO SDE DATA FOUND IN %s', collection_name)
        return None

    logger.info('--pushing data into Pandas')
    data_df = pd.DataFrame(raw_data)

    logger.debug(data_df.head(5))

    return data_df

def debug_dump(
        raw_data,
        file_name,
        dump_path=HERE
):
    """drop data to file rather than to mongodb

    Args:
        raw_data (:obj:`list`): JSON-serializable data
        file_name (str): dump filename (database_collection)
        dump_path (str, optional)

    Returns:
        str: File name of dump

    """
    warnings.warn('Writing data to disk, not database', RuntimeWarning)
    file_name = '{}__{}.json'.format(file_name, datetime.utcnow().isoformat())
    file_path = path.join(dump_path, file_name)
    with open(file_path, 'w') as dump_fh:
        json.dump(raw_data, dump_fh)

    return file_path

PROVENANCE_COLLECTION='provenance_recipts'
def write_provenance(
        metadata_obj,
        conn,
        provenance_collection=PROVENANCE_COLLECTION,
        debug=False,
        logger=cli_core.DEFAULT_LOGGER
):
    """write recipts to db with source information.

    Notes:
        since most writes are bulk-writes, single meta tag->multiple documents

    Args:
        metadata_obj (:obj:`dict`): metadata to write to provenance db
        conn (:obj:`MongoConnection`): database handle to write with
        provenance_collection (str, optional): name of collection to store to
        debug (bool, optional): actually write to db?
        logger (:obj:`logging.logger`, optional): logging handle

    """
    if debug:
        logger.warning('DEBUG MODE ENABLED: writing data to disk')
        warnings.warn('Not writing provenance data', RuntimeWarning)
        return

    logger.info('--passing data to Mongo')
    with conn as db_conn:
        db_conn[provenance_collection].insert(metadata_obj)

def dump_to_db(
        data_df,
        collection_name,
        conn,
        debug=False,
        logger=cli_core.DEFAULT_LOGGER
):
    """push data to mongodb

    Args:
        data_df (:obj:`pandas.DataFrame` or :obj:`dict`): data to write to db
        collection_name (str): table to write data to
        conn (:obj:`MongoConnection`): database handle to write with
        debug (bool, optional): actually write to db?  Or dump to file
        logger (:obj:`logging.logger`, optional): logging handle

    Returns:
        None?

    """
    if not isinstance(data_df, (dict, list)):
        logger.info('--pulling data out of Pandas->list')
        raw_data = data_df.to_dict(orient='records')
    else:
        raw_data = data_df

    if debug:
        logger.warning('DEBUG MODE ENABLED: writing data to disk')
        dump_path = ''
        try:
            dump_path = cli_core.CONFIG.get('GENERAL', 'dump_path')
        except Exception:
            pass

        if not dump_path:
            dump_path = HERE
        return debug_dump(
            raw_data,
            '{}__{}'.format(conn.database, collection_name),
            dump_path=dump_path
        )

    logger.info('--pushing data to mongodb')
    with conn as db_conn:
        db_conn[collection_name].insert_many(raw_data)


CONNECTION_STR = 'mongodb://{username}:{{password}}@{hostname}:{port}/{database}?{args}'
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
        self.database = config.get('MONGO', 'database')
        self.mongo_address = self._load_connection(config)

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
        # TODO: early return for "mongo conn str" in config

        self.ready_to_query = all([
            config.get('MONGO', 'username'),
            config.get('MONGO', 'password'),
            config.get('MONGO', 'hostname'),
            config.get('MONGO', 'port'),
            config.get('MONGO', 'database'),
            config.get('MONGO', 'args')
        ])

        self.password = config.get('MONGO', 'password')

        return connection_str.format(
            username=config.get('MONGO', 'username'),
            hostname=config.get('MONGO', 'hostname'),
            port=config.get('MONGO', 'port'),
            database=config.get('MONGO', 'database'),
            args=config.get('MONGO', 'args')
        )

    def __bool__(self):
        return self.ready_to_query

    def __enter__(self):
        """for `with obj()` logic -- open connection

        Returns:
            :obj:`pymongo.collections`

        """
        if not self.password or not bool(self):
            self.logger.warning('Missing connection info')
            raise exceptions.MissingMongoConnectionInfo

        self.logger.info('Connecting to: %s', self.mongo_address)
        mongo_address = self.mongo_address.format(password=self.password)

        self.mongo_conn = pymongo.MongoClient(mongo_address)

        return self.mongo_conn[self.database]

    def __exit__(self, exception_type, exception_value, traceback):
        """for `with obj()` logic -- close connection"""
        self.mongo_conn.close()
