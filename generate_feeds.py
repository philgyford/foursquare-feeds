import configparser
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CONFIG_FILE = "config.ini"


class FeedGenerator:
    def __init__(self):
        self._load_config(CONFIG_FILE)

    def _load_config(self, config_file):
        config = configparser.ConfigParser()

        try:
            config.read_file(open(config_file))
        except IOError:
            logger.critical("Can't read config file: " + config_file)
            exit()

        self.api_id = config.get("Foursquare", "ClientID")
        self.api_secret = config.get("Foursquare", "ClientSecret")

    def generate(self):
        logger.info("GENERATE")


if __name__ == "__main__":

    generator = FeedGenerator()

    generator.generate()
