#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import subprocess
import sys

parser = argparse.ArgumentParser(description='Read Yocto sensor.')
parser.add_argument('metric', type=str,
                    help='Metric name.')
parser.add_argument('binary', type=str,
                    help='Yocto binary.')
parser.add_argument('sensor', type=str,
                    help='Sensor name.')

args = parser.parse_args()

try:
  returned_output = subprocess.check_output(["/usr/local/YoctoLib.cmdline.24497/Binaries/linux/32bits/"+args.binary, "-r", "localhost", "-f", "[result]", args.sensor, "get_currentValue"])
  try:
      value = round(float(returned_output.decode("utf-8").strip().strip("'")), 1)
  except ValueError:
      print ("Got garbage: "+returned_output)
      sys.exit(1)
except Exception as e:
  print(e)
  sys.exit(1)

data = {}
data[args.metric] = value
print(json.dumps(data))
