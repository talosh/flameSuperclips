#!/usr/bin/env python

#
# Wiretap SDK tool for obtaining the metadata associated with a node.
#

import getopt
from adsk.libwiretapPythonClientAPI import *
from sys import exit,argv

def printUsage():
  print "Usage:\n" \
          "-n <node Id>\n"\
          "[-h <hostname> (default = localhost)]\n" \
          "[-s <metadata stream name (default = 'XML')>]\n"\
          "[-f <metadata filter>]\n"\
          "[-d <depth> (default = 1)]\n"

def main(argv):

  # Check the command line options for correctness.
  try:
    opts, args = getopt.getopt(argv, "h:n:d:s:f:")
  except getopt.GetoptError:
    printUsage()
    exit(2)

  # Declare variables (to be set from command line arguments).
  # For hostName, the default "localhost" will work if a Wiretap server 
  # is running on your machine.
  #
  nodeId = ""
  hostName = 'localhost:Gateway'
  streamName = 'SourceData'
  filter = ""
  depth = 1

  # Parse command line and set variables just declared.
  #
  for opt, arg in opts:
    if opt == '-h':
      hostName = arg
    elif opt == '-n':
      nodeId = arg
    elif opt == '-d':
      depth = int(arg)
    elif opt == '-s':
      streamName = arg
    elif opt == '-f':
      filter = arg

  if nodeId == "":
     print "Node ID not specified.\n"
     printUsage()
     exit(2)

  # Initialize the Wiretap Client API.
  #
  wiretapClient = WireTapClient()
  if not wiretapClient.init():
    raise Exception( "Unable to initialize WireTap client API" )

  try:
    # Instantiate a server handle
    #
    server = WireTapServerHandle( hostName )

    # Instantiate the node handle and get its metadata
    #  
    node = WireTapNodeHandle( server, nodeId)
    metaData = WireTapStr()
    if not node.getMetaData( streamName, filter, depth, metaData ):
       raise Exception( "Unable to retrieve meta data: %s" % node.lastError() )

    print metaData.c_str()

  finally:
    # Must destroy WireTapServerHandle and WireTapNodeHandle before
    # uninitializing the WireTap Client API.
    #
    node = None
    server = None

if __name__ == '__main__':
  main(argv[1:])
