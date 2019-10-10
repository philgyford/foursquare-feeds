#!/usr/bin/env python3
import argparse
import configparser
from datetime import datetime
import logging
import os
import pytz
from xml.sax.saxutils import escape as xml_escape

import foursquare
from ics import Calendar, Event
import simplekml

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


current_dir = os.path.realpath(os.path.dirname(__file__))
CONFIG_FILE = os.path.join(current_dir, "config.ini")

# The kinds of file we can generate:
VALID_KINDS = ["ics", "kml"]


class FeedGenerator:

    fetch = "recent"

    def __init__(self, fetch="recent"):
        "Loads config, sets up Foursquare API client."

        self.fetch = fetch

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
        self.kml_filepath = config.get("Local", "KmlFilepath")

    def generate(self, kind="ics"):
        "Call this to fetch the data from the API and generate the file."
        if kind not in VALID_KINDS:
            raise ValueError("kind should be one of {}.".format(", ".join(VALID_KINDS)))

        if self.fetch == "all":
            checkins = self._get_all_checkins()
        else:
            checkins = self._get_recent_checkins()

        plural = "" if len(checkins) == 1 else "s"
        logger.info("Fetched {} checkin{} from the API".format(len(checkins), plural))

        if kind == "ics":
            filepath = self._generate_ics_file(checkins)
        elif kind == "kml":
            filepath = self._generate_kml_file(checkins)

        logger.info("Generated file {}".format(filepath))

        exit(0)

    def _get_recent_checkins(self):
        "Make one request to the API for the most recent checkins."
        results = self._get_checkins_from_api()
        return results["checkins"]["items"]

    def _get_all_checkins(self):
        "Make multiple requests to the API to get ALL checkins."
        offset = 0
        checkins = []
        # Temporary total:
        total_checkins = 9999999999

        while offset < total_checkins:

            results = self._get_checkins_from_api(offset)

            if offset == 0:
                # First time, set the correct total:
                total_checkins = results["checkins"]["count"]
                plural = "" if total_checkins == 1 else "s"
                logger.debug("{} checkin{} to fetch".format(total_checkins, plural))

            logger.debug("Fetched {}-{}".format(offset + 1, offset + 250))

            checkins += results["checkins"]["items"]
            offset += 250

        return checkins

    def _get_checkins_from_api(self, offset=0):
        """Returns a list of recent checkins for the authenticated user.

        Keyword arguments:
        offset -- Integer, the offset number to send to the API.
                  The number of results to skip.
        """

        try:
            return self.client.users.checkins(
                params={"limit": 250, "offset": offset, "sort": "newestfirst"}
            )
        except foursquare.FoursquareException as err:
            logger.error(
                "Error getting checkins, with offset of {}: {}".format(offset, err)
            )
            exit(1)

    def _get_user(self):
        "Returns details about the authenticated user."
        try:
            user = self.client.users()
        except foursquare.FoursquareException as err:
            logger.error("Error getting user: {}".format(err))
            exit(1)

        return user["user"]

    def _generate_ics_file(self, checkins):
        """Supplied with a list of checkin data from the API, generates
        and saves a .ics file.

        Returns the filepath of the saved file.

        Keyword arguments:
        checkins -- A list of dicts, each one data about a single checkin.
        """
        calendar = self._generate_calendar(checkins)

        with open(self.ics_filepath, "w") as f:
            f.writelines(calendar)

        return self.ics_filepath

    def _generate_calendar(self, checkins):
        """Supplied with a list of checkin data from the API, generates
        an ics Calendar object and returns it.

        Keyword arguments:
        checkins -- A list of dicts, each one data about a single checkin.
        """
        user = self._get_user()

        c = Calendar()

        for checkin in checkins:
            if "venue" not in checkin:
                # I had some checkins with no data other than
                # id, createdAt and source.
                continue

            venue_name = checkin["venue"]["name"]
            tz_offset = self._get_checkin_timezone(checkin)

            e = Event()

            e.name = "@ {}".format(venue_name)
            e.location = venue_name
            e.url = "{}/checkin/{}".format(user["canonicalUrl"], checkin["id"])
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

    def _generate_kml_file(self, checkins):
        """Supplied with a list of checkin data from the API, generates
        and saves a kml file.

        Returns the filepath of the saved file.

        Keyword arguments:
        checkins -- A list of dicts, each one data about a single checkin.
        """
        user = self._get_user()

        kml = simplekml.Kml()

        # The original Foursquare files had a Folder with name and
        # description like this, so:
        user_name = "{} {}".format(user["firstName"], user["lastName"])
        name = "foursquare checkin history for {}".format(user_name)
        fol = kml.newfolder(name=name, description=name)

        for checkin in checkins:
            if "venue" not in checkin:
                # I had some checkins with no data other than
                # id, createdAt and source.
                continue

            venue_name = checkin["venue"]["name"]
            tz_offset = self._get_checkin_timezone(checkin)
            url = "https://foursquare.com/v/{}".format(checkin["venue"]["id"])

            description = ['@<a href="{}">{}</a>'.format(url, venue_name)]
            if "shout" in checkin and len(checkin["shout"]) > 0:
                description.append('"{}"'.format(checkin["shout"]))
            description.append("Timezone offset: {}".format(tz_offset))

            coords = [
                (
                    checkin["venue"]["location"]["lng"],
                    checkin["venue"]["location"]["lat"],
                )
            ]

            visibility = 0 if "private" in checkin else 1

            pnt = fol.newpoint(
                name=venue_name,
                description="<![CDATA[{}]]>".format("\n".join(description)),
                coords=coords,
                visibility=visibility,
                # Both of these were set like this in Foursquare's original KML:
                altitudemode=simplekml.AltitudeMode.relativetoground,
                extrude=1,
            )

            # Foursquare's KML feeds had 'updated' and 'published' elements
            # in the Placemark, but I don't *think* those are standard, so:
            pnt.timestamp.when = (
                datetime.utcfromtimestamp(checkin["createdAt"])
                .replace(tzinfo=pytz.utc)
                .isoformat()
            )

            # Use the address, if any:
            if "location" in checkin["venue"]:
                loc = checkin["venue"]["location"]
                if "formattedAddress" in loc and len(loc["formattedAddress"]) > 0:
                    address = ", ".join(loc["formattedAddress"])
                    # While simplexml escapes other strings, it threw a wobbly
                    # over '&' in addresses, so escape them:
                    pnt.address = xml_escape(address)

        kml.save(self.kml_filepath)

        return self.kml_filepath

    def _get_checkin_timezone(self, checkin):
        """Given a checkin from the API, returns a string representing the
        timezone offset of that checkin.
        In the API they're given as a number of minutes, positive or negative.

        e.g. if offset is 60,   this returns '+01:00'
             if offset is 0,    this returns '+00:00'
             if offset is -480, this returns '-08:00'

        Keyword arguments
        checkin -- A dict of data about a single checkin
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

    parser = argparse.ArgumentParser(
        description="Makes a .ics file from your Foursquare/Swarm checkins"
    )

    parser.add_argument(
        "--all",
        help="Fetch all checkins, not only the most recent",
        required=False,
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "-k",
        "--kind",
        action="store",
        help="Either ics (default) or kml",
        required=False,
        type=str,
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        help="-v or --verbose for brief output; -vv for more.",
        required=False,
    )

    args = parser.parse_args()

    if args.verbose == 1:
        logger.setLevel(logging.INFO)
    elif args.verbose == 2:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.WARNING)

    if args.all:
        to_fetch = "all"
    else:
        to_fetch = "recent"

    if args.kind:
        if args.kind in VALID_KINDS:
            kind = args.kind
        else:
            raise ValueError("kind should be one of {}.".format(", ".join(VALID_KINDS)))
    else:
        kind = "ics"

    generator = FeedGenerator(fetch=to_fetch)

    generator.generate(kind=kind)

    exit(0)
