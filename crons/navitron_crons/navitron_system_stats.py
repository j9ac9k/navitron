"""navitron_system_kills.py: cronjob for snapshotting /universe/system_kills/"""
from os import path
from datetime import datetime
import warnings

import pandas as pd
import retry

import navitron_crons.exceptions as exceptions
import navitron_crons.connections as connections
import navitron_crons._version as _version
import navitron_crons.cli_core as cli_core

HERE = path.abspath(path.dirname(__file__))

__app_version__ = _version.__version__
__app_name__ = 'navitron_system_stats'


def get_system_jumps(
        config,
        logger=cli_core.DEFAULT_LOGGER
):
    """fetches system jump information from ESI

    Args:
        config (:obj:`ProsperConfig`): config with [ENDPOINTS]
        logger (:obj:`logging.logger`, optional): logging handle

    Returns:
        :obj:`pandas.DataFrame`: parsed data

    """
    logger.info('--fetching data from ESI')
    raw_data = connections.get_esi(
        config.get('ENDPOINTS', 'source'),
        config.get('ENDPOINTS', 'system_jumps'),
        logger=logger
    )

    logger.info('--parsing data into pandas')
    system_jumps_df = pd.DataFrame(raw_data)

    logger.debug(system_jumps_df.head(5))
    return system_jumps_df

def get_system_kills(
        config,
        logger=cli_core.DEFAULT_LOGGER
):
    """fetches system kills information from ESI

    Args:
        config (:obj:`ProsperConfig`): config with [ENDPOINTS]
        logger (:obj:`logging.logger`, optional): logging handle

    Returns:
        :obj:`pandas.DataFrame`: parsed data

    """
    logger.info('--fetching data from ESI')
    raw_data = connections.get_esi(
        config.get('ENDPOINTS', 'source'),
        config.get('ENDPOINTS', 'system_kills'),
        logger=logger
    )

    logger.info('--parsing data into pandas')
    system_kills_df = pd.DataFrame(raw_data)

    logger.debug(system_kills_df.head(5))
    return system_kills_df


class NavitronSystemStats(cli_core.NavitronApplication):
    """fetch and store /universe/system_kills/ & /universe/system_jumps

    Feel free to add script-specific args/vars

    """
    PROGNAME = __app_name__
    VERSION = __app_version__

    def main(self):
        """application runtime"""
        self.load_logger(self.PROGNAME)
        self.conn = connections.MongoConnection(
            self.config,
            logger=self.logger  # note: order specific, logger may not be loaded yet
        )

        self.logger.info('HELLO WORLD')

        self.logger.info('Fetching system info: Jumps')
        try:
            # only retry first call.  Fail otherwise
            system_jumps_df = retry.api.retry_call(
                get_system_jumps,
                fkwargs={
                    'config': self.config,
                    'logger':self.logger
                },
                tries=3,
                delay=300
            )
        except Exception:  # pragma: no cover
            self.logger.error(
                '%s: Unable to fetch system_jumps',
                self.PROGNAME,
                exc_info=True
            )
            raise

        self.logger.info('Fetching system info: Kills')
        try:
            system_kills_df = get_system_kills(
                config=self.config,
                logger=self.logger
            )
        except Exception:  # pramga: no cover
            self.logger.error(
                '%s: Unable to fetch system_kills',
                self.PROGNAME,
                exc_info=True
            )
            raise

        self.logger.info('Merging system info')
        system_info_df = system_jumps_df.merge(
            system_kills_df,
            on='system_id'
        )

        self.logger.info('Appending Metadata')
        metadata_obj = cli_core.generate_metadata(
            self.PROGNAME,
            self.VERSION
        )
        system_info_df['cron_datetime'] = metadata_obj['cron_datetime']
        system_info_df['write_recipt'] = metadata_obj['write_recipt']
        self.logger.debug(system_info_df.head(5))

        self.logger.info('Pushing data to database')
        try:
            connections.dump_to_db(
                system_info_df,
                self.PROGNAME,
                self.conn,
                debug=self.debug,
                logger=self.logger
            )
            connections.write_provenance(
                metadata_obj,
                self.conn,
                debug=self.debug,
                logger=self.logger
            )
        except Exception:
            self.logger.error(
                '%s: Unable to write data to database -- Attempting to write to disk',
                self.PROGNAME,
                exc_info=True
            )
            try:
                file_name = connections.dump_to_db(
                    system_info_df,
                    self.PROGNAME,
                    self.conn,
                    debug=True,
                    logger=self.logger
                )
            except Exception:  # pramga: no cover
                self.logger.critical(
                    '%s: UNABLE TO SAVE DATA',
                    self.PROGNAME,
                    exc_info=True
                )
                raise
            self.logger.error(
                '%s: saved data safely to disk: %s',
                self.PROGNAME,
                file_name
            )

        self.logger.info('%s: Complete -- Have a nice day', self.PROGNAME)

def run_main():
    """hook for running entry_points"""
    NavitronSystemStats.run()

if __name__ == '__main__':
    run_main()
