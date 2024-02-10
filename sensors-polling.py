#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import time
import signal
import yaml
import requests
import subprocess
import argparse
import threading
import socketserver
import sys
from http.server import BaseHTTPRequestHandler
from threading import Event
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

xprint_lock = Lock()

def xprint(*args, **kwargs):
    """Thread safe print function"""
    with xprint_lock:
        print(*args, **kwargs)
        sys.stdout.flush()

parser = argparse.ArgumentParser(description='Sensors polling and metrics recording.')
parser.add_argument("-v", "--verbosity", help="Increase output verbosity",
                    type=str, choices=['DEBUG', 'INFO', 'WARNING'], default='INFO')
args = parser.parse_args()

verbosity = args.verbosity
logger = logging.getLogger('sensors-polling')

if verbosity == 'DEBUG':
    logger.setLevel(logging.DEBUG)
elif verbosity == 'INFO':
    logger.setLevel(logging.INFO)
elif verbosity == 'WARNING':
    logger.setLevel(logging.WARNING)

# create console handler
ch = logging.StreamHandler()
# create formatter
formatter = logging.Formatter('[%(levelname)s] %(name)s: [%(threadName)s] %(message)s')
# add formatter to ch
ch.setFormatter(formatter)
# add ch to logger
logger.addHandler(ch)

logger.info("====== Starting ======")

stop = Event()
last_data = {}

def handler(signum, frame):
    global stop
    logger.info("Got interrupt: "+str(signum))
    stop.set()
    logger.info("Shutdown")

signal.signal(signal.SIGTERM,handler)
signal.signal(signal.SIGINT,handler)

with open('./conf.yml') as conf:
    yaml_conf = yaml.load(conf)
    polling_conf = yaml_conf.get("polling_conf")
    http_port = yaml_conf.get("http_port")
    default_polling_interval = yaml_conf.get("default_polling_interval")
    default_recording_interval = yaml_conf.get("default_recording_interval")
    max_threads = len(polling_conf)
    recording_api_key = yaml_conf.get("recording_api_key")
    post_url = yaml_conf.get("post_url")

def sensors_polling(poller_conf):
    global stop
    global last_data
    s = requests.Session()
    start_time=time.time()
    last_polling_time=None
    last_recording_time=None
    if 'polling_interval' in poller_conf.keys():
        polling_interval = poller_conf['polling_interval']
    else:
        polling_interval = default_polling_interval

    if 'recording_interval' in poller_conf.keys():
        recording_interval = poller_conf['recording_interval']
    else:
        recording_interval = default_recording_interval

    while True:
        if stop.is_set():
            logger.info('Stopping thread '+poller_conf['name'])
            break
        logger.debug('New while loop for '+poller_conf['name'])
        utc_now = datetime.utcnow()
        now = datetime.now()
        current_time=time.time()
        logger.debug('current_time: '+str(current_time))

        # Polling
        try:
            logger.debug('Getting data for '+poller_conf['name'])
            command = [poller_conf['executable']] + poller_conf['arguments']
            returned_output = subprocess.check_output(command)
            data = json.loads(returned_output.decode("utf-8"))
            logger.debug('Got: '+returned_output.decode("utf-8"))
            for metric in poller_conf['metrics']:
                last_data[metric['name']] = {'value': data[metric['name']], 'timestamp': utc_now.isoformat()}
            last_polling_time=time.time()
            logger.debug('last_polling_time: '+str(last_polling_time))
        except Exception as e:
            logger.error(e)
        if last_polling_time is None:
            polling_missed = int((current_time - start_time) // polling_interval)
        else:
            polling_missed = int((current_time - last_polling_time) // polling_interval)
        if polling_missed > 0:
            logger.warning("Missed "+str(polling_missed)+" polling iteration(s)")

        # Recording
        if last_polling_time is not None:
            if last_recording_time is not None:
                recording_interval_elapsed = (current_time - last_recording_time > recording_interval)
                polling_recent_enough = (last_polling_time > last_recording_time + recording_interval/2)
                logger.debug('recording_interval_elapsed: '+str(recording_interval_elapsed))
                logger.debug('polling_recent_enough: '+str(polling_recent_enough))
            if last_recording_time is None or (recording_interval_elapsed and polling_recent_enough):
                try:
                    for metric in poller_conf['metrics']:
                        logger.debug('Posting data for '+metric['name'])
                        r = s.post(post_url[metric['type']],
                                   headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:75.0) Gecko/20100101 Firefox/75.0',
                                            'X-API-KEY': recording_api_key},
                                   json={'metric': metric['name'],
                                         'value': last_data[metric['name']]['value'],
                                         'time': utc_now.isoformat()})
                        if r.status_code != 201:
                            logger.error(str(r.status_code)+" "+r.reason)
                    # It has to be current_time variable so the interval check works correctly
                    last_recording_time=current_time
                    logger.debug('last_recording_time: '+str(last_recording_time))
                except Exception as e:
                    logger.error(e)
        if last_recording_time is None:
            recording_missed = int((current_time - start_time) // recording_interval)
        else:
            recording_missed = int((current_time - last_recording_time) // recording_interval)
        if recording_missed > 0:
            logger.warning("Missed "+str(recording_missed)+" recording iteration(s)")

        # Sleeping
        time_to_sleep = polling_interval - ((current_time - start_time) % polling_interval)
        logger.debug('Sleeping '+str(time_to_sleep)+' seconds for '+poller_conf['name'])
        stop.wait(timeout=time_to_sleep)

def metric_list():
    metrics = []
    for poller_conf in polling_conf:
        for metric in poller_conf['metrics']:
            metrics.append(metric['name'])
    return metrics

class MyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(bytes(str(metric_list())+'\n', 'utf-8'))
        if self.path[1:] in metric_list():
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(bytes(json.dumps(last_data[self.path[1:]])+'\n', 'utf-8'))
        else:
            self.send_response(404)
    # This rewrites the BaseHTTP logging function
    def log_message(self, format, *args):
        if verbosity == 'INFO':
            xprint("%s - - [%s] %s" %
                 (self.address_string(),
                  self.log_date_time_string(),
                  format%args))

class WebThread(threading.Thread):
    def run(self):
        httpd.serve_forever()

httpd = socketserver.TCPServer(("", http_port), MyHandler, bind_and_activate=False)
httpd.allow_reuse_address = True
httpd.server_bind()
httpd.server_activate()
webserver_thread = WebThread()
webserver_thread.start()
 
executor = ThreadPoolExecutor(max_workers=max_threads)
threads = []
for poller_conf in polling_conf:
    threads.append(executor.submit(sensors_polling, poller_conf))

logger.info("Polling "+str(metric_list()))

while True:
    if stop.is_set():
        executor.shutdown(wait=True)
        httpd.shutdown()
        httpd.server_close()
        break
    for thread in threads:
        if not thread.running():
            try:
                res = thread.exception(timeout=1)
                if res is not None:
                    logger.error(res)
            except Exception as e:
                logger.error(e)
    stop.wait(timeout=0.5)

logger.info("====== Ended successfully ======")

# vim: set ts=4 sw=4 sts=4 et :
