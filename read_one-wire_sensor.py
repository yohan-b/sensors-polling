#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import subprocess
import sys

parser = argparse.ArgumentParser(description='Read one-wire sensor.')
parser.add_argument('metric', type=str,
                    help='Metric name.')
parser.add_argument('path', type=str,
                    help='owfs sensor path.')

args = parser.parse_args()

try:
  returned_output = subprocess.check_output(["/usr/bin/owread", "-s", "localhost:4304", args.path])
  try:
      value = round(float(returned_output.decode("utf-8").strip().strip("'")), 1)
  except ValueError:
      print (now()+" "+room+": Expected temperature, got garbage: "+returned_output)
      sys.exit(1)
except Exception as e:
  print(e)
  sys.exit(1)

data = {}
data[args.metric] = value
print(json.dumps(data))
