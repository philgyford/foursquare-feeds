#!/usr/bin/env python3
import configparser
import logging
import os

import foursquare
from ics import Calendar, Event

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


current_dir = os.path.realpath(os.path.dirname(__file__))
CONFIG_FILE = os.path.join(current_dir, "config.ini")

# How many to fetch and use. Up to 250.
NUM_CHECKINS = 100


class FeedGenerator:
    def __init__(self):
        "Loads config, sets up Foursquare API client."
        self._load_config(CONFIG_FILE)

        self.client = foursquare.Foursquare(access_token=self.api_access_token)

    def _load_config(self, config_file):
        "Set object variables based on supplied config file."
        config = configparser.ConfigParser()

        try:
            config.read_file(open(config_file))
        except IOError:
            logger.critical("Can't read config file: " + config_file)
            exit()

        self.api_access_token = config.get("Foursquare", "AccessToken")
        self.ics_filepath = config.get("Local", "IcsFilepath")

    def generate(self):
        ""
        checkins = self._get_checkins()

        calendar = self._generate_calendar(checkins)

        with open(self.ics_filepath, "w") as f:
            f.writelines(calendar)

        exit(0)

    def _get_checkins(self):
        "Returns a list of recent checkins for the authenticated user."

        try:
            return self.client.users.checkins(
                params={"limit": NUM_CHECKINS, "sort": "newestfirst"}
            )
        except foursquare.FoursquareException as e:
            logger.error("Error getting checkins: {}".format(e))
            exit(1)

    def _get_user_url(self):
        "Returns the Foursquare URL for the authenticated user."
        try:
            user = self.client.users()
        except foursquare.FoursquareException as e:
            logger.error("Error getting user: {}".format(e))
            exit(1)

        return user["user"]["canonicalUrl"]

    def _generate_calendar(self, checkins):
        """Supplied with a list of checkin data from the API, generates an
        ics Calendar object and returns it.
        """
        user_url = self._get_user_url()

        c = Calendar()

        for checkin in checkins["checkins"]["items"]:
            venue_name = checkin["venue"]["name"]
            tz_offset = self._get_checkin_timezone(checkin)

            e = Event()

            e.name = "@ {}".format(venue_name)
            e.location = venue_name
            e.url = "{}/checkin/{}".format(user_url, checkin["id"])
            e.uid = "{}@foursquare.com".format(checkin["id"])
            e.begin = checkin["createdAt"]

            # Use the 'shout', if any, and the timezone offset in the
            # description.
            description = []
            if "shout" in checkin and len(checkin["shout"]) > 0:
                description = [checkin["shout"]]
            description.append("Timezone offset: {}".format(tz_offset))
            e.description = "\n".join(description)

            # Use the venue_name and the address, if any, for the location.
            location = venue_name
            if "location" in checkin["venue"]:
                loc = checkin["venue"]["location"]
                if "formattedAddress" in loc and len(loc["formattedAddress"]) > 0:
                    address = ", ".join(loc["formattedAddress"])
                    location = "{}, {}".format(location, address)
            e.location = location

            c.events.add(e)

        return c

    def _get_checkin_timezone(self, checkin):
        """Given a checkin from the API, returns a string representing the
        timezone offset of that checkin.
        In the API they're given as a number of minutes, positive or negative.

        e.g. if offset is 60,   this returns '+01:00'
             if offset is 0,    this returns '+00:00'
             if offset is -480, this returns '-08:00'
        """
        # In minutes, e.g. 60 or -480
        minutes = checkin["timeZoneOffset"]

        # e.g. 1 or -8
        hours = minutes / 60

        # e.g. '01.00' or '-08.00'
        if hours >= 0:
            offset = "{:05.2f}".format(hours)
            symbol = "+"
        else:
            offset = "{:06.2f}".format(hours)
            symbol = ""

        # e.g. '+01:00' or '-08.00'
        return "{}{}".format(symbol, offset).replace(".", ":")


if __name__ == "__main__":

    generator = FeedGenerator()
    generator.generate()

    exit(0)
