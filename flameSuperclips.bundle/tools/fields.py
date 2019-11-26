#! /usr/bin/python

site = "http://shotgunlex.tdiuk.net"

import sys
sys.path.append("..")
import shotgun_api3


if len (sys.argv) != 2 :
    print "\nPrints a list of shotgun fields \navaliable for the shotgun entity\n"
    print "Usage: fileds.py entity"
    print "Example: fileds.py PublishedFiles\n"
    sys.exit (1)

entity = sys.argv[1:]

sg = shotgun_api3.Shotgun(site, login = "toloshnyya", password = "Mahakala108", convert_datetimes_to_utc=True)

print "%s:" % entity

schema = sg.schema_read()
for id, info in schema.items():
    if id == entity[0]:
        for key in info:
            print key
